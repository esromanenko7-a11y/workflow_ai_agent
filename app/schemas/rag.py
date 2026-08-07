from pydantic import BaseModel, Field


class RAGQueryRequest(BaseModel):
    question: str = Field(
        min_length=1,
        description="Вопрос пользователя",
    )


class RAGSource(BaseModel):
    id: str
    file_name: str | None = None
    page: str | int | None = None
    score: float
    snippet: str


class RAGQueryResponse(BaseModel):
    answer: str
    top_score: float
    confident: bool
    sources: list[RAGSource]