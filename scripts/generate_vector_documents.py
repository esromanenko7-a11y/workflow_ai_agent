import json
from pathlib import Path

from app.services.document_generator import generate_documents


OUTPUT_FILE = Path("app/data/vector_documents.json")


def main() -> None:
    """
    Генерирует документы и сохраняет их в JSON.

    Этот скрипт используется для ручной проверки.
    Основная логика генерации находится
    в app/services/document_generator.py.
    """

    documents = generate_documents()

    output_data = [
        document.model_dump()
        for document in documents
    ]

    OUTPUT_FILE.write_text(
        json.dumps(
            output_data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Создано документов: {len(documents)}")
    print(f"Файл: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()