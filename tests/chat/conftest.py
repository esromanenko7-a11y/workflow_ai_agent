import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.chat.repositories.json_repo import JsonChatRepository
from app.chat.repositories.pg_repo import PostgresChatRepository
from app.core.config import get_settings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def repository(tmp_path):
    """
    Обычный JSON-репозиторий для service-тестов.

    Эти тесты проверяют ChatService, а не конкретную БД,
    поэтому оставляем быстрый JSON-вариант.
    """
    return JsonChatRepository(base_dir=tmp_path / "chat-storage")


@pytest.fixture(params=["json", "postgres"])
async def contract_repository(request, tmp_path):
    """
    Репозиторий для contract-тестов.

    Один и тот же набор тестов проверяет две реализации:
    - JsonChatRepository;
    - PostgresChatRepository.
    """
    if request.param == "json":
        yield JsonChatRepository(base_dir=tmp_path / "chat-storage")
        return

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with sessionmaker() as session:
            yield PostgresChatRepository(session=session)
    finally:
        await engine.dispose()
