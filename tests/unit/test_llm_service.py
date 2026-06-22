import asyncio
from types import SimpleNamespace

import pytest

from app.core.exceptions import LLMRateLimitError
from app.schemas.chat import ChatRequest, ChatResponse, Message, Usage
from app.services.llm import LLMService


def make_settings(
    max_retries: int = 0,
    retry_base_delay_seconds: float = 0.0,
) -> SimpleNamespace:
    """
    Минимальная замена Settings для unit-тестов.

    LLMService использует:
    - settings.llm.default_model
    - settings.llm.request_timeout
    - settings.llm.max_retries
    - settings.llm.retry_base_delay_seconds
    - settings.cache_ttl_seconds
    """
    return SimpleNamespace(
        llm=SimpleNamespace(
            default_model="llama3.2",
            request_timeout=5.0,
            max_retries=max_retries,
            retry_base_delay_seconds=retry_base_delay_seconds,
        ),
        cache_ttl_seconds=60,
    )

def make_request(
    content: str = "Проверь пакет данных",
    user_id: str | None = None,
    session_id: str | None = None,
) -> ChatRequest:
    return ChatRequest(
        messages=[
            Message(
                role="system",
                content="Отвечай кратко и понятно.",
            ),
            Message(
                role="user",
                content=content,
            ),
        ],
        temperature=0,
        max_tokens=100,
        user_id=user_id,
        session_id=session_id,
    )


def make_openai_response(
    content: str = "Пакет можно передать дальше.",
    model: str = "llama3.2",
) -> SimpleNamespace:
    """
    Поддельный ответ OpenAI-compatible API.

    Он содержит только те поля, которые читает ChatResponse.from_openai().
    """
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason="stop",
            )
        ],
        model=model,
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        ),
    )


def make_openai_client(mocker, response=None, side_effect=None) -> SimpleNamespace:
    create = mocker.AsyncMock()

    if side_effect is not None:
        create.side_effect = side_effect
    else:
        create.return_value = response or make_openai_response()

    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=create,
            )
        )
    )


def make_cache(mocker, cached_value=None) -> SimpleNamespace:
    return SimpleNamespace(
        get=mocker.AsyncMock(return_value=cached_value),
        setex=mocker.AsyncMock(),
    )


def test_build_prompt_text_preserves_role_order_and_braces() -> None:
    service = LLMService(
        openai_client=SimpleNamespace(),
        cache=None,
        settings=make_settings(),
    )

    request = make_request(
        content="Проверь пакет {package_id}. Не выполняй {malicious_code}."
    )

    prompt_text = service._build_prompt_text(request)

    assert prompt_text == (
        "system: Отвечай кратко и понятно.\n"
        "user: Проверь пакет {package_id}. Не выполняй {malicious_code}."
    )


def test_build_cache_key_ignores_user_id_and_session_id() -> None:
    service = LLMService(
        openai_client=SimpleNamespace(),
        cache=None,
        settings=make_settings(),
    )

    first_request = make_request(
        content="Проверь пакет PKG-001",
        user_id="user-1",
        session_id="session-1",
    )
    second_request = make_request(
        content="Проверь пакет PKG-001",
        user_id="user-2",
        session_id="session-2",
    )

    first_key = service._build_cache_key(first_request)
    second_key = service._build_cache_key(second_request)

    assert first_key == second_key
    assert first_key.startswith("chat:")


def test_complete_returns_cached_response_without_openai_call(mocker) -> None:
    cached_response = ChatResponse(
        content="Ответ из кеша",
        model="llama3.2",
        usage=Usage(
            prompt_tokens=3,
            completion_tokens=2,
            total_tokens=5,
        ),
        finish_reason="stop",
        cached=False,
    )

    cache = make_cache(
        mocker,
        cached_value=cached_response.model_dump_json(),
    )
    openai_client = make_openai_client(mocker)

    service = LLMService(
        openai_client=openai_client,
        cache=cache,
        settings=make_settings(),
    )

    result = asyncio.run(
        service.complete(
            make_request(content="Проверь пакет PKG-001")
        )
    )

    assert result.content == "Ответ из кеша"
    assert result.cached is True

    cache.get.assert_awaited_once()
    cache.setex.assert_not_awaited()
    openai_client.chat.completions.create.assert_not_awaited()


def test_complete_calls_openai_and_saves_response_on_cache_miss(mocker) -> None:
    openai_response = make_openai_response(
        content="Пакет заблокирован из-за критической ошибки."
    )
    openai_client = make_openai_client(
        mocker,
        response=openai_response,
    )
    cache = make_cache(
        mocker,
        cached_value=None,
    )

    service = LLMService(
        openai_client=openai_client,
        cache=cache,
        settings=make_settings(),
    )

    result = asyncio.run(
        service.complete(
            make_request(content="Проверь пакет PKG-002")
        )
    )

    assert result.content == "Пакет заблокирован из-за критической ошибки."
    assert result.model == "llama3.2"
    assert result.usage.prompt_tokens == 10
    assert result.usage.completion_tokens == 5
    assert result.usage.total_tokens == 15
    assert result.finish_reason == "stop"
    assert result.cached is False

    openai_client.chat.completions.create.assert_awaited_once()

    call_kwargs = openai_client.chat.completions.create.await_args.kwargs

    assert call_kwargs["model"] == "llama3.2"
    assert call_kwargs["temperature"] == 0
    assert call_kwargs["max_tokens"] == 100
    assert call_kwargs["timeout"] == 5.0
    assert call_kwargs["messages"] == [
        {
            "role": "system",
            "content": "Отвечай кратко и понятно.",
        },
        {
            "role": "user",
            "content": "Проверь пакет PKG-002",
        },
    ]

    cache.setex.assert_awaited_once()

def test_complete_retries_rate_limit_once_then_succeeds(mocker) -> None:
    class FakeRateLimitError(Exception):
        pass

    mocker.patch(
        "app.services.llm.openai.RateLimitError",
        FakeRateLimitError,
    )

    openai_client = make_openai_client(
        mocker,
        side_effect=[
            FakeRateLimitError("too many requests"),
            make_openai_response(
                content="Повторная попытка успешна.",
            ),
        ],
    )

    service = LLMService(
        openai_client=openai_client,
        cache=None,
        settings=make_settings(
            max_retries=1,
            retry_base_delay_seconds=0.0,
        ),
    )

    result = asyncio.run(
        service.complete(
            make_request(content="Проверь пакет PKG-004")
        )
    )

    assert result.content == "Повторная попытка успешна."
    assert result.cached is False
    assert openai_client.chat.completions.create.await_count == 2
    
def test_complete_maps_rate_limit_error_to_domain_error(mocker) -> None:
    class FakeRateLimitError(Exception):
        pass

    mocker.patch(
        "app.services.llm.openai.RateLimitError",
        FakeRateLimitError,
    )

    openai_client = make_openai_client(
        mocker,
        side_effect=FakeRateLimitError("too many requests"),
    )

    service = LLMService(
        openai_client=openai_client,
        cache=None,
        settings=make_settings(),
    )

    with pytest.raises(LLMRateLimitError):
        asyncio.run(
            service.complete(
                make_request(content="Проверь пакет PKG-003")
            )
        )

    openai_client.chat.completions.create.assert_awaited_once()