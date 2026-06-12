import os

from openinference.instrumentation.openai import OpenAIInstrumentor
from phoenix.otel import register


def _normalize_phoenix_endpoint(endpoint: str) -> str:
    """
    Phoenix UI живёт на http://phoenix:6006,
    но HTTP endpoint для приёма traces — http://phoenix:6006/v1/traces.

    Если в переменной окружения указан только адрес Phoenix-сервера,
    добавляем нужный путь автоматически.
    """
    endpoint = endpoint.rstrip("/")

    if endpoint.endswith("/v1/traces"):
        return endpoint

    return f"{endpoint}/v1/traces"


def setup_tracing(project_name: str = "diploma-fastapi") -> None:
    """
    Настраивает отправку OpenAI traces в Phoenix.

    Важно: эту функцию нужно вызвать до создания OpenAI-клиента,
    чтобы автоинструментация успела примениться.
    """
    raw_endpoint = os.environ.get(
        "PHOENIX_COLLECTOR_ENDPOINT",
        "http://localhost:6006",
    )

    endpoint = _normalize_phoenix_endpoint(raw_endpoint)

    tracer_provider = register(
        project_name=project_name,
        endpoint=endpoint,
    )

    OpenAIInstrumentor().instrument(
        tracer_provider=tracer_provider,
    )