from fastapi import Depends
from openai import AsyncOpenAI

from app.chat.repository import ChatRepository
from app.chat.repositories.json_repo import JsonChatRepository
from app.chat.service import ChatService
from app.core.config import Settings, get_settings
from app.deps.providers import get_openai


def get_repository(
    settings: Settings = Depends(get_settings),
) -> ChatRepository:
    if settings.chat_repository == "json":
        return JsonChatRepository(base_dir=settings.chat_storage_dir)

    if settings.chat_repository == "postgres":
        raise NotImplementedError(
            "CHAT_REPOSITORY=postgres will be implemented in the Postgres step"
        )

    raise ValueError(
        "Unknown CHAT_REPOSITORY. Expected one of: json, postgres"
    )


def get_chat_service(
    repository: ChatRepository = Depends(get_repository),
    openai_client: AsyncOpenAI = Depends(get_openai),
    settings: Settings = Depends(get_settings),
) -> ChatService:
    return ChatService(
        repository=repository,
        llm_client=openai_client,
        default_model=settings.llm.default_model,
        context_window=settings.chat_context_window,
    )
