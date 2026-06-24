import re
import unicodedata
from dataclasses import dataclass
from typing import Final


MAX_INPUT_CHARS: Final[int] = 4000
NON_PRINTABLE_RATIO_LIMIT: Final[float] = 0.10
SUSPICIOUS_UNICODE_RATIO_LIMIT: Final[float] = 0.35

INJECTION_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(
        r"\bignore\s+(any|all)\s+(previous|prior|above)(\s+and\s+following)?\s+instructions?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bstop\s+everything\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bjust\s+print\s+[\"'??]?i\s+hate\s+humans[\"'??]?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bdisregard\s+(the\s+)?(system|previous|above)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bforget\s+(everything|all|previous)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\byou\s+are\s+now\s+(a|an|the|dan|do anything now)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(dan mode|developer mode|jailbreak|jailbroken|godmode)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(system prompt|hidden instructions|secret instructions)\b",
        re.IGNORECASE,
    ),
]

ENCODING_MARKERS: Final[list[re.Pattern[str]]] = [
    re.compile(r"\bbase64\b", re.IGNORECASE),
    re.compile(r"\bdecode\s+this\b", re.IGNORECASE),
    re.compile(r"\batob\s*\(", re.IGNORECASE),
    re.compile(r"\bfrom\s+base64\b", re.IGNORECASE),
]


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reason: str | None = None
    rule: str | None = None


def _non_printable_ratio(text: str) -> float:
    if not text:
        return 0.0

    non_printable_count = sum(
        1
        for char in text
        if not char.isprintable() and char not in "\n\r\t"
    )

    return non_printable_count / len(text)


def _suspicious_unicode_ratio(text: str) -> float:
    """
    Простая эвристика на необычные unicode-символы.

    Разрешаем обычные буквы, цифры, пробелы, пунктуацию и кириллицу/латиницу.
    Остальное считаем подозрительным, но не блокируем один символ — смотрим долю.
    """
    if not text:
        return 0.0

    suspicious_count = 0

    for char in text:
        if char.isspace():
            continue

        category = unicodedata.category(char)

        if category.startswith(("L", "N", "P", "S")):
            name = unicodedata.name(char, "")

            if (
                "CYRILLIC" in name
                or "LATIN" in name
                or "DIGIT" in name
                or category.startswith(("N", "P"))
            ):
                continue

        suspicious_count += 1

    return suspicious_count / len(text)


def validate_input(text: str) -> ValidationResult:
    """
    Проверяет пользовательский ввод до похода в LLM.

    Для нашего проекта выбираем стратегию: блокировать подозрительный ввод.
    В роутере это будет превращаться в HTTP 400.

    Почему блокируем:
    - garak видит 400 без поля content как защитный отказ;
    - мы не тратим LLM-токены на очевидные jailbreak/injection prompts;
    - пользователь получает понятную ошибку вместо небезопасного ответа.
    """
    if len(text) > MAX_INPUT_CHARS:
        return ValidationResult(
            ok=False,
            reason="input too long",
            rule="length",
        )

    if _non_printable_ratio(text) > NON_PRINTABLE_RATIO_LIMIT:
        return ValidationResult(
            ok=False,
            reason="high non-printable character ratio",
            rule="encoding_non_printable",
        )

    if _suspicious_unicode_ratio(text) > SUSPICIOUS_UNICODE_RATIO_LIMIT:
        return ValidationResult(
            ok=False,
            reason="high suspicious unicode character ratio",
            rule="encoding_unicode",
        )

    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            return ValidationResult(
                ok=False,
                reason=f"matched injection pattern: {pattern.pattern}",
                rule="injection",
            )

    for pattern in ENCODING_MARKERS:
        if pattern.search(text):
            return ValidationResult(
                ok=False,
                reason=f"matched encoding marker: {pattern.pattern}",
                rule="encoding_marker",
            )

    return ValidationResult(ok=True)