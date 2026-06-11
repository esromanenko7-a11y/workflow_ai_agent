from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.deps.providers import LLMServiceDep
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Получить обычный LLM-ответ",
    responses={
        200: {"description": "Ответ успешно получен"},
        422: {"description": "Ошибка валидации входного запроса"},
        429: {"description": "Превышен лимит запросов к LLM-провайдеру"},
        502: {"description": "Ошибка LLM-провайдера"},
        504: {"description": "Timeout LLM-провайдера"},
    },
)
async def chat(
    request: ChatRequest,
    llm_service: LLMServiceDep,
) -> ChatResponse:
    return await llm_service.complete(request)


@router.post(
    "/chat/stream",
    summary="Получить streaming LLM-ответ через SSE",
    responses={
        200: {
            "description": "Streaming-ответ успешно начат",
            "content": {
                "text/event-stream": {
                    "example": "data: Привет\n\ndata: [DONE]\n\n"
                }
            },
        },
        422: {"description": "Ошибка валидации входного запроса"},
        429: {"description": "Превышен лимит запросов к LLM-провайдеру"},
        502: {"description": "Ошибка LLM-провайдера"},
        504: {"description": "Timeout LLM-провайдера"},
    },
)
async def chat_stream(
    request: ChatRequest,
    llm_service: LLMServiceDep,
) -> StreamingResponse:
    async def event_generator() -> AsyncIterator[str]:
        async for delta in llm_service.stream(request):
            if delta.content is not None:
                yield f"data: {delta.content}\n\n"

            if delta.usage is not None:
                yield f"data: {delta.model_dump_json(exclude_none=True)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
        },
    )