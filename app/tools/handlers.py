import json
from pathlib import Path


DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "validation_reports.json"


def get_validation_report(package_id: str) -> dict:
    """
    Получает результаты проверок пакета по package_id.

    package_id — это строка, например "PKG-001".
    Функция возвращает словарь с результатом.
    """
    reports_text = DATA_FILE.read_text(encoding="utf-8")
    reports = json.loads(reports_text)

    report = reports.get(package_id)

    if report is None:
        return {
            "found": False,
            "package_id": package_id,
            "message": "Пакет с таким package_id не найден"
        }

    return {
        "found": True,
        "report": report
    }


TOOL_HANDLERS = {
    "get_validation_report": get_validation_report
}