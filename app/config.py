import os

from dotenv import load_dotenv


load_dotenv()


# Настройки Ollama
OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434/v1",
)
SUPPORT_PRIMARY_MODEL = os.getenv(
    "SUPPORT_PRIMARY_MODEL",
    "qwen2.5vl:7b",
)
SUPPORT_CLASSIFIER_MODEL = os.getenv(
    "SUPPORT_CLASSIFIER_MODEL",
    "llama3.2",
)


# Настройки Qdrant
QDRANT_URL = os.getenv(
    "QDRANT_URL",
    "http://localhost:6333",
)
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None
QDRANT_COLLECTION = os.getenv(
    "QDRANT_COLLECTION",
    "documents",
)
EMBEDDING_DIM = int(
    os.getenv("EMBEDDING_DIM", "384")
)


def validate_config() -> None:
    """
    Проверяет обязательные настройки приложения.
    """
    if not OLLAMA_BASE_URL:
        raise ValueError(
            "Не найден OLLAMA_BASE_URL в .env"
        )

    if not SUPPORT_PRIMARY_MODEL:
        raise ValueError(
            "Не найден SUPPORT_PRIMARY_MODEL в .env"
        )

    if not QDRANT_URL:
        raise ValueError(
            "Не найден QDRANT_URL в .env"
        )

    if EMBEDDING_DIM <= 0:
        raise ValueError(
            "EMBEDDING_DIM должен быть положительным числом"
        )