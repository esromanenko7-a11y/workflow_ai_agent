from dataclasses import dataclass, field


@dataclass(frozen=True)
class ValidationRule:
    """
    Описание одной проверки PreChecker.

    verification:
        Исходное описание из колонки «Что проверяем».

    objective:
        Краткая цель проверки.

    requirements:
        Формализованные требования, допустимые значения
        и обязательные условия.

    notes:
        Дополнительные особенности алгоритма проверки.
    """

    code: str
    category: str
    name: str
    severity: str
    verification: str

    objective: str | None = None
    requirements: tuple[str, ...] = field(default_factory=tuple)
    notes: tuple[str, ...] = field(default_factory=tuple)

    needs_review: bool = False