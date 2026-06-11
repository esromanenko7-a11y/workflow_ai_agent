import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.deps.providers import CacheDep

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Проверить, что FastAPI-сервис запущен",
    responses={
        200: {
            "description": "Сервис доступен",
            "content": {
                "application/json": {
                    "example": {"status": "ok"}
                }
            },
        }
    },
)
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/ready",
    summary="Проверить готовность сервиса к обработке запросов",
    responses={
        200: {
            "description": "Сервис готов принимать запросы",
            "content": {
                "application/json": {
                    "example": {"status": "ok", "redis": "up"}
                }
            },
        },
        503: {
            "description": "Сервис работает в деградированном режиме",
            "content": {
                "application/json": {
                    "example": {"status": "degraded", "redis": "down"}
                }
            },
        },
    },
)
async def readiness_check(cache: CacheDep):
    if cache is None:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "redis": "down"},
        )

    try:
        async with asyncio.timeout(2):
            await cache.ping()
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "redis": "down"},
        )

    return {"status": "ok", "redis": "up"}