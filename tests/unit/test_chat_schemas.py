import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatRequest, ChatResponse, Message


def test_chat_request_accepts_valid_minimal_payload() -> None:
    request = ChatRequest(
        messages=[
            Message(
                role="user",
                content="Что означает статус BLOCKED?",
            )
        ]
    )

    assert request.messages[0].role == "user"
    assert request.messages[0].content == "Что означает статус BLOCKED?"
    assert request.temperature == 0.0
    assert request.max_tokens == 1000


def test_chat_request_requires_at_least_one_message() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(messages=[])


def test_message_rejects_invalid_role() -> None:
    with pytest.raises(ValidationError):
        Message(
            role="developer",
            content="Проверь пакет данных",
        )


def test_message_rejects_empty_content() -> None:
    with pytest.raises(ValidationError):
        Message(
            role="user",
            content="",
        )


def test_chat_request_rejects_temperature_above_two() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(
            messages=[
                Message(
                    role="user",
                    content="Проверь пакет данных",
                )
            ],
            temperature=2.1,
        )


def test_chat_request_rejects_zero_max_tokens() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(
            messages=[
                Message(
                    role="user",
                    content="Проверь пакет данных",
                )
            ],
            max_tokens=0,
        )


def test_chat_response_from_openai_parses_usage_and_finish_reason(mocker) -> None:
    message = mocker.Mock()
    message.content = "Пакет заблокирован из-за критической ошибки."

    choice = mocker.Mock()
    choice.message = message
    choice.finish_reason = "stop"

    usage = mocker.Mock()
    usage.prompt_tokens = 12
    usage.completion_tokens = 7
    usage.total_tokens = 19

    response = mocker.Mock()
    response.choices = [choice]
    response.model = "llama3.2"
    response.usage = usage

    chat_response = ChatResponse.from_openai(response)

    assert chat_response.content == "Пакет заблокирован из-за критической ошибки."
    assert chat_response.model == "llama3.2"
    assert chat_response.usage.prompt_tokens == 12
    assert chat_response.usage.completion_tokens == 7
    assert chat_response.usage.total_tokens == 19
    assert chat_response.finish_reason == "stop"
    assert chat_response.cached is False


def test_chat_response_from_openai_handles_missing_usage_and_empty_content(mocker) -> None:
    message = mocker.Mock()
    message.content = None

    choice = mocker.Mock()
    choice.message = message
    choice.finish_reason = None

    response = mocker.Mock()
    response.choices = [choice]
    response.model = "llama3.2"
    response.usage = None

    chat_response = ChatResponse.from_openai(response, cached=True)

    assert chat_response.content == ""
    assert chat_response.model == "llama3.2"
    assert chat_response.usage.prompt_tokens == 0
    assert chat_response.usage.completion_tokens == 0
    assert chat_response.usage.total_tokens == 0
    assert chat_response.finish_reason is None
    assert chat_response.cached is True