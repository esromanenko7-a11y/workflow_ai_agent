from app.data.validation_catalog import VALIDATION_CATALOG
from app.data.validation_models import ValidationRule
from app.schemas.vector_document import VectorDocument


def create_document(
    *,
    rule: ValidationRule,
    chunk_type: str,
    text: str,
) -> VectorDocument:
    """
    Создаёт один документ для векторного поиска.

    rule:
        Исходное правило проверки.

    chunk_type:
        Тип смысловой части: description, objective,
        requirements или notes.

    text:
        Текст, по которому позже будет выполняться
        семантический поиск.
    """

    return VectorDocument(
        source="validation_catalog",
        check_code=rule.code,
        check_name=rule.name,
        category=rule.category,
        severity=rule.severity.lower(),
        chunk_type=chunk_type,
        text=text,
    )


def format_items(items: tuple[str, ...]) -> str:
    """
    Превращает кортеж требований или примечаний
    в читаемый маркированный текст.
    """

    return "\n".join(f"- {item}" for item in items)


def generate_documents() -> list[VectorDocument]:
    """
    Преобразует весь каталог ValidationRule
    в список документов для RAG.
    """

    documents: list[VectorDocument] = []

    for rule in VALIDATION_CATALOG:
        # Краткая карточка проверки.
        summary_parts = [
            f"Проверка: {rule.name}",
            f"Категория: {rule.category}",
            f"Критичность: {rule.severity}",
        ]

        if rule.objective:
            summary_parts.append(
                f"Цель проверки: {rule.objective}"
            )

        documents.append(
            create_document(
                rule=rule,
                chunk_type="summary",
                text="\n".join(summary_parts),
            )
        )
        # Полное описание из исходной документации.
        documents.append(
            create_document(
                rule=rule,
                chunk_type="description",
                text=rule.verification,
            )
        )

        # Краткая цель проверки.
        if rule.objective:
            documents.append(
                create_document(
                    rule=rule,
                    chunk_type="objective",
                    text=rule.objective,
                )
            )

        # Формализованные требования.
        if rule.requirements:
            documents.append(
                create_document(
                    rule=rule,
                    chunk_type="requirements",
                    text=format_items(rule.requirements),
                )
            )

        # Дополнительные условия и особенности алгоритма.
        if rule.notes:
            documents.append(
                create_document(
                    rule=rule,
                    chunk_type="notes",
                    text=format_items(rule.notes),
                )
            )

    return documents