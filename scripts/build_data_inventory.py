import argparse
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".html",
    ".htm",
    ".md",
    ".markdown",
    ".txt",
}


def human_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} Б"

    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} КБ"

    return f"{size_bytes / 1024 / 1024:.2f} МБ"


def get_category(file_path: Path, data_dir: Path) -> str:
    relative_path = file_path.relative_to(data_dir)

    if len(relative_path.parts) <= 1:
        return "root"

    return relative_path.parts[0]


def collect_inventory(data_dir: Path) -> dict:
    files = [
        path
        for path in data_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
        and not path.name.endswith(".failed")
    ]

    format_counter = Counter()
    category_counter = Counter()
    category_format_counter = defaultdict(Counter)

    total_size_bytes = 0

    for file_path in files:
        extension = file_path.suffix.lower()
        category = get_category(file_path, data_dir)
        size_bytes = file_path.stat().st_size

        format_counter[extension] += 1
        category_counter[category] += 1
        category_format_counter[category][extension] += 1
        total_size_bytes += size_bytes

    return {
        "files": sorted(files),
        "format_counter": format_counter,
        "category_counter": category_counter,
        "category_format_counter": category_format_counter,
        "total_size_bytes": total_size_bytes,
    }


def build_format_table(format_counter: Counter) -> list[str]:
    lines = [
        "| Формат | Количество файлов |",
        "|--------|:-----------------:|",
    ]

    for extension, count in sorted(format_counter.items()):
        lines.append(f"| `{extension}` | {count} |")

    return lines


def build_category_table(category_counter: Counter) -> list[str]:
    lines = [
        "| Категория | Количество файлов |",
        "|-----------|:-----------------:|",
    ]

    for category, count in sorted(category_counter.items()):
        lines.append(f"| `{category}` | {count} |")

    return lines


def build_category_format_table(category_format_counter: dict) -> list[str]:
    all_extensions = sorted(
        {
            extension
            for counter in category_format_counter.values()
            for extension in counter
        }
    )

    header = "| Категория | " + " | ".join(f"`{ext}`" for ext in all_extensions) + " | Итого |"
    separator = "|-----------|" + "|".join(":---:" for _ in all_extensions) + "|:----:|"

    lines = [
        header,
        separator,
    ]

    for category, counter in sorted(category_format_counter.items()):
        total = sum(counter.values())
        values = [
            str(counter.get(extension, 0))
            for extension in all_extensions
        ]

        lines.append(
            "| "
            + category
            + " | "
            + " | ".join(values)
            + f" | {total} |"
        )

    return lines


def write_inventory_doc(data_dir: Path, output_path: Path) -> None:
    inventory = collect_inventory(data_dir)

    files = inventory["files"]
    total_size_bytes = inventory["total_size_bytes"]

    lines = [
        "# Инвентаризация корпуса данных для RAG",
        "",
        "## Общая информация",
        "",
        f"- Папка корпуса: `{data_dir}`",
        f"- Дата формирования отчёта: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Количество файлов: **{len(files)}**",
        f"- Общий размер корпуса: **{human_size(total_size_bytes)}**",
        "",
        "## Разбивка по форматам",
        "",
        *build_format_table(inventory["format_counter"]),
        "",
        "## Разбивка по категориям",
        "",
        *build_category_table(inventory["category_counter"]),
        "",
        "## Матрица категорий и форматов",
        "",
        *build_category_format_table(inventory["category_format_counter"]),
        "",
        "## Примечание",
        "",
        "Корпус подготовлен для учебного корпоративного RAG-ассистента по проверке пакетов данных. Документы разложены по категориям в структуре `data/<category>/...`, чтобы категория могла автоматически попадать в metadata при ingestion.",
        "",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Файл создан: {output_path}")
    print(f"Количество файлов: {len(files)}")
    print(f"Общий размер: {human_size(total_size_bytes)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Формирование docs/data_inventory.md для RAG-корпуса.",
    )

    parser.add_argument(
        "--data-dir",
        default="data",
        help="Папка с корпусом документов.",
    )

    parser.add_argument(
        "--output",
        default="docs/data_inventory.md",
        help="Путь к markdown-отчёту.",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    write_inventory_doc(
        data_dir=Path(args.data_dir),
        output_path=Path(args.output),
    )


if __name__ == "__main__":
    main()
