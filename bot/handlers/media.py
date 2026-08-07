from io import BytesIO

import httpx
from aiogram import F, Router
from aiogram.types import Document, Message

from bot.handlers.common import backend_error_text, get_user_chat_id
from bot.keyboards.feedback import feedback_kb
from bot.services.backend_client import BackendClient
from bot.web import stream_to_chat


router = Router()

MAX_PHOTO_SIZE_BYTES = 2 * 1024 * 1024
MAX_DOCUMENT_SIZE_BYTES = 10 * 1024 * 1024

SUPPORTED_DOCUMENT_EXTENSIONS = (".pdf", ".docx")


async def _download_telegram_file(
    message: Message,
    file_id: str,
) -> bytes:
    telegram_file = await message.bot.get_file(file_id)

    destination = BytesIO()

    await message.bot.download_file(
        file_path=telegram_file.file_path,
        destination=destination,
    )

    return destination.getvalue()


async def _send_media_to_backend(
    message: Message,
    backend: BackendClient,
    content: str,
    media: bytes,
    mime: str,
) -> None:
    chat_id = await get_user_chat_id(
        message=message,
        backend=backend,
    )

    tokens = backend.send_message(
        chat_id=chat_id,
        content=content,
        media=media,
        mime=mime,
    )

    result = await stream_to_chat(
        message=message,
        tokens=tokens,
    )

    if result.backend_message_id:
        await message.answer(
            "Оцените ответ:",
            reply_markup=feedback_kb(result.backend_message_id),
        )


def _document_mime(document: Document) -> str:
    filename = (document.file_name or "").lower()

    if filename.endswith(".pdf"):
        return "application/pdf"

    if filename.endswith(".docx"):
        return (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        )

    return document.mime_type or "application/octet-stream"


@router.message(F.photo)
async def handle_photo(
    message: Message,
    backend: BackendClient,
) -> None:
    try:
        photos = message.photo or []

        suitable_photos = [
            photo
            for photo in photos
            if (photo.file_size or 0) <= MAX_PHOTO_SIZE_BYTES
        ]

        if not suitable_photos:
            await message.answer(
                "Фото слишком большое. Пришлите изображение до 2 МБ.",
            )
            return

        photo = max(
            suitable_photos,
            key=lambda item: item.file_size or 0,
        )

        media = await _download_telegram_file(
            message=message,
            file_id=photo.file_id,
        )

        content = message.caption or "[фото]"

        await _send_media_to_backend(
            message=message,
            backend=backend,
            content=content,
            media=media,
            mime="image/jpeg",
        )

    except (
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.HTTPStatusError,
    ) as error:
        await message.answer(backend_error_text(error))


@router.message(F.voice)
async def handle_voice(
    message: Message,
    backend: BackendClient,
) -> None:
    try:
        if message.voice is None:
            return

        media = await _download_telegram_file(
            message=message,
            file_id=message.voice.file_id,
        )

        await _send_media_to_backend(
            message=message,
            backend=backend,
            content="[голосовое сообщение]",
            media=media,
            mime=message.voice.mime_type or "audio/ogg",
        )

    except (
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.HTTPStatusError,
    ) as error:
        await message.answer(backend_error_text(error))


@router.message(F.document)
async def handle_document(
    message: Message,
    backend: BackendClient,
) -> None:
    try:
        document = message.document

        if document is None:
            return

        filename = document.file_name or ""
        filename_lower = filename.lower()

        if not filename_lower.endswith(SUPPORTED_DOCUMENT_EXTENSIONS):
            await message.answer(
                "Поддерживаются только PDF и DOCX документы.",
            )
            return

        if (
            document.file_size is not None
            and document.file_size > MAX_DOCUMENT_SIZE_BYTES
        ):
            await message.answer(
                "Документ слишком большой. Пришлите файл до 10 МБ.",
            )
            return

        media = await _download_telegram_file(
            message=message,
            file_id=document.file_id,
        )

        content = message.caption or f"[документ: {filename}]"

        await _send_media_to_backend(
            message=message,
            backend=backend,
            content=content,
            media=media,
            mime=_document_mime(document),
        )

    except (
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.HTTPStatusError,
    ) as error:
        await message.answer(backend_error_text(error))
