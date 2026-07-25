from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    question: str = Field(
        min_length=1,
        description="Вопрос пользователя",
    )


class RAGSource(BaseModel):
    text: str
    source: str | None = None
    score: float


class RAGQueryResponse(BaseModel):
    answer: str
    top_score: float
    sources: list[RAGSource]