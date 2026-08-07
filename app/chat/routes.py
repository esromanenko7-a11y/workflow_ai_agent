import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.chat.deps import get_chat_service
from app.chat.domain import Chat, ChatMessage
from app.chat.feedback import FeedbackIn, FeedbackOut
from app.chat.media import media_to_part
from app.chat.service import ChatService


router = APIRouter(
    prefix="/chats",
    tags=["chats"],
)


class CreateChatIn(BaseModel):
    owner_external_id: str = Field(min_length=1)
    interface: str = Field(min_length=1)
    system_prompt: str | None = None


class CreateChatOut(BaseModel):
    chat_id: UUID


@router.post("")
async def create_chat(
    payload: CreateChatIn,
    chat_service: ChatService = Depends(get_chat_service),
) -> CreateChatOut:
    chat = await chat_service.create_chat(
        owner_external_id=payload.owner_external_id,
        interface=payload.interface,
        system_prompt=payload.system_prompt,
    )

    return CreateChatOut(chat_id=chat.id)


@router.get("/{chat_id}")
async def get_chat(
    chat_id: UUID,
    chat_service: ChatService = Depends(get_chat_service),
) -> Chat:
    chat = await chat_service.get_chat(chat_id)

    if chat is None:
        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    return chat


@router.get("/{chat_id}/messages")
async def list_messages(
    chat_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    chat_service: ChatService = Depends(get_chat_service),
) -> list[ChatMessage]:
    chat = await chat_service.get_chat(chat_id)

    if chat is None:
        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    return await chat_service.list_messages(
        chat_id=chat_id,
        limit=limit,
    )


@router.post("/{chat_id}/messages")
async def send_message(
    chat_id: UUID,
    request: Request,
    content: str = Form(...),
    media: UploadFile | None = File(default=None),
    chat_service: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    chat = await chat_service.get_chat(chat_id)

    if chat is None:
        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    media_refs = None

    if media is not None:
        try:
            media_part = await media_to_part(media)
        except ValueError as error:
            raise HTTPException(
                status_code=415,
                detail=str(error),
            ) from error

        media_refs = {
            "mime": media.content_type,
            "size": media.size,
            "filename": media.filename,
            "part": media_part,
        }

    chat_service.check_input_moderation(content)

    async def event_stream():
        rag_service = getattr(request.app.state, "rag_service", None)

        async for event in chat_service.send_message(
                chat_id=chat_id,
                user_content=content,
                media_refs=media_refs,
                rag_service=rag_service,
        ):
            payload = json.dumps(event, ensure_ascii=False)

            if event.get("type") == "sources":
                yield f"event: sources\ndata: {payload}\n\n"
                continue

            yield f"data: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
    )


@router.post(
    "/{chat_id}/messages/{message_id}/feedback",
)
async def save_message_feedback(
    chat_id: UUID,
    message_id: UUID,
    payload: FeedbackIn,
    owner_external_id: str = Query(..., min_length=1),
    chat_service: ChatService = Depends(get_chat_service),
) -> FeedbackOut:
    try:
        await chat_service.save_feedback(
            chat_id=chat_id,
            message_id=message_id,
            owner_external_id=owner_external_id,
            value=payload.value,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    return FeedbackOut()


@router.delete("/{chat_id}/messages")
async def clear_messages(
    chat_id: UUID,
    chat_service: ChatService = Depends(get_chat_service),
) -> dict[str, str]:
    chat = await chat_service.get_chat(chat_id)

    if chat is None:
        raise HTTPException(
            status_code=404,
            detail="Chat not found",
        )

    await chat_service.clear_history(chat_id)

    return {
        "status": "ok",
    }
