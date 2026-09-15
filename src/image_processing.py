"""Wspólne przygotowanie obrazów z JPG, PNG i PDF do skanowania Aztec."""

from __future__ import annotations

import io
import math
import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .errors import (
    DecoderDependencyError,
    ImageTooLargeError,
    ImageTooSmallError,
    InvalidImageError,
    InvalidPdfError,
    PdfPageLimitError,
    PdfRenderError,
    PdfTooLargeError,
    UnsupportedDocumentTypeError,
)

SUPPORTED_IMAGE_FORMATS = {"JPEG", "PNG"}
DocumentType = Literal["image", "pdf"]


@dataclass(frozen=True, slots=True)
class ProcessingLimits:
    max_image_upload_mb: int
    max_pdf_upload_mb: int
    max_pdf_pages: int
    pdf_render_dpi: int
    min_image_side: int
    max_image_pixels: int


@dataclass(frozen=True, slots=True)
class PreparedImage:
    """Obraz gotowy dla istniejącego preprocessingu i czytnika Aztec."""

    image: Image.Image
    source_type: DocumentType
    page_number: int
    page_count: int


def _positive_int_from_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def get_processing_limits() -> ProcessingLimits:
    dpi = _positive_int_from_env("PDF_RENDER_DPI", 300)
    return ProcessingLimits(
        max_image_upload_mb=_positive_int_from_env("MAX_UPLOAD_MB", 10),
        max_pdf_upload_mb=_positive_int_from_env("MAX_PDF_MB", 15),
        max_pdf_pages=_positive_int_from_env("MAX_PDF_PAGES", 10),
        pdf_render_dpi=min(max(dpi, 150), 400),
        min_image_side=_positive_int_from_env("MIN_IMAGE_SIDE", 200),
        max_image_pixels=_positive_int_from_env("MAX_IMAGE_PIXELS", 25_000_000),
    )


def detect_document_type(document_bytes: bytes) -> DocumentType:
    """Rozpoznaje rzeczywistą zawartość; nazwa i MIME z uploadu nie są zaufane."""

    if not document_bytes:
        raise UnsupportedDocumentTypeError("empty upload")
    if b"%PDF-" in document_bytes[:1_024]:
        return "pdf"
    if document_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image"
    if document_bytes.startswith(b"\xff\xd8\xff"):
        return "image"
    raise UnsupportedDocumentTypeError("unknown file signature")


def prepare_document_images(
    document_bytes: bytes,
    *,
    detected_type: DocumentType | None = None,
) -> Iterator[PreparedImage]:
    """Zwraca kolejno obrazy stron dokumentu, zawsze bez plików tymczasowych."""

    document_type = detected_type or detect_document_type(document_bytes)
    if document_type == "image":
        yield PreparedImage(
            image=load_image(document_bytes),
            source_type="image",
            page_number=1,
            page_count=1,
        )
        return

    yield from _render_pdf_pages(document_bytes)


def load_image(image_bytes: bytes) -> Image.Image:
    """Waliduje JPG/PNG i zwraca obraz RGB wyłącznie w pamięci."""

    limits = get_processing_limits()
    if not image_bytes:
        raise InvalidImageError("empty image")
    if len(image_bytes) > limits.max_image_upload_mb * 1024 * 1024:
        raise ImageTooLargeError("upload byte limit exceeded")

    try:
        with Image.open(io.BytesIO(image_bytes)) as candidate:
            actual_format = candidate.format
            width, height = candidate.size
            candidate.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise InvalidImageError("image verification failed") from exc

    if actual_format not in SUPPORTED_IMAGE_FORMATS:
        raise InvalidImageError(f"unsupported image format: {actual_format}")
    if width < limits.min_image_side or height < limits.min_image_side:
        raise ImageTooSmallError(f"image dimensions: {width}x{height}")
    if width * height > limits.max_image_pixels:
        raise ImageTooLargeError(f"image pixel limit exceeded: {width}x{height}")

    try:
        with Image.open(io.BytesIO(image_bytes)) as candidate:
            candidate.load()
            normalized = ImageOps.exif_transpose(candidate).convert("RGB")
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise InvalidImageError("image decode failed") from exc
    return normalized


def _render_pdf_pages(document_bytes: bytes) -> Iterator[PreparedImage]:
    limits = get_processing_limits()
    if len(document_bytes) > limits.max_pdf_upload_mb * 1024 * 1024:
        raise PdfTooLargeError("PDF byte limit exceeded")

    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover - zależy od instalacji
        raise DecoderDependencyError("PyMuPDF is not installed") from exc

    try:
        document = pymupdf.open(stream=document_bytes, filetype="pdf")
    except Exception as exc:
        raise InvalidPdfError("cannot open PDF") from exc

    try:
        if document.needs_pass:
            raise InvalidPdfError("encrypted PDF")
        page_count = document.page_count
        if page_count <= 0:
            raise InvalidPdfError("PDF has no pages")
        if page_count > limits.max_pdf_pages:
            raise PdfPageLimitError(
                f"PDF page limit exceeded: {page_count}>{limits.max_pdf_pages}"
            )

        zoom = limits.pdf_render_dpi / 72.0
        matrix = pymupdf.Matrix(zoom, zoom)
        for page_index in range(page_count):
            try:
                page = document.load_page(page_index)
                width = max(1, math.ceil(page.rect.width * zoom))
                height = max(1, math.ceil(page.rect.height * zoom))
                if width * height > limits.max_image_pixels:
                    raise PdfRenderError(
                        f"rendered page pixel limit exceeded: {width}x{height}"
                    )
                pixmap = page.get_pixmap(
                    matrix=matrix,
                    colorspace=pymupdf.csRGB,
                    alpha=False,
                )
                image = Image.frombytes(
                    "RGB",
                    (pixmap.width, pixmap.height),
                    pixmap.samples,
                )
            except PdfRenderError:
                raise
            except Exception as exc:
                raise PdfRenderError(f"cannot render PDF page {page_index + 1}") from exc

            yield PreparedImage(
                image=image,
                source_type="pdf",
                page_number=page_index + 1,
                page_count=page_count,
            )
    finally:
        document.close()


def _overlapping_scan_regions(
    gray: np.ndarray,
) -> Iterator[tuple[str, np.ndarray]]:
    """Dzieli dużą stronę na zachodzące obszary bez utraty pokrycia."""

    height, width = gray.shape
    if min(width, height) < 1_000:
        return

    crop_width = max(1, round(width * 0.58))
    crop_height = max(1, round(height * 0.58))
    x_positions = (0, width - crop_width)
    y_positions = (0, height - crop_height)
    boxes = [
        (x, y, x + crop_width, y + crop_height)
        for y in y_positions
        for x in x_positions
    ]
    boxes.append(
        (
            (width - crop_width) // 2,
            (height - crop_height) // 2,
            (width + crop_width) // 2,
            (height + crop_height) // 2,
        )
    )

    for index, (left, top, right, bottom) in enumerate(boxes, start=1):
        yield f"region_{index}", np.ascontiguousarray(gray[top:bottom, left:right])


def generate_scan_variants(image: Image.Image) -> Iterator[tuple[str, np.ndarray]]:
    """Warianty pełnego obrazu i regionów dla małego kodu na stronie PDF."""

    rgb = np.ascontiguousarray(np.asarray(image, dtype=np.uint8))
    # Pythonowy binding zxing-cpp interpretuje 3 kanały jako BGR.
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    contrast = clahe.apply(gray)
    _threshold, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    yield "original", bgr
    yield "grayscale", gray
    yield "contrast", contrast
    yield "otsu", binary

    if max(image.size) <= 2_000:
        yield "upscaled_grayscale", cv2.resize(
            gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC
        )
        yield "upscaled_contrast", cv2.resize(
            contrast, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC
        )

    # Na skanie A4 kod z dowodu bywa mały w stosunku do całej strony.
    # Zachodzące regiony zapobiegają zgubieniu go podczas downscalingu ZXing.
    for region_name, region_gray in _overlapping_scan_regions(gray):
        region_contrast = clahe.apply(region_gray)
        yield f"{region_name}_grayscale", region_gray
        yield f"{region_name}_contrast", region_contrast

        if max(region_gray.shape) <= 2_200:
            yield f"{region_name}_upscaled", cv2.resize(
                region_contrast,
                None,
                fx=1.5,
                fy=1.5,
                interpolation=cv2.INTER_CUBIC,
            )
