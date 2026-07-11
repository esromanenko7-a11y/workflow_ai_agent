from io import BytesIO

import pytest
from fastapi import UploadFile

import app.chat.media as media_module
from app.chat.media import media_to_part


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_media_to_part_for_png_returns_image_url_part() -> None:
    file = UploadFile(
        filename="image.png",
        file=BytesIO(b"fake-png-bytes"),
        headers={
            "content-type": "image/png",
        },
    )

    part = await media_to_part(file)

    assert part["type"] == "image_url"
    assert part["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )


async def test_media_to_part_for_pdf_returns_text_part(monkeypatch) -> None:
    def fake_extract_pdf_text(data: bytes) -> str:
        assert data == b"fake-pdf-bytes"
        return "Ошибка: отсутствует обязательное поле package_id"

    monkeypatch.setattr(
        media_module,
        "extract_pdf_text",
        fake_extract_pdf_text,
    )

    file = UploadFile(
        filename="report.pdf",
        file=BytesIO(b"fake-pdf-bytes"),
        headers={
            "content-type": "application/pdf",
        },
    )

    part = await media_to_part(file)

    assert part == {
        "type": "text",
        "text": (
            "[документ PDF]:\n"
            "Ошибка: отсутствует обязательное поле package_id"
        ),
    }


async def test_media_to_part_for_unsupported_type_raises_value_error() -> None:
    file = UploadFile(
        filename="data.bin",
        file=BytesIO(b"123"),
        headers={
            "content-type": "application/octet-stream",
        },
    )

    with pytest.raises(ValueError, match="Unsupported media type"):
        await media_to_part(file)
