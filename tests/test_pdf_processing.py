import base64
import io

import pymupdf
import pytest
import zxingcpp
from PIL import Image

from src.errors import (
    AztecNotFoundInPdfError,
    InvalidPdfError,
    PdfPageLimitError,
    PdfTooLargeError,
)
from src.image_processing import prepare_document_images
from src.registration_decoder import decode_registration_certificate


def _synthetic_payload() -> bytes:
    fields = [""] * 66
    fields[0] = "XXC1"
    fields[7] = "PDF 1234"
    fields[8] = "PDF-MARKA"
    fields[13] = "SYNTHETICVINPDF01"
    utf16 = ("|".join(fields) + "|").encode("utf-16le")

    compressed = bytearray()
    for start in range(0, len(utf16), 8):
        chunk = utf16[start : start + 8]
        compressed.append(sum(1 << (7 - bit) for bit in range(len(chunk))))
        compressed.extend(chunk)
    return base64.b64encode(len(utf16).to_bytes(4, "little") + compressed)


def _aztec_png() -> bytes:
    barcode = zxingcpp.create_barcode(
        _synthetic_payload().decode("ascii"),
        zxingcpp.BarcodeFormat.Aztec,
    )
    image = Image.fromarray(barcode.to_image(scale=8)).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _make_pdf(pages: list[bytes | None]) -> bytes:
    document = pymupdf.open()
    try:
        for image_bytes in pages:
            page = document.new_page(width=400, height=400)
            if image_bytes is not None:
                page.insert_image(
                    pymupdf.Rect(40, 40, 360, 360),
                    stream=image_bytes,
                    keep_proportion=True,
                )
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


def _make_a4_pdf_with_small_aztec() -> bytes:
    document = pymupdf.open()
    try:
        page = document.new_page(width=595, height=842)
        page.insert_image(
            pymupdf.Rect(470, 715, 535, 780),
            stream=_aztec_png(),
            keep_proportion=True,
        )
        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


def test_valid_single_page_pdf() -> None:
    pdf_bytes = _make_pdf([_aztec_png()])

    certificate = decode_registration_certificate(pdf_bytes)

    assert certificate.registration_number == "PDF 1234"
    assert certificate.make == "PDF-MARKA"


def test_a4_pdf_with_small_aztec_in_page_corner() -> None:
    certificate = decode_registration_certificate(_make_a4_pdf_with_small_aztec())

    assert certificate.registration_number == "PDF 1234"


def test_multi_page_pdf_stops_after_page_with_valid_aztec() -> None:
    pdf_bytes = _make_pdf([None, _aztec_png(), None])

    certificate = decode_registration_certificate(pdf_bytes)

    assert certificate.vin == "SYNTHETICVINPDF01"


def test_pdf_without_aztec() -> None:
    pdf_bytes = _make_pdf([None, None])

    with pytest.raises(AztecNotFoundInPdfError):
        decode_registration_certificate(pdf_bytes)


def test_corrupted_pdf() -> None:
    with pytest.raises(InvalidPdfError):
        list(prepare_document_images(b"%PDF-1.7\nthis is not a PDF"))


def test_pdf_exceeding_byte_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_PDF_MB", "1")
    oversized = b"%PDF-1.7\n" + b"x" * (1024 * 1024)

    with pytest.raises(PdfTooLargeError):
        list(prepare_document_images(oversized))


def test_pdf_exceeding_page_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_PDF_PAGES", "2")
    pdf_bytes = _make_pdf([None, None, None])

    with pytest.raises(PdfPageLimitError):
        list(prepare_document_images(pdf_bytes))
