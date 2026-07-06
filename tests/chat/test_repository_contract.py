from uuid import uuid4

import pytest

from app.chat.domain import ChatMessage
from app.chat.repository import ChatRepository


pytestmark = pytest.mark.anyio


async def test_create_chat_and_get_it_back(repository: ChatRepository) -> None:
    chat = await repository.create_chat(
        owner_external_id="test-user-1",
        interface="cli",
        system_prompt="Ты помощник проверки пакетов данных.",
    )

    loaded_chat = await repository.get_chat(chat.id)

    assert loaded_chat is not None
    assert loaded_chat.id == chat.id
    assert loaded_chat.owner_external_id == "test-user-1"
    assert loaded_chat.interface == "cli"
    assert loaded_chat.system_prompt == "Ты помощник проверки пакетов данных."


async def test_append_message_and_list_messages_chronological(
    repository: ChatRepository,
) -> None:
    chat = await repository.create_chat(
        owner_external_id="test-user-1",
        interface="cli",
    )

    await repository.append_message(
        chat.id,
        ChatMessage(
            chat_id=chat.id,
            role="user",
            content="first",
        ),
    )
    await repository.append_message(
        chat.id,
        ChatMessage(
            chat_id=chat.id,
            role="assistant",
            content="second",
        ),
    )
    await repository.append_message(
        chat.id,
        ChatMessage(
            chat_id=chat.id,
            role="user",
            content="third",
        ),
    )

    messages = await repository.list_messages(chat.id)

    assert [message.content for message in messages] == [
        "first",
        "second",
        "third",
    ]
    assert [message.role for message in messages] == [
        "user",
        "assistant",
        "user",
    ]


async def test_list_messages_limit_returns_last_messages(
    repository: ChatRepository,
) -> None:
    chat = await repository.create_chat(
        owner_external_id="test-user-1",
        interface="cli",
    )

    for index in range(5):
        await repository.append_message(
            chat.id,
            ChatMessage(
                chat_id=chat.id,
                role="user",
                content=f"message-{index}",
            ),
        )

    messages = await repository.list_messages(chat.id, limit=2)

    assert [message.content for message in messages] == [
        "message-3",
        "message-4",
    ]


async def test_soft_delete_hides_old_messages_but_new_messages_are_visible(
    repository: ChatRepository,
) -> None:
    chat = await repository.create_chat(
        owner_external_id="test-user-1",
        interface="cli",
    )

    await repository.append_message(
        chat.id,
        ChatMessage(
            chat_id=chat.id,
            role="user",
            content="old message",
        ),
    )

    await repository.soft_delete_messages(chat.id)

    messages_after_delete = await repository.list_messages(chat.id)

    assert messages_after_delete == []

    await repository.append_message(
        chat.id,
        ChatMessage(
            chat_id=chat.id,
            role="user",
            content="new message",
        ),
    )

    messages_after_new = await repository.list_messages(chat.id)

    assert len(messages_after_new) == 1
    assert messages_after_new[0].content == "new message"


async def test_unknown_chat_returns_none_and_empty_messages(
    repository: ChatRepository,
) -> None:
    unknown_chat_id = uuid4()

    chat = await repository.get_chat(unknown_chat_id)
    messages = await repository.list_messages(unknown_chat_id)

    assert chat is None
    assert messages == []