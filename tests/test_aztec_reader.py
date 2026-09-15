import io
import base64

import numpy as np
import pytest
import zxingcpp
from PIL import Image

from src.errors import AztecNotFoundError
from src.registration_decoder import decode_registration_certificate


def _synthetic_payload() -> bytes:
    fields = [""] * 66
    fields[0] = "XXC1"
    fields[7] = "POC 1234"
    fields[8] = "MARKA-TEST"
    fields[13] = "SYNTHETICVIN00003"
    utf16 = ("|".join(fields) + "|").encode("utf-16le")

    compressed = bytearray()
    for start in range(0, len(utf16), 8):
        chunk = utf16[start : start + 8]
        compressed.append(sum(1 << (7 - bit) for bit in range(len(chunk))))
        compressed.extend(chunk)
    return base64.b64encode(len(utf16).to_bytes(4, "little") + compressed)


def test_image_without_aztec_code() -> None:
    image = Image.fromarray(np.full((400, 600, 3), 245, dtype=np.uint8))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    with pytest.raises(AztecNotFoundError):
        decode_registration_certificate(buffer.getvalue())


@pytest.mark.parametrize(
    ("image_format", "save_options"),
    (("PNG", {}), ("JPEG", {"quality": 95})),
)
def test_full_pipeline_with_generated_synthetic_aztec(
    image_format: str,
    save_options: dict[str, int],
) -> None:
    barcode = zxingcpp.create_barcode(
        _synthetic_payload().decode("ascii"),
        zxingcpp.BarcodeFormat.Aztec,
    )
    image = Image.fromarray(barcode.to_image(scale=8)).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format=image_format, **save_options)

    certificate = decode_registration_certificate(buffer.getvalue())

    assert certificate.registration_number == "POC 1234"
    assert certificate.make == "MARKA-TEST"
    assert certificate.vin == "SYNTHETICVIN00003"


def test_full_pipeline_accepts_aim_framed_aztec() -> None:
    barcode = zxingcpp.create_barcode(
        "]z0" + _synthetic_payload().decode("ascii"),
        zxingcpp.BarcodeFormat.Aztec,
    )
    image = Image.fromarray(barcode.to_image(scale=8)).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    certificate = decode_registration_certificate(buffer.getvalue())

    assert certificate.registration_number == "POC 1234"
