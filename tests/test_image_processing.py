import io

import pytest
from PIL import Image

from src.errors import InvalidImageError, ImageTooSmallError
from src.image_processing import load_image


def test_rejects_non_image_bytes() -> None:
    with pytest.raises(InvalidImageError):
        load_image(b"not an image")


def test_rejects_tiny_image() -> None:
    image = Image.new("RGB", (50, 50), "white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    with pytest.raises(ImageTooSmallError):
        load_image(buffer.getvalue())

