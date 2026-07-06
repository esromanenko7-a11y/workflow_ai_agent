from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.chat.domain import Chat, ChatMessage
from app.chat.deps import get_chat_service
from app.chat.service import ChatService


router = APIRouter(prefix="/chats", tags=["chats"])


class CreateChatIn(BaseModel):
    owner_external_id: str = Field(min_length=1)
    interface: str = Field(min_length=1)
    system_prompt: str | None = None


class CreateChatOut(BaseModel):
    chat_id: UUID


class MessageIn(BaseModel):
    content: str = Field(min_length=1)


@router.post("", response_model=CreateChatOut)
async def create_chat(
    body: CreateChatIn,
    chat_service: ChatService = Depends(get_chat_service),
) -> CreateChatOut:
    chat = await chat_service.create_chat(
        owner_external_id=body.owner_external_id,
        interface=body.interface,
        system_prompt=body.system_prompt,
    )

    return CreateChatOut(chat_id=chat.id)


@router.get("/{chat_id}", response_model=Chat)
async def get_chat(
    chat_id: UUID,
    chat_service: ChatService = Depends(get_chat_service),
) -> Chat:
    chat = await chat_service.get_chat(chat_id)

    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")

    return chat


@router.get("/{chat_id}/messages", response_model=list[ChatMessage])
async def list_messages(
    chat_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    chat_service: ChatService = Depends(get_chat_service),
) -> list[ChatMessage]:
    chat = await chat_service.get_chat(chat_id)

    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")

    return await chat_service.list_messages(chat_id, limit=limit)


@router.post("/{chat_id}/messages")
async def send_message(
    chat_id: UUID,
    body: MessageIn,
    chat_service: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    chat = await chat_service.get_chat(chat_id)

    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")

    async def event_stream() -> AsyncIterator[str]:
        async for chunk in chat_service.send_message(chat_id, body.content):
            yield f"data: {chunk}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
    )


@router.delete("/{chat_id}/messages")
async def clear_messages(
    chat_id: UUID,
    chat_service: ChatService = Depends(get_chat_service),
) -> dict[str, str]:
    chat = await chat_service.get_chat(chat_id)

    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")

    await chat_service.clear_history(chat_id)

    return {"status": "ok"}
