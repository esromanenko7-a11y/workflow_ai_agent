import re
from typing import Final

from app.observability.pii import redact_pii


PASSPORT_RU_RE: Final[re.Pattern[str]] = re.compile(
    r"\b\d{4}\s?\d{6}\b"
)


def _normalize_spaces(text: str) -> str:
    return " ".join(text.split())


def filter_output(
    answer: str,
    system_prompt: str,
    canary: str,
) -> str:
    """
    Фильтрует ответ LLM перед возвратом пользователю.

    Что проверяем:
    - не утёк ли canary-token;
    - не утёк ли system prompt;
    - нет ли сырых PII в ответе.

    Если утёк system prompt или canary — считаем это security-инцидентом
    и поднимем ValueError. В роутере превратим это в HTTP 502.
    """
    normalized_answer = _normalize_spaces(answer)
    normalized_system_prompt = _normalize_spaces(system_prompt)

    if canary and canary in answer:
        raise ValueError("system_prompt leakage: canary detected")

    system_prompt_head = normalized_system_prompt[:120]

    if (
        system_prompt_head
        and system_prompt_head.lower() in normalized_answer.lower()
    ):
        raise ValueError("system_prompt leakage: system prompt prefix detected")

    # Сначала маскируем паспорт РФ без пробелов.
    # Иначе 10 цифр могут быть ошибочно распознаны общим INN-правилом
    # из app.observability.pii.redact_pii.
    masked_answer = PASSPORT_RU_RE.sub("[PASSPORT]", answer)

    # Затем переиспользуем общий PII-маскер из observability-слоя:
    # email, телефон, карта, ИНН, паспорт с пробелами.
    masked_answer = redact_pii(masked_answer)

    return masked_answer
