from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile

from app.chat.media import media_to_part


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def test_media_to_part_for_audio_uses_whisper_stub() -> None:
    create_transcription = AsyncMock(
        return_value=SimpleNamespace(
            text="Пользователь сказал: проверь пакет данных",
        )
    )

    fake_client = SimpleNamespace(
        audio=SimpleNamespace(
            transcriptions=SimpleNamespace(
                create=create_transcription,
            )
        )
    )

    file = UploadFile(
        filename="voice.ogg",
        file=BytesIO(b"fake-ogg-bytes"),
        headers={
            "content-type": "audio/ogg",
        },
    )

    part = await media_to_part(
        media=file,
        client=fake_client,
    )

    assert part == {
        "type": "text",
        "text": (
            "[пользователь сказал голосом]:\n"
            "Пользователь сказал: проверь пакет данных"
        ),
    }

    create_transcription.assert_awaited_once()

    kwargs = create_transcription.await_args.kwargs

    assert kwargs["model"] == "whisper-1"
    assert kwargs["file"].name == "voice.ogg"
