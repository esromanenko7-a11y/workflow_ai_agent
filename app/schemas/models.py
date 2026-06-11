from pydantic import BaseModel, Field


class ModelInfo(BaseModel):
    id: str = Field(description="Идентификатор модели")
    provider: str = Field(description="Провайдер модели")
    input_price_per_1m_tokens_usd: float = Field(
        description="Стоимость входных токенов за 1 млн токенов в долларах"
    )
    output_price_per_1m_tokens_usd: float = Field(
        description="Стоимость выходных токенов за 1 млн токенов в долларах"
    )
    notes: str = Field(description="Комментарий по использованию модели")


class ModelsResponse(BaseModel):
    models: list[ModelInfo]


AVAILABLE_MODELS = [
    ModelInfo(
        id="llama3.2",
        provider="Ollama",
        input_price_per_1m_tokens_usd=0.0,
        output_price_per_1m_tokens_usd=0.0,
        notes="Локальная модель. API-стоимость $0, но используются ресурсы компьютера.",
    ),
    ModelInfo(
        id="qwen2.5",
        provider="Ollama",
        input_price_per_1m_tokens_usd=0.0,
        output_price_per_1m_tokens_usd=0.0,
        notes="Локальная fallback-модель для простых ответов без tool calling.",
    ),
]