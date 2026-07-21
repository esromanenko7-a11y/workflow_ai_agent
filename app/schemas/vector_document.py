from typing import Literal

from pydantic import BaseModel, Field


ChunkType = Literal[
    "description",
    "summary",
    "objective",
    "requirements",
    "notes",
]


class VectorDocument(BaseModel):
    """
    Один смысловой фрагмент базы знаний.

    Эта модель описывает payload, который будет храниться
    вместе с вектором в Qdrant.
    """

    source: str = Field(
        min_length=1,
        description="Источник документа",
    )

    check_code: str = Field(
        min_length=1,
        description="Стабильный код проверки",
    )

    check_name: str = Field(
        min_length=1,
        description="Название проверки для пользователя",
    )

    category: str = Field(
        min_length=1,
        description="Категория проверки",
    )

    severity: str = Field(
        min_length=1,
        description="Уровень критичности",
    )

    chunk_type: ChunkType = Field(
        description="Тип смыслового фрагмента",
    )

    text: str = Field(
        min_length=1,
        description="Текст для семантического поиска",
    )