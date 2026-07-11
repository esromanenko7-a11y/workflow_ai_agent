from collections.abc import AsyncIterator
from functools import lru_cache

from fastapi import Depends
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.chat.repository import ChatRepository
from app.chat.repositories.json_repo import JsonChatRepository
from app.chat.repositories.pg_repo import PostgresChatRepository
from app.chat.service import ChatService
from app.core.config import Settings, get_settings
from app.deps.providers import get_openai


@lru_cache
def get_sessionmaker(
    database_url: str,
) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        database_url,
        pool_pre_ping=True,
    )

    return async_sessionmaker(
        engine,
        expire_on_commit=False,
    )


async def get_repository(
    settings: Settings = Depends(get_settings),
) -> AsyncIterator[ChatRepository]:
    if settings.chat_repository == "json":
        yield JsonChatRepository(base_dir=settings.chat_storage_dir)
        return

    if settings.chat_repository == "postgres":
        sessionmaker = get_sessionmaker(settings.database_url)

        async with sessionmaker() as session:
            yield PostgresChatRepository(session=session)

        return

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
