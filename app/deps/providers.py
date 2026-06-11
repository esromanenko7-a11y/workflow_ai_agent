from typing import Annotated

from fastapi import Depends, Request
from openai import AsyncOpenAI
from redis.asyncio import Redis

from app.core.config import Settings, get_settings
from app.services.llm import LLMService


def get_openai(request: Request) -> AsyncOpenAI:
    return request.app.state.openai_client


def get_cache(request: Request) -> Redis | None:
    return getattr(request.app.state, "cache", None)


SettingsDep = Annotated[Settings, Depends(get_settings)]
OpenAIDep = Annotated[AsyncOpenAI, Depends(get_openai)]
CacheDep = Annotated[Redis | None, Depends(get_cache)]


def get_llm_service(
    settings: SettingsDep,
    openai_client: OpenAIDep,
    cache: CacheDep,
) -> LLMService:
    return LLMService(
        openai_client=openai_client,
        cache=cache,
        settings=settings,
    )


LLMServiceDep = Annotated[LLMService, Depends(get_llm_service)]