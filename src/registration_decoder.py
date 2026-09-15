"""Publiczna fasada dekodera polskiego dowodu rejestracyjnego."""

from __future__ import annotations

import base64
import binascii
import os
import re
from collections.abc import Callable
from contextlib import closing

from .aztec_reader import iter_aztec_payloads
from .errors import (
    AztecNotFoundError,
    AztecNotFoundInPdfError,
    DecompressionError,
    InvalidBase64Error,
    InvalidPayloadError,
    PayloadHeaderError,
    RegistrationDecoderError,
    UnsupportedFormatError,
)
from .image_processing import detect_document_type, prepare_document_images
from .models import RegistrationCertificateData
from .nrv2e import decompress_nrv2e

Decompressor = Callable[[bytes, int], bytes]

# Każdy wariant ma osobną mapę. Nowy układ nie dziedziczy indeksów starego.
_NEW_XXC1_FIELDS = {
    "registration_number": 7,
    "make": 8,
    "vehicle_type": 9,
    "model": 12,
    "vin": 13,
    "gross_vehicle_weight_kg": 39,  # F.2
    "curb_weight_kg": 41,  # G
    "engine_capacity_cm3": 48,  # P.1
    "power_kw": 49,  # P.2
    "fuel_type": 50,  # P.3
    "first_registration_date": 51,  # B
    "seats": 52,  # S.1
    "production_year": 56,
}

_OLD_FIELDS = {
    "registration_number": 5,
    "make": 6,
    "vehicle_type": 7,
    "model": 10,
    "vin": 11,
    "gross_vehicle_weight_kg": 23,  # F.2
    "curb_weight_kg": 25,  # G
    "engine_capacity_cm3": 32,  # P.1
    "power_kw": 33,  # P.2
    "fuel_type": 34,  # P.3
    "first_registration_date": 36,  # B
    "seats": 37,  # S.1
    "production_year": 41,
}


def decode_registration_certificate(document_bytes: bytes) -> RegistrationCertificateData:
    """Dekoduje JPG, PNG lub PDF do danych dokumentu.

    To jedyny interfejs wymagany przez resztę aplikacji. Szczegóły Aztec,
    Base64, NRV2E i układu pól pozostają ukryte w warstwie dekodera.
    """

    document_type = detect_document_type(document_bytes)
    payload_error: RegistrationDecoderError | None = None

    prepared_images = prepare_document_images(
        document_bytes,
        detected_type=document_type,
    )
    with closing(prepared_images):
        for prepared in prepared_images:
            try:
                raw_payloads = iter_aztec_payloads(prepared.image)
                for raw_payload in raw_payloads:
                    try:
                        return decode_registration_payload(raw_payload)
                    except RegistrationDecoderError as exc:
                        payload_error = _prefer_payload_error(payload_error, exc)
            except AztecNotFoundError:
                continue

    if payload_error is not None:
        raise payload_error
    if document_type == "pdf":
        raise AztecNotFoundInPdfError("no valid Aztec found on PDF pages")
    raise AztecNotFoundError("no Aztec found in image")


def decode_registration_payload(
    raw_payload: bytes | str,
    *,
    decompressor: Decompressor = decompress_nrv2e,
) -> RegistrationCertificateData:
    """Dekoduje payload odczytany z Aztec; przydatne także w testach integracji."""

    decoded_candidates = _base64_decoded_candidates(raw_payload)
    max_output_size = _get_max_output_size()
    best_error: RegistrationDecoderError | None = None

    for decoded in decoded_candidates:
        if len(decoded) < 5:
            continue
        expected_size = int.from_bytes(decoded[:4], byteorder="little", signed=False)
        if not _is_valid_output_size(expected_size, max_output_size):
            continue
        try:
            return _decode_nrv2e_document(decoded[4:], expected_size, decompressor)
        except RegistrationDecoderError as exc:
            if _error_stage(exc) > _error_stage(best_error):
                best_error = exc

    if best_error is not None:
        raise best_error

    primary = decoded_candidates[0]
    declared_size = (
        int.from_bytes(primary[:4], byteorder="little", signed=False)
        if len(primary) >= 4
        else 0
    )
    raise PayloadHeaderError(len(primary), declared_size)


def _decode_nrv2e_document(
    compressed: bytes,
    expected_size: int,
    decompressor: Decompressor,
) -> RegistrationCertificateData:
    try:
        utf16_bytes = decompressor(compressed, expected_size)
    except DecompressionError:
        raise
    except Exception as exc:
        raise DecompressionError("NRV2E backend failed") from exc

    if len(utf16_bytes) != expected_size:
        raise DecompressionError("NRV2E output length mismatch")

    # Występują dokumenty z nieparzystą deklarowaną długością (np. 1101).
    # Referencyjne dekodery alokują pełny bufor NRV2E, po czym UTF-16LE czyta
    # kompletne pary bajtów. Samotny bajt końcowy nie należy do znaku tekstu.
    text_bytes = utf16_bytes[: len(utf16_bytes) - (len(utf16_bytes) % 2)]
    try:
        text = text_bytes.decode("utf-16le", errors="strict").rstrip("\x00")
    except UnicodeDecodeError as exc:
        raise InvalidPayloadError("payload is not valid UTF-16LE") from exc
    return parse_registration_text(text)


def _get_max_output_size() -> int:
    try:
        max_output_size = int(os.getenv("NRV2E_MAX_OUTPUT_BYTES", "65536"))
    except ValueError:
        return 65_536
    return max_output_size if max_output_size > 0 else 65_536


def _is_valid_output_size(expected_size: int, max_output_size: int) -> bool:
    return 0 < expected_size <= max_output_size


def _error_stage(error: RegistrationDecoderError | None) -> int:
    """Preferuje błąd z najdalszego poprawnie osiągniętego etapu."""

    if isinstance(error, UnsupportedFormatError):
        return 4
    if isinstance(error, PayloadHeaderError):
        return 1
    if isinstance(error, DecompressionError):
        return 2
    if isinstance(error, InvalidPayloadError):
        return 3
    return 0


def _prefer_payload_error(
    current: RegistrationDecoderError | None,
    candidate: RegistrationDecoderError,
) -> RegistrationDecoderError:
    return candidate if _error_stage(candidate) > _error_stage(current) else current or candidate


def parse_registration_text(text: str) -> RegistrationCertificateData:
    """Rozpoznaje układ dokumentu i wybiera potrzebne pola bez danych C.*."""

    normalized = text.lstrip("\ufeff").rstrip("\x00")
    fields = re.split(r"\||\r?\n", normalized)

    if not fields:
        raise UnsupportedFormatError("empty registration data")

    format_marker = fields[0].strip()
    if format_marker == "XXC1":
        if len(fields) < 14:
            raise InvalidPayloadError("truncated XXC1 document")
        document_format = "new:XXC1"
        mapping = _NEW_XXC1_FIELDS
    elif format_marker.startswith("XX"):
        raise UnsupportedFormatError(f"unknown new document marker: {format_marker}")
    elif _looks_like_old_format(fields):
        document_format = "old"
        mapping = _OLD_FIELDS
    else:
        raise UnsupportedFormatError("document layout does not match a supported format")

    values = {name: _clean_value(fields, index) for name, index in mapping.items()}
    missing = tuple(name for name, value in values.items() if value is None)
    return RegistrationCertificateData(
        document_format=document_format,
        **values,
        missing_fields=missing,
    )


def _clean_value(fields: list[str], index: int) -> str | None:
    if index >= len(fields):
        return None
    value = fields[index].replace("\x00", "").strip()
    return None if not value or value in {"---", "-"} else value


def _looks_like_old_format(fields: list[str]) -> bool:
    if len(fields) < 46 or not _clean_value(fields, 0):
        return False
    essential_values = sum(
        _clean_value(fields, index) is not None for index in (5, 6, 11)
    )
    return essential_values >= 2


def _base64_decoded_candidates(raw_payload: bytes | str) -> list[bytes]:
    raw_bytes = raw_payload.encode("utf-8") if isinstance(raw_payload, str) else raw_payload
    try:
        text = raw_bytes.decode("ascii", errors="strict")
    except UnicodeDecodeError:
        text = None

    decoded_candidates: list[bytes] = []
    seen_decoded: set[bytes] = set()
    if text is not None:
        compact = "".join(text.split())
        framed_candidates = _base64_text_candidates(compact)
        for candidate in framed_candidates:
            if len(candidate) % 4 == 1:
                continue
            padded = candidate + "=" * (-len(candidate) % 4)
            alphabets = (None, b"-_") if "-" in candidate or "_" in candidate else (None,)
            for altchars in alphabets:
                try:
                    decoded = base64.b64decode(
                        padded,
                        altchars=altchars,
                        validate=True,
                    )
                except (binascii.Error, ValueError):
                    continue
                _append_decoded_candidate(decoded_candidates, seen_decoded, decoded)

    # Niektóre integracje przekazują Base64 opakowane drugi raz. Próba jest
    # ograniczona do jednego poziomu i nadal wymaga pełnej walidacji dokumentu.
    for decoded in tuple(decoded_candidates):
        nested = _try_decode_nested_base64(decoded)
        if nested is not None:
            _append_decoded_candidate(decoded_candidates, seen_decoded, nested)

    if _looks_like_raw_binary_payload(raw_bytes):
        _append_decoded_candidate(decoded_candidates, seen_decoded, raw_bytes)

    if not decoded_candidates:
        raise InvalidBase64Error("invalid Base64 payload")
    return decoded_candidates


def _base64_text_candidates(compact: str) -> tuple[str, ...]:
    if not compact:
        return ()

    unframed = [compact]
    # AIM/ISO 15424: identyfikator Aztec ma postać "]z" + modyfikator.
    # Niektóre skanery usuwają znak "]" albo zmieniają wielkość litery z.
    if re.match(r"^\]z[0-9A-Ca-c]", compact):
        unframed.append(compact[3:])
    elif re.match(r"^[zZ][0-9A-Ca-c]", compact):
        unframed.append(compact[2:])

    candidates: list[str] = []
    for value in unframed:
        candidates.append(value)
        last_padding = value.rfind("=")
        if last_padding >= 0 and last_padding + 1 < len(value):
            candidates.append(value[: last_padding + 1])
        # Czytniki dowodów bywają skonfigurowane z jednobajtowym sufiksem.
        if len(value) > 1:
            candidates.append(value[:-1])
    return tuple(dict.fromkeys(candidates))


def _looks_like_raw_binary_payload(value: bytes) -> bool:
    if len(value) < 5:
        return False
    expected_size = int.from_bytes(value[:4], byteorder="little", signed=False)
    return _is_valid_output_size(expected_size, _get_max_output_size())


def _append_decoded_candidate(
    candidates: list[bytes],
    seen: set[bytes],
    candidate: bytes,
) -> None:
    if candidate and candidate not in seen:
        seen.add(candidate)
        candidates.append(candidate)


def _try_decode_nested_base64(value: bytes) -> bytes | None:
    try:
        text = value.decode("ascii", errors="strict")
    except UnicodeDecodeError:
        return None
    compact = "".join(text.split())
    if len(compact) < 16 or re.fullmatch(r"[A-Za-z0-9+/]*={0,2}", compact) is None:
        return None
    if len(compact) % 4 == 1:
        return None
    try:
        return base64.b64decode(compact + "=" * (-len(compact) % 4), validate=True)
    except (binascii.Error, ValueError):
        return None
