import os

from dotenv import load_dotenv


load_dotenv()


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
SUPPORT_PRIMARY_MODEL = os.getenv("SUPPORT_PRIMARY_MODEL", "qwen2.5vl:7b")
SUPPORT_CLASSIFIER_MODEL = os.getenv("SUPPORT_CLASSIFIER_MODEL", "llama3.2")


def validate_config() -> None:
    """
    Проверяет настройки подключения к локальной Ollama.
    """
    if not OLLAMA_BASE_URL:
        raise ValueError("Не найден OLLAMA_BASE_URL в .env")

    if not SUPPORT_PRIMARY_MODEL:
        raise ValueError("Не найден SUPPORT_PRIMARY_MODEL в .env")