from fastapi import APIRouter

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