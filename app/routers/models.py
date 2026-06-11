from fastapi import APIRouter

from app.schemas.models import AVAILABLE_MODELS, ModelsResponse

router = APIRouter(tags=["models"])


@router.get(
    "/models",
    response_model=ModelsResponse,
    summary="Получить список доступных моделей",
    responses={
        200: {
            "description": "Список моделей успешно получен",
        }
    },
)
async def list_models() -> ModelsResponse:
    return ModelsResponse(models=AVAILABLE_MODELS)