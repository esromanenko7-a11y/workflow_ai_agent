from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


class LLMSettings(BaseSettings):
    openai_api_key: SecretStr = Field(
        validation_alias="OPENAI_API_KEY",
    )

    openai_base_url: str = Field(
        default="http://localhost:11434/v1",
        validation_alias="OPENAI_BASE_URL",
    )

    ollama_base_url: str = Field(
        default="http://localhost:11434",
        validation_alias="OLLAMA_BASE_URL",
    )

    default_model: str = Field(
        default="llama3.2:latest",
        validation_alias="DEFAULT_MODEL",
    )

    request_timeout: float = Field(
        default=120.0,
        gt=0,
        validation_alias="REQUEST_TIMEOUT",
    )

    max_retries: int = Field(
        default=2,
        ge=0,
        le=10,
        validation_alias="LLM_MAX_RETRIES",
    )

    retry_base_delay_seconds: float = Field(
        default=0.5,
        ge=0,
        validation_alias="LLM_RETRY_BASE_DELAY_SECONDS",
    )

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


class Settings(BaseSettings):
    llm: LLMSettings = Field(default_factory=LLMSettings)

    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias="REDIS_URL",
    )
    database_url: str = Field(
        default="postgresql+asyncpg://app:app@localhost:5432/app",
        validation_alias="DATABASE_URL",
    )
    cache_ttl_seconds: int = Field(
        default=3600,
        validation_alias="CACHE_TTL_SECONDS",
    )
    qdrant_url: str = Field(
        default="http://localhost:6333",
        validation_alias="QDRANT_URL",
    )
    qdrant_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="QDRANT_API_KEY",
    )
    qdrant_collection: str = Field(
        default="documents",
        validation_alias="QDRANT_COLLECTION",
    )
    embedding_model: str = Field(
        default="intfloat/multilingual-e5-small",
        validation_alias="EMBEDDING_MODEL",
    )
    embedding_dim: int = Field(
        default=384,
        gt=0,
        validation_alias="EMBEDDING_DIM",
    )
    rag_collection: str = Field(
        default="rag_block_03",
        validation_alias="RAG_COLLECTION",
    )
    rag_baremetal_collection: str = Field(
        default="rag_baremetal_block_03",
        validation_alias="RAG_BAREMETAL_COLLECTION",
    )
    rag_data_dir: Path = Field(
        default=Path("./data"),
        validation_alias="RAG_DATA_DIR",
    )
    rag_chunk_size: int = Field(
        default=512,
        gt=0,
        validation_alias="RAG_CHUNK_SIZE",
    )
    rag_chunk_overlap: int = Field(
        default=64,
        ge=0,
        validation_alias="RAG_CHUNK_OVERLAP",
    )
    rag_similarity_top_k: int = Field(
        default=10,
        gt=0,
        validation_alias="RAG_SIMILARITY_TOP_K",
    )
    rag_reranker_enabled: bool = Field(
        default=True,
        validation_alias="RAG_RERANKER_ENABLED",
    )
    rag_reranker_top_n: int = Field(
        default=5,
        gt=0,
        validation_alias="RAG_RERANKER_TOP_N",
    )
    rag_score_threshold: float = Field(
        default=0.85,
        ge=0,
        validation_alias="RAG_SCORE_THRESHOLD",
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        validation_alias="CORS_ORIGINS",
    )
    log_level: str = Field(
        default="INFO",
        validation_alias="LOG_LEVEL",
    )
    admin_token: SecretStr = Field(
        default=SecretStr("replace-me"),
        validation_alias="ADMIN_TOKEN",
    )

    chat_repository: Literal["json", "postgres"] = Field(
        default="json",
        validation_alias="CHAT_REPOSITORY",
    )
    chat_storage_dir: Path = Field(
        default=Path("./var/chats"),
        validation_alias="CHAT_STORAGE_DIR",
    )
    chat_context_strategy: Literal["sliding", "hybrid"] = Field(
        default="sliding",
        validation_alias="CHAT_CONTEXT_STRATEGY",
    )
    chat_context_window: int = Field(
        default=10,
        ge=1,
        validation_alias="CHAT_CONTEXT_WINDOW",
    )

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()