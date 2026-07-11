from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.admin.deps import require_admin
from app.admin.schemas import (
    AdminUsersOut,
    BroadcastIn,
    BroadcastOut,
    StatsOut,
)
from app.chat.deps import get_repository
from app.chat.repository import ChatRepository


router = APIRouter(
    prefix="/chats/admin",
    tags=["admin"],
)


@router.get(
    "/stats",
    response_model=StatsOut,
)
async def get_admin_stats(
    _: None = Depends(require_admin),
    repository: ChatRepository = Depends(get_repository),
) -> StatsOut:
    stats = await repository.get_admin_stats()
    return StatsOut(**stats)


@router.get(
    "/users",
    response_model=AdminUsersOut,
)
async def get_admin_users(
    limit: int = Query(default=50, ge=1, le=100),
    _: None = Depends(require_admin),
    repository: ChatRepository = Depends(get_repository),
) -> AdminUsersOut:
    users = await repository.list_admin_users(limit=limit)
    return AdminUsersOut(users=users)


@router.get(
    "/broadcasts/pending",
)
async def list_pending_broadcasts(
    interface_filter: str = Query(default="telegram"),
    limit: int = Query(default=10, ge=1, le=50),
    _: None = Depends(require_admin),
    repository: ChatRepository = Depends(get_repository),
) -> dict:
    broadcasts = await repository.list_pending_broadcasts(
        interface_filter=interface_filter,
        limit=limit,
    )

    return {
        "broadcasts": broadcasts,
    }


@router.post(
    "/broadcasts/{broadcast_id}/sent",
)
async def mark_broadcast_sent(
    broadcast_id: UUID,
    _: None = Depends(require_admin),
    repository: ChatRepository = Depends(get_repository),
) -> dict:
    await repository.mark_broadcast_sent(
        broadcast_id=broadcast_id,
    )

    return {
        "status": "ok",
    }


@router.post(
    "/broadcast",
    response_model=BroadcastOut,
)
async def create_broadcast(
    payload: BroadcastIn,
    _: None = Depends(require_admin),
    repository: ChatRepository = Depends(get_repository),
) -> BroadcastOut:
    broadcast_id = await repository.enqueue_broadcast(
        message=payload.message,
        interface_filter=payload.interface_filter,
    )

    return BroadcastOut(
        broadcast_id=broadcast_id,
    )
