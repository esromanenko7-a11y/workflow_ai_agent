from pathlib import Path

from app.data.validation_catalog import VALIDATION_CATALOG


OUTPUT_DIR = Path("data/rag-block-03")

SELECTED_CHECK_CODES = [
    "PACKAGE_UNPACKING",
    "FILE_NAMING",
    "META_FILE_FORMAT",
    "META_FILE_STRUCTURE",
    "META_REQUIRED_TECH_FIELDS",
    "META_DATA_TYPES",
    "DATA_FIELDS_EXIST_IN_META",
    "META_FIELDS_EXIST_IN_DATA",
    "DATA_QUOTING",
]


def build_document_text(rule) -> str:
    """
    Преобразует правило проверки в отдельный Markdown-документ.
    """
    sections = [
        f"# {rule.name}",
        "",
        f"Код проверки: `{rule.code}`",
        f"Категория: {rule.category}",
        f"Критичность: {rule.severity.upper()}",
        "",
        "## Описание проверки",
        "",
        rule.verification,
    ]

    if rule.objective:
        sections.extend(
            [
                "",
                "## Цель",
                "",
                rule.objective,
            ]
        )

    if rule.requirements:
        sections.extend(
            [
                "",
                "## Требования",
                "",
            ]
        )

        sections.extend(
            f"- {requirement}"
            for requirement in rule.requirements
        )

    if rule.notes:
        sections.extend(
            [
                "",
                "## Примечания",
                "",
            ]
        )

        sections.extend(
            f"- {note}"
            for note in rule.notes
        )

    return "\n".join(sections).strip() + "\n"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rules_by_code = {
        rule.code: rule
        for rule in VALIDATION_CATALOG
    }

    for check_code in SELECTED_CHECK_CODES:
        rule = rules_by_code.get(check_code)

        if rule is None:
            raise ValueError(
                f"В каталоге не найдена проверка: {check_code}"
            )

        file_name = f"{check_code.lower()}.md"
        file_path = OUTPUT_DIR / file_name

        file_path.write_text(
            build_document_text(rule),
            encoding="utf-8",
        )

        print(f"Создан файл: {file_path}")

    irrelevant_file = OUTPUT_DIR / "indoor_plants.txt"

    irrelevant_file.write_text(
        (
            "Уход за комнатными растениями\n\n"
            "Большинство комнатных растений нуждается в умеренном поливе, "
            "рассеянном освещении и подходящей влажности воздуха. "
            "Перед повторным поливом рекомендуется проверить состояние почвы. "
            "Частота полива зависит от времени года и вида растения.\n"
        ),
        encoding="utf-8",
    )

    print(f"Создан нерелевантный файл: {irrelevant_file}")
    print(f"Всего файлов: {len(list(OUTPUT_DIR.iterdir()))}")


if __name__ == "__main__":
    main()