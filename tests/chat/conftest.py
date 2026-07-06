import pytest

from app.chat.repositories.json_repo import JsonChatRepository


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def repository(tmp_path):
    return JsonChatRepository(base_dir=tmp_path / "chat-storage")