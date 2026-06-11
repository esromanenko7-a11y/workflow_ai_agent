import hashlib
import json
from collections.abc import AsyncIterator
from typing import Any

import openai
from openai import AsyncOpenAI
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.exceptions import (
    LLMAuthError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.schemas.chat import ChatDelta, ChatRequest, ChatResponse, Usage


class LLMService:
    def __init__(
        self,
        openai_client: AsyncOpenAI,
        cache: Redis | None,
        settings: Settings,
    ) -> None:
        self.openai = openai_client
        self.cache = cache
        self.settings = settings

    def _get_model(self, req: ChatRequest) -> str:
        return req.model or self.settings.llm.default_model

    def _build_cache_key(self, req: ChatRequest) -> str:
        payload = req.model_dump(
            mode="json",
            exclude={"user_id", "session_id"},
            exclude_none=True,
        )
        payload["model"] = self._get_model(req)

        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        return f"chat:{digest}"

    async def _get_cached_response(self, cache_key: str) -> ChatResponse | None:
        if self.cache is None:
            return None

        try:
            cached_value = await self.cache.get(cache_key)
        except Exception:
            return None

        if not cached_value:
            return None

        if isinstance(cached_value, bytes):
            cached_value = cached_value.decode("utf-8")

        response = ChatResponse.model_validate_json(cached_value)
        response.cached = True
        return response

    async def _save_to_cache(self, cache_key: str, response: ChatResponse) -> None:
        if self.cache is None:
            return

        try:
            await self.cache.setex(
                cache_key,
                self.settings.cache_ttl_seconds,
                response.model_dump_json(),
            )
        except Exception:
            return

    async def complete(self, req: ChatRequest) -> ChatResponse:
        cache_key = self._build_cache_key(req)
        cached_response = await self._get_cached_response(cache_key)

        if cached_response is not None:
            return cached_response

        model = self._get_model(req)

        try:
            response = await self.openai.chat.completions.create(
                model=model,
                messages=[message.model_dump() for message in req.messages],
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                timeout=self.settings.llm.request_timeout,
            )
        except openai.RateLimitError as exc:
            raise LLMRateLimitError() from exc
        except openai.APITimeoutError as exc:
            raise LLMTimeoutError() from exc
        except openai.AuthenticationError as exc:
            raise LLMAuthError() from exc
        except Exception as exc:
            raise LLMError(str(exc)) from exc

        chat_response = ChatResponse.from_openai(response, cached=False)
        await self._save_to_cache(cache_key, chat_response)

        return chat_response

    async def stream(self, req: ChatRequest) -> AsyncIterator[ChatDelta]:
        model = self._get_model(req)

        try:
            stream = await self.openai.chat.completions.create(
                model=model,
                messages=[message.model_dump() for message in req.messages],
                temperature=req.temperature,
                max_tokens=req.max_tokens,
                timeout=self.settings.llm.request_timeout,
                stream=True,
                stream_options={"include_usage": True},
            )

            async for chunk in stream:
                if getattr(chunk, "usage", None) is not None:
                    usage = Usage(
                        prompt_tokens=getattr(chunk.usage, "prompt_tokens", 0),
                        completion_tokens=getattr(chunk.usage, "completion_tokens", 0),
                        total_tokens=getattr(chunk.usage, "total_tokens", 0),
                    )
                    yield ChatDelta(usage=usage)
                    continue

                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)

                if content:
                    yield ChatDelta(content=content)

        except openai.RateLimitError as exc:
            raise LLMRateLimitError() from exc
        except openai.APITimeoutError as exc:
            raise LLMTimeoutError() from exc
        except openai.AuthenticationError as exc:
            raise LLMAuthError() from exc
        except Exception as exc:
            raise LLMError(str(exc)) from exc