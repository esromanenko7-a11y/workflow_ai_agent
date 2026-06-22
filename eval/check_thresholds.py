from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml


DEFAULT_RUNS_DIR = Path(__file__).resolve().parent / "runs"
DEFAULT_THRESHOLDS_PATH = Path(__file__).resolve().parent / "thresholds.yaml"


def load_thresholds(path: Path) -> dict[str, float]:
    """
    Загружает пороги качества из YAML.

    Пример thresholds.yaml:
    correctness_avg: 4.0
    min_correctness: 2.0
    """
    if not path.exists():
        raise FileNotFoundError(f"Thresholds file not found: {path}")

    raw_data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))

    if not isinstance(raw_data, dict):
        raise ValueError("thresholds.yaml must contain a mapping")

    thresholds: dict[str, float] = {}

    for metric_name, metric_value in raw_data.items():
        if not isinstance(metric_name, str):
            raise ValueError("Threshold metric names must be strings")

        if not isinstance(metric_value, int | float):
            raise ValueError(
                f"Threshold for {metric_name!r} must be a number"
            )

        thresholds[metric_name] = float(metric_value)

    return thresholds


def find_latest_run(runs_dir: Path) -> Path:
    """
    Находит самый свежий JSON-файл в eval/runs/.
    """
    if not runs_dir.exists():
        raise FileNotFoundError(f"Runs directory not found: {runs_dir}")

    run_files = sorted(
        runs_dir.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not run_files:
        raise FileNotFoundError(
            f"No evaluation run files found in {runs_dir}"
        )

    return run_files[0]


def load_run(path: Path) -> dict[str, Any]:
    """
    Загружает результат evaluation-прогона.
    """
    if not path.exists():
        raise FileNotFoundError(f"Run file not found: {path}")

    return json.loads(path.read_text(encoding="utf-8-sig"))


def check_thresholds(
    run_data: dict[str, Any],
    thresholds: dict[str, float],
) -> list[str]:
    """
    Сравнивает aggregates из run-файла с порогами.

    Возвращает список сообщений об ошибках.
    Если список пустой — все пороги пройдены.
    """
    aggregates = run_data.get("aggregates")

    if not isinstance(aggregates, dict):
        return ["Run file does not contain valid 'aggregates' object"]

    failures: list[str] = []

    for metric_name, threshold_value in thresholds.items():
        actual_value = aggregates.get(metric_name)

        if actual_value is None:
            failures.append(
                f"{metric_name}: missing in run aggregates "
                f"(required >= {threshold_value})"
            )
            continue

        if not isinstance(actual_value, int | float):
            failures.append(
                f"{metric_name}: value must be numeric, got {actual_value!r}"
            )
            continue

        if float(actual_value) < threshold_value:
            failures.append(
                f"{metric_name}: {actual_value:.3f} "
                f"< required {threshold_value:.3f}"
            )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check evaluation run against quality thresholds."
    )
    parser.add_argument(
        "--runs-dir",
        default=str(DEFAULT_RUNS_DIR),
        help="Directory with evaluation run JSON files.",
    )
    parser.add_argument(
        "--thresholds",
        default=str(DEFAULT_THRESHOLDS_PATH),
        help="Path to thresholds.yaml.",
    )
    parser.add_argument(
        "--run",
        default=None,
        help="Optional path to a specific run JSON file. "
        "If not provided, the latest file from --runs-dir is used.",
    )

    args = parser.parse_args()

    thresholds_path = Path(args.thresholds)
    runs_dir = Path(args.runs_dir)

    try:
        thresholds = load_thresholds(thresholds_path)
        run_path = Path(args.run) if args.run else find_latest_run(runs_dir)
        run_data = load_run(run_path)
        failures = check_thresholds(run_data, thresholds)
    except Exception as exc:
        print(f"Threshold check failed: {exc}", file=sys.stderr)
        return 1

    print(f"Run file: {run_path}")
    print(f"Thresholds file: {thresholds_path}")

    if failures:
        print("Quality thresholds failed:")

        for failure in failures:
            print(f"- {failure}")

        return 1

    print("Quality thresholds passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())