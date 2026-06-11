class LLMError(Exception):
    """Базовая ошибка LLM-слоя."""

    code = "llm_error"
    message = "Ошибка при обращении к LLM-провайдеру"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.message
        super().__init__(self.message)


class LLMRateLimitError(LLMError):
    """Провайдер ограничил частоту запросов."""

    code = "llm_rate_limit"
    message = "Превышен лимит запросов к LLM-провайдеру"


class LLMTimeoutError(LLMError):
    """LLM-провайдер не ответил за отведённое время."""

    code = "llm_timeout"
    message = "LLM-провайдер не ответил за отведённое время"


class LLMAuthError(LLMError):
    """Ошибка авторизации у LLM-провайдера."""

    code = "llm_auth"
    message = "Ошибка авторизации у LLM-провайдера"