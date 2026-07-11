from uuid import UUID

from fastapi.testclient import TestClient

from app.admin.deps import require_admin
from app.chat.deps import get_repository
from app.main import app


class FakeAdminRepository:
    async def get_admin_stats(self) -> dict:
        return {
            "total_messages": 12,
            "active_users": 3,
            "avg_latency_ms": None,
            "moderation_block_rate": 0.0,
            "feedback_up_ratio": 0.75,
            "top_questions": [],
        }

    async def list_admin_users(
        self,
        limit: int = 50,
    ) -> list[dict]:
        return [
            {
                "owner_external_id": "telegram:123",
                "interface": "telegram",
                "chats_count": 2,
                "last_seen_at": None,
            }
        ][:limit]

    async def enqueue_broadcast(
        self,
        message: str,
        interface_filter: str,
    ) -> UUID:
        assert message == "Hello admins"
        assert interface_filter == "telegram"
        return UUID("77777777-7777-7777-7777-777777777777")


def test_admin_stats_requires_token() -> None:
    client = TestClient(app)

    response = client.get("/chats/admin/stats")

    assert response.status_code == 401


def test_admin_stats_returns_data() -> None:
    fake_repository = FakeAdminRepository()

    app.dependency_overrides[require_admin] = lambda: None
    app.dependency_overrides[get_repository] = lambda: fake_repository

    try:
        client = TestClient(app)

        response = client.get("/chats/admin/stats")

        assert response.status_code == 200
        assert response.json() == {
            "total_messages": 12,
            "active_users": 3,
            "avg_latency_ms": None,
            "moderation_block_rate": 0.0,
            "feedback_up_ratio": 0.75,
            "top_questions": [],
        }
    finally:
        app.dependency_overrides.clear()


def test_admin_users_returns_data() -> None:
    fake_repository = FakeAdminRepository()

    app.dependency_overrides[require_admin] = lambda: None
    app.dependency_overrides[get_repository] = lambda: fake_repository

    try:
        client = TestClient(app)

        response = client.get("/chats/admin/users?limit=10")

        assert response.status_code == 200
        assert response.json() == {
            "users": [
                {
                    "owner_external_id": "telegram:123",
                    "interface": "telegram",
                    "chats_count": 2,
                    "last_seen_at": None,
                }
            ]
        }
    finally:
        app.dependency_overrides.clear()


def test_admin_broadcast_enqueues_message() -> None:
    fake_repository = FakeAdminRepository()

    app.dependency_overrides[require_admin] = lambda: None
    app.dependency_overrides[get_repository] = lambda: fake_repository

    try:
        client = TestClient(app)

        response = client.post(
            "/chats/admin/broadcast",
            json={
                "message": "Hello admins",
                "interface_filter": "telegram",
            },
        )

        assert response.status_code == 200
        assert response.json() == {
            "status": "queued",
            "broadcast_id": "77777777-7777-7777-7777-777777777777",
        }
    finally:
        app.dependency_overrides.clear()
