import hashlib
import json
from collections.abc import AsyncIterator
from typing import Any
import structlog
import time

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
from app.observability.pii import prompt_hash, redact_pii

from app.schemas.chat import ChatDelta, ChatRequest, ChatResponse, Usage

logger = structlog.get_logger("llm-service")

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

    def _build_prompt_text(self, req: ChatRequest) -> str:
        """
        Собирает текст prompt для безопасного логирования.

        Сырой prompt в лог не пишем. Этот текст нужен только для:
        - prompt_hash;
        - prompt_preview после PII-маскирования.
        """
        return "\n".join(
            f"{message.role}: {message.content}"
            for message in req.messages
        )

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
            logger.info(
                "llm_cache_hit",
                model=cached_response.model,
                input_tokens=cached_response.usage.prompt_tokens,
                output_tokens=cached_response.usage.completion_tokens,
                finish_reason=cached_response.finish_reason,
            )
            return cached_response

        model = self._get_model(req)
        raw_prompt = self._build_prompt_text(req)
        started_at = time.perf_counter()

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

        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)

        chat_response = ChatResponse.from_openai(response, cached=False)

        logger.info(
            "llm_request_completed",
            model=chat_response.model,
            input_tokens=chat_response.usage.prompt_tokens,
            output_tokens=chat_response.usage.completion_tokens,
            total_tokens=chat_response.usage.total_tokens,
            latency_ms=latency_ms,
            finish_reason=chat_response.finish_reason,
            prompt_hash=prompt_hash(raw_prompt),
            prompt_preview=redact_pii(raw_prompt)[:120],
        )

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