import json
from pathlib import Path


DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "validation_reports.json"


def build_recommendation(message: str) -> str:
    """
    Формирует понятную рекомендацию на основе текста проверки.
    """
    if "metadata.json" in message:
        return "Добавить файл metadata.json в пакет."

    if "DD.MM.YYYY" in message:
        return "Привести даты к формату YYYY-MM-DD."

    return f"Исправить проблему: {message}"


def analyze_checks(checks: list[dict]) -> dict:
    """
    Группирует проверки и определяет итоговый статус пакета.

    Это бизнес-логика проекта.
    LLM не должна сама решать, blocked пакет или approved.
    """
    critical_errors = []
    warnings = []
    ok_checks = []
    recommendations = []

    for check in checks:
        status = check.get("status")
        message = check.get("message", "")

        if status == "error":
            critical_errors.append(check)
            recommendations.append(build_recommendation(message))

        elif status == "warning":
            warnings.append(check)
            recommendations.append(build_recommendation(message))

        elif status == "ok":
            ok_checks.append(check)

    if critical_errors:
        final_status = "BLOCKED"
        can_pass_next = "нет"
    elif warnings:
        final_status = "NEEDS_REVIEW"
        can_pass_next = "требуется ручная проверка"
    else:
        final_status = "APPROVED"
        can_pass_next = "да"

    return {
        "final_status": final_status,
        "can_pass_next": can_pass_next,
        "critical_errors": critical_errors,
        "warnings": warnings,
        "ok_checks": ok_checks,
        "recommendations": recommendations,
    }


def get_validation_report(package_id: str) -> dict:
    """
    Получает результаты проверок пакета по package_id.
    """
    reports_text = DATA_FILE.read_text(encoding="utf-8")
    reports = json.loads(reports_text)

    report = reports.get(package_id)

    if report is None:
        return {
            "found": False,
            "package_id": package_id,
            "message": "Пакет с таким package_id не найден",
        }

    analysis = analyze_checks(report["checks"])

    return {
        "found": True,
        "package_id": package_id,
        "package_name": report["package_name"],
        "checks": report["checks"],
        "analysis": analysis,
    }


TOOL_HANDLERS = {
    "get_validation_report": get_validation_report
}