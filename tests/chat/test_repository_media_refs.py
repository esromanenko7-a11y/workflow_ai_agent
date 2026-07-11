import pytest

from app.chat.domain import ChatMessage
from app.chat.repository import ChatRepository


pytestmark = pytest.mark.anyio


async def test_repository_preserves_message_media_refs(
    contract_repository: ChatRepository,
) -> None:
    chat = await contract_repository.create_chat(
        owner_external_id="media-user",
        interface="test",
        system_prompt=None,
    )

    media_refs = {
        "mime": "image/png",
        "size": 15,
        "filename": "image.png",
        "part": {
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64,ZmFrZS1wbmctYnl0ZXM=",
            },
        },
    }

    await contract_repository.append_message(
        chat.id,
        ChatMessage(
            chat_id=chat.id,
            role="user",
            content="[медиа]",
            media_refs=media_refs,
        ),
    )

    messages = await contract_repository.list_messages(chat.id)

    assert len(messages) == 1
    assert messages[0].media_refs == media_refs
