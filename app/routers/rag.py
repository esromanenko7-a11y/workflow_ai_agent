from fastapi import APIRouter, Request

from app.schemas.rag import (
    RAGQueryRequest,
    RAGQueryResponse,
)
from app.services.rag import RAGService


router = APIRouter(
    prefix="/rag",
    tags=["RAG"],
)


@router.post(
    "/query",
    response_model=RAGQueryResponse,
)
def query_rag(
    request: Request,
    body: RAGQueryRequest,
) -> RAGQueryResponse:
    """
    Выполняет поиск по базе знаний и возвращает ответ LLM.
    """

    rag_service: RAGService = request.app.state.rag_service

    result = rag_service.answer(body.question)

    return RAGQueryResponse(**result)