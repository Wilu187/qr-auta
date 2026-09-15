"""Odczyt surowego payloadu kodu Aztec przy użyciu zxing-cpp."""

from __future__ import annotations

from collections.abc import Iterator

from PIL import Image

from .errors import AztecNotFoundError, DecoderDependencyError
from .image_processing import generate_scan_variants


def iter_aztec_payloads(image: Image.Image) -> Iterator[bytes]:
    """Zwraca unikalne reprezentacje treści ze wszystkich udanych prób Aztec."""

    try:
        import zxingcpp
    except ImportError as exc:  # pragma: no cover - zależy od środowiska instalacji
        raise DecoderDependencyError("zxing-cpp is not installed") from exc

    seen: set[bytes] = set()
    for _variant_name, variant in generate_scan_variants(image):
        try:
            barcodes = zxingcpp.read_barcodes(
                variant,
                formats=zxingcpp.BarcodeFormat.Aztec,
                try_rotate=True,
                try_downscale=True,
                try_invert=True,
                text_mode=zxingcpp.TextMode.Plain,
                binarizer=zxingcpp.Binarizer.LocalAverage,
            )
        except (TypeError, ValueError, RuntimeError):
            # Uszkodzony wariant nie przerywa kolejnych bezpiecznych prób.
            continue

        for barcode in barcodes:
            if hasattr(barcode, "valid") and not barcode.valid:
                continue
            candidates = [bytes(barcode.bytes)]
            try:
                candidates.append(barcode.text.encode("ascii", errors="strict"))
            except (AttributeError, UnicodeEncodeError):
                pass

            for candidate in candidates:
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    yield candidate

    if not seen:
        raise AztecNotFoundError("no Aztec barcode found")


def read_aztec_payload(image: Image.Image) -> bytes:
    """Zwraca pierwszy payload; zachowany interfejs dla istniejących integracji."""

    return next(iter_aztec_payloads(image))
