import base64

import pytest

from src.errors import (
    DecompressionError,
    InvalidBase64Error,
    PayloadHeaderError,
    UnsupportedFormatError,
)
from src.field_mapper import map_certificate_to_vehicle
from src.registration_decoder import decode_registration_payload, parse_registration_text


def _new_format_fields() -> list[str]:
    fields = [""] * 66
    fields[0] = "XXC1"
    fields[1] = "SYN0000001"
    fields[7] = "WX 1000"
    fields[8] = "TESTMARKA"
    fields[9] = "TYP-X"
    fields[12] = "MODEL-Y"
    fields[13] = "SYNTHETICVIN00001"
    fields[39] = "1900"
    fields[41] = "1300"
    fields[48] = "1499,00"
    fields[49] = "88,00"
    fields[50] = "P"
    fields[51] = "2020-01-02"
    fields[52] = "5"
    fields[56] = "2020"
    return fields


def _literal_only_nrv2e(data: bytes, buffer_bits: int = 8) -> bytes:
    """Syntetyczny strumień: każda wartość jest literałem NRV2E."""

    encoded = bytearray()
    for start in range(0, len(data), buffer_bits):
        chunk = data[start : start + buffer_bits]
        control = sum(1 << (buffer_bits - 1 - bit) for bit in range(len(chunk)))
        encoded.extend(control.to_bytes(buffer_bits // 8, byteorder="big"))
        encoded.extend(chunk)
    return bytes(encoded)


def test_decodes_synthetic_base64_nrv2e_utf16_pipeline() -> None:
    text = "|".join(_new_format_fields()) + "|"
    utf16 = text.encode("utf-16le")
    packed = len(utf16).to_bytes(4, "little") + _literal_only_nrv2e(utf16)
    payload = base64.b64encode(packed)

    certificate = decode_registration_payload(payload)
    vehicle = map_certificate_to_vehicle(certificate)

    assert certificate.document_format == "new:XXC1"
    assert vehicle.registration_number == "WX 1000"
    assert vehicle.vin == "SYNTHETICVIN00001"
    assert vehicle.engine_capacity_cm3 == "1499,00"


def test_decodes_unpadded_base64_with_trailing_scanner_character() -> None:
    text = "|".join(_new_format_fields()) + "|"
    utf16 = text.encode("utf-16le")
    packed = len(utf16).to_bytes(4, "little") + _literal_only_nrv2e(utf16)
    payload = base64.b64encode(packed).rstrip(b"=") + b"?"

    certificate = decode_registration_payload(payload)

    assert certificate.registration_number == "WX 1000"


def test_decodes_base64_with_short_text_framing_prefix() -> None:
    text = "|".join(_new_format_fields()) + "|"
    utf16 = text.encode("utf-16le")
    packed = len(utf16).to_bytes(4, "little") + _literal_only_nrv2e(utf16)
    payload = b"Z0" + base64.b64encode(packed)

    certificate = decode_registration_payload(payload)

    assert certificate.registration_number == "WX 1000"


def test_decodes_base64_with_full_aim_aztec_prefix() -> None:
    text = "|".join(_new_format_fields()) + "|"
    utf16 = text.encode("utf-16le")
    packed = len(utf16).to_bytes(4, "little") + _literal_only_nrv2e(utf16)
    payload = b"]z0" + base64.b64encode(packed)

    certificate = decode_registration_payload(payload)

    assert certificate.registration_number == "WX 1000"


def test_rejects_undocumented_binary_header_prefix() -> None:
    text = "|".join(_new_format_fields()) + "|"
    utf16 = text.encode("utf-16le")
    packed = b"\x01\x02" + len(utf16).to_bytes(4, "little") + _literal_only_nrv2e(utf16)
    payload = base64.b64encode(packed)

    with pytest.raises(PayloadHeaderError):
        decode_registration_payload(payload)


def test_decodes_raw_binary_payload() -> None:
    text = "|".join(_new_format_fields()) + "|"
    utf16 = text.encode("utf-16le")
    packed = len(utf16).to_bytes(4, "little") + _literal_only_nrv2e(utf16)

    certificate = decode_registration_payload(packed)

    assert certificate.registration_number == "WX 1000"


def test_decodes_double_base64_wrapper() -> None:
    text = "|".join(_new_format_fields()) + "|"
    utf16 = text.encode("utf-16le")
    packed = len(utf16).to_bytes(4, "little") + _literal_only_nrv2e(utf16)
    payload = base64.b64encode(base64.b64encode(packed))

    certificate = decode_registration_payload(payload)

    assert certificate.registration_number == "WX 1000"


def test_decodes_odd_declared_output_size_like_real_document() -> None:
    text = "|".join(_new_format_fields()) + "|"
    utf16_with_terminal_byte = text.encode("utf-16le") + b"\x00"
    assert len(utf16_with_terminal_byte) % 2 == 1
    packed = (
        len(utf16_with_terminal_byte).to_bytes(4, "little")
        + _literal_only_nrv2e(utf16_with_terminal_byte)
    )

    certificate = decode_registration_payload(base64.b64encode(packed))

    assert certificate.registration_number == "WX 1000"


def test_regression_for_header_b450_s1101() -> None:
    fields = _new_format_fields()
    base_utf16 = ("|".join(fields) + "|").encode("utf-16le")
    fields[65] = "X" * ((1_100 - len(base_utf16)) // 2)
    utf16_with_terminal_byte = ("|".join(fields) + "|").encode("utf-16le") + b"\x00"
    assert len(utf16_with_terminal_byte) == 1_101

    packed = (1_101).to_bytes(4, "little") + b"\xA5" * 446
    assert len(packed) == 450

    def fake_nrv2e(compressed: bytes, expected_size: int) -> bytes:
        assert len(compressed) == 446
        assert expected_size == 1_101
        return utf16_with_terminal_byte

    certificate = decode_registration_payload(
        base64.b64encode(packed),
        decompressor=fake_nrv2e,
    )

    assert certificate.registration_number == "WX 1000"


def test_empty_document_fields_stay_empty() -> None:
    fields = _new_format_fields()
    fields[12] = ""
    fields[48] = "---"

    certificate = parse_registration_text("|".join(fields))
    vehicle = map_certificate_to_vehicle(certificate)

    assert certificate.model is None
    assert certificate.engine_capacity_cm3 is None
    assert vehicle.model == ""
    assert vehicle.engine_capacity_cm3 == ""
    assert "model" in certificate.missing_fields


def test_parses_legacy_layout_with_separate_index_map() -> None:
    fields = [""] * 46
    fields[0] = "SYN0000002"
    fields[5] = "KR 2000"
    fields[6] = "STARAMARKA"
    fields[7] = "TYP-OLD"
    fields[10] = "MODEL-OLD"
    fields[11] = "SYNTHETICVIN00002"
    fields[23] = "1800"
    fields[25] = "1200"
    fields[32] = "1199,00"
    fields[33] = "55,00"
    fields[34] = "D"
    fields[36] = "2008-03-04"
    fields[37] = "5"
    fields[41] = "2008"

    certificate = parse_registration_text("|".join(fields))

    assert certificate.document_format == "old"
    assert certificate.registration_number == "KR 2000"
    assert certificate.vehicle_type == "TYP-OLD"
    assert certificate.production_year == "2008"


def test_rejects_invalid_base64() -> None:
    with pytest.raises(InvalidBase64Error):
        decode_registration_payload("to-nie-jest%%%base64")


def test_rejects_unsupported_document_format() -> None:
    with pytest.raises(UnsupportedFormatError):
        parse_registration_text("XXZ9|nieznany|format")


def test_decompression_diagnostic_code_contains_no_payload() -> None:
    error = DecompressionError("invalid NRV2E back-reference")

    assert error.diagnostic_code == "NRV-04"
