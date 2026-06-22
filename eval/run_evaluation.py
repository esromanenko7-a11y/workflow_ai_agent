from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI


DEFAULT_APP_URL = "http://localhost:8000/chat"


def load_golden_dataset(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Golden dataset not found: {path}")

    dataset = json.loads(path.read_text(encoding="utf-8"))

    if dataset.get("version") != 1:
        raise ValueError("Golden dataset must contain version: 1")

    items = dataset.get("items")

    if not isinstance(items, list) or not items:
        raise ValueError("Golden dataset must contain non-empty items list")

    return dataset


async def call_app(
    client: httpx.AsyncClient,
    app_url: str,
    question: str,
    model_under_test: str | None,
) -> str:
    """
    Вызывает наш FastAPI endpoint /chat.

    Важно:
    - temperature=0, чтобы ответы были стабильнее;
    - X-Request-ID помогает потом найти запрос в логах/Phoenix.
    """
    payload: dict[str, Any] = {
        "messages": [
            {
                "role": "user",
                "content": question,
            }
        ],
        "temperature": 0,
        "max_tokens": 1000,
    }

    if model_under_test:
        payload["model"] = model_under_test

    response = await client.post(
        app_url,
        json=payload,
        headers={
            "X-Request-ID": f"eval-{uuid.uuid4().hex[:12]}",
        },
        timeout=120,
    )
    response.raise_for_status()

    data = response.json()
    return str(data.get("content", ""))


def build_judge_prompt(item: dict[str, Any], answer: str) -> str:
    """
    G-Eval style prompt.

    Просим judge сначала написать reasoning,
    а потом оценки score по критериям.
    """
    expected_keywords = item.get("expected_keywords", [])
    must_not_contain = item.get("must_not_contain", [])

    return f"""
You are an expert evaluator of an AI assistant for data package validation.

Evaluate the assistant answer against the golden expectation.

Important:
- Return ONLY valid JSON.
- Do not use markdown.
- The JSON object MUST contain fields in this order:
  1. reasoning
  2. scores
  3. explanation
- In reasoning, briefly explain your evaluation before giving scores.
- Scores must be integers from 1 to 5.

Scoring criteria:
- relevance: Does the answer address the user's question?
- correctness: Is the answer factually and logically correct according to the expected answer?
- completeness: Does the answer cover the important parts of the expected answer?

JSON schema example:
{{
  "reasoning": "The answer explains the blocking status and says the package must not be sent further until fixed.",
  "scores": {{
    "relevance": 5,
    "correctness": 5,
    "completeness": 5
  }},
  "explanation": "The answer is relevant, correct, and complete."
}}

Golden item:
id: {item["id"]}
category: {item["category"]}
difficulty: {item["difficulty"]}

Question:
{item["question"]}

Expected answer:
{item["expected_answer"]}

Expected keywords or synonyms:
{json.dumps(expected_keywords, ensure_ascii=False)}

Forbidden phrases or meanings:
{json.dumps(must_not_contain, ensure_ascii=False)}

Assistant answer:
{answer}
""".strip()


def build_judge_client() -> AsyncOpenAI:
    """
    Создаёт OpenAI-compatible client для judge-модели.

    Можно использовать:
    - JUDGE_OPENAI_API_KEY / JUDGE_OPENAI_BASE_URL
    - или обычные OPENAI_API_KEY / OPENAI_BASE_URL
    """
    api_key = os.getenv("JUDGE_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("JUDGE_OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL")

    kwargs: dict[str, Any] = {
        "api_key": api_key,
    }

    if base_url:
        kwargs["base_url"] = base_url

    return AsyncOpenAI(**kwargs)


async def call_judge(
    judge_client: AsyncOpenAI,
    judge_model: str,
    item: dict[str, Any],
    answer: str,
) -> dict[str, Any]:
    prompt = build_judge_prompt(item, answer)

    response = await judge_client.chat.completions.create(
        model=judge_model,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        temperature=0,
        response_format={
            "type": "json_object",
        },
    )

    raw_content = response.choices[0].message.content or "{}"
    judge_result = json.loads(raw_content)

    reasoning = str(judge_result.get("reasoning", ""))
    explanation = str(judge_result.get("explanation", ""))
    scores = judge_result.get("scores", {})

    if not isinstance(scores, dict):
        raise ValueError(f"Judge returned invalid scores for item {item['id']}")

    return {
        "reasoning": reasoning,
        "scores": {
            "relevance": int(scores["relevance"]),
            "correctness": int(scores["correctness"]),
            "completeness": int(scores["completeness"]),
        },
        "explanation": explanation,
    }


def make_dry_run_judge_result(item: dict[str, Any]) -> dict[str, Any]:
    """
    Offline-режим для проверки пайплайна без LLM judge.

    Ставит 5/5, потому что в dry-run мы используем expected_answer
    как будто это ответ модели.
    """
    return {
        "reasoning": (
            "Dry-run mode: expected_answer is used as the assistant answer, "
            "so the item is treated as fully matching the golden expectation."
        ),
        "scores": {
            "relevance": 5,
            "correctness": 5,
            "completeness": 5,
        },
        "explanation": "Dry-run structural check passed.",
    }


def calculate_aggregates(items: list[dict[str, Any]]) -> dict[str, float]:
    if not items:
        raise ValueError("Cannot calculate aggregates for empty items")

    relevance_values = [
        item["scores"]["relevance"]
        for item in items
    ]
    correctness_values = [
        item["scores"]["correctness"]
        for item in items
    ]
    completeness_values = [
        item["scores"]["completeness"]
        for item in items
    ]

    return {
        "relevance_avg": round(sum(relevance_values) / len(relevance_values), 3),
        "correctness_avg": round(sum(correctness_values) / len(correctness_values), 3),
        "completeness_avg": round(sum(completeness_values) / len(completeness_values), 3),
        "min_correctness": float(min(correctness_values)),
    }


async def run_evaluation(args: argparse.Namespace) -> dict[str, Any]:
    golden_path = Path(args.golden)
    out_path = Path(args.out)

    dataset = load_golden_dataset(golden_path)
    items = dataset["items"]

    run_items: list[dict[str, Any]] = []

    judge_client: AsyncOpenAI | None = None

    if not args.dry_run:
        judge_client = build_judge_client()

    async with httpx.AsyncClient() as http_client:
        for item in items:
            print(f"Evaluating {item['id']}...")

            if args.dry_run:
                answer = item["expected_answer"]
                judge_result = make_dry_run_judge_result(item)
            else:
                answer = await call_app(
                    client=http_client,
                    app_url=args.app_url,
                    question=item["question"],
                    model_under_test=args.model_under_test,
                )

                if judge_client is None:
                    raise RuntimeError("Judge client was not initialized")

                judge_result = await call_judge(
                    judge_client=judge_client,
                    judge_model=args.judge,
                    item=item,
                    answer=answer,
                )

            run_items.append(
                {
                    "id": item["id"],
                    "question": item["question"],
                    "answer": answer,
                    "scores": judge_result["scores"],
                    "reasoning": judge_result["reasoning"],
                    "explanation": judge_result["explanation"],
                }
            )

    timestamp = datetime.now(UTC).isoformat()
    run_id = f"eval-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

    result = {
        "run_id": run_id,
        "timestamp": timestamp,
        "model_under_test": args.model_under_test or "app-default",
        "judge_model": args.judge,
        "golden_version": dataset["version"],
        "items": run_items,
        "aggregates": calculate_aggregates(run_items),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run evaluation for the FastAPI LLM service."
    )
    parser.add_argument(
        "--golden",
        required=True,
        help="Path to eval/golden_dataset.json.",
    )
    parser.add_argument(
        "--judge",
        required=True,
        help="Judge model name, for example gpt-5 or gpt-5.2.",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Path to output JSON file in eval/runs/.",
    )
    parser.add_argument(
        "--app-url",
        default=DEFAULT_APP_URL,
        help="FastAPI /chat endpoint URL.",
    )
    parser.add_argument(
        "--model-under-test",
        default=None,
        help="Optional model name to pass to the app.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without calling app or judge. Useful for offline structural checks.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = asyncio.run(run_evaluation(args))

    print("Evaluation completed.")
    print(f"Run ID: {result['run_id']}")
    print(f"Output saved to: {args.out}")
    print("Aggregates:")
    print(json.dumps(result["aggregates"], ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
