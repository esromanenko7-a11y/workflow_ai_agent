import json
import logging
from pathlib import Path
from typing import Any

from jsonschema import validate
from openai import OpenAI

from app.config import OLLAMA_BASE_URL, SUPPORT_PRIMARY_MODEL, validate_config
from app.prompts.loader import render_prompt_file, render_system_prompt
from app.tools.handlers import TOOL_HANDLERS
from app.tools.schemas import TOOLS
import re


LOG_FILE = Path("logs/tool_calls.jsonl")
PACKAGE_ID_PATTERN = re.compile(r"\bPKG-\d{3}\b")
GENERAL_QUESTION_KEYWORDS = [
    "что означает",
    "что такое",
    "объясни",
    "расскажи",
    "какие бывают",
    "как понять",
    "для чего",
    "чем отличается",
]


PACKAGE_CHECK_KEYWORDS = [
    "проверь",
    "проверить",
    "проверка пакета",
    "можно ли передавать дальше",
    "можно ли его передавать",
    "можно ли пакет передавать",
    "есть проблемы",
    "проблемы с пакетом",
    "с пакетом есть проблемы",
]


def looks_like_general_question(user_input: str) -> bool:
    """
    Определяет, похож ли запрос на общий справочный вопрос.
    Например: "Что означает статус BLOCKED?"
    """
    normalized_input = user_input.lower()

    return any(keyword in normalized_input for keyword in GENERAL_QUESTION_KEYWORDS)


def looks_like_package_check_request(user_input: str) -> bool:
    """
    Определяет, похож ли запрос на просьбу проверить конкретный пакет.

    Важно: слово "пакет" само по себе здесь не используем,
    потому что оно встречается и в общих вопросах.
    """
    normalized_input = user_input.lower()

    return any(keyword in normalized_input for keyword in PACKAGE_CHECK_KEYWORDS)


def setup_logger() -> logging.Logger:
    """
    Создаёт логгер, который пишет события в файл logs/tool_calls.jsonl.
    Каждая строка — отдельный JSON.
    """
    LOG_FILE.parent.mkdir(exist_ok=True)

    logger = logging.getLogger("tool_call_logger")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        logger.addHandler(file_handler)

    return logger


logger = setup_logger()


def log_event(event_type: str, data: dict[str, Any]) -> None:
    """
    Записывает одно событие в лог.
    """
    event = {
        "event_type": event_type,
        **data,
    }

    logger.info(json.dumps(event, ensure_ascii=False))


def get_total_tokens(response) -> int | None:
    """
    Достаёт usage.total_tokens из ответа модели, если Ollama его вернула.
    У локальных моделей это поле может отсутствовать.
    """
    usage = getattr(response, "usage", None)

    if usage is None:
        return None

    return getattr(usage, "total_tokens", None)


def ask_assistant(user_input: str) -> str:
    """
    Полный цикл Function Calling:
    1. отправляем вопрос пользователя и список tools;
    2. если модель выбрала tool — выполняем Python-функцию;
    3. возвращаем результат tool модели;
    4. получаем финальный ответ.
    """
    validate_config()

    client = OpenAI(
        base_url=OLLAMA_BASE_URL,
        api_key="ollama",
    )

    messages = [
        {
            "role": "system",
            "content": render_system_prompt(),
        },
        {
            "role": "user",
            "content": user_input,
        },
    ]

    log_event("user_input", {"input": user_input})

    has_package_id = PACKAGE_ID_PATTERN.search(user_input) is not None
    is_general_question = looks_like_general_question(user_input)
    is_package_check_request = looks_like_package_check_request(user_input)

    if not has_package_id and not is_general_question and is_package_check_request:
        final_answer = (
            "Чтобы проверить пакет, укажите его package_id в формате PKG-001. "
            "Без идентификатора я не могу получить результаты автоматических проверок."
        )

        log_event(
            "final_answer_without_tool",
            {
                "answer": final_answer,
                "total_tokens": None,
                "reason": "package_id_required",
            },
        )

        return final_answer

    

    if has_package_id:
        first_response = client.chat.completions.create(
            model=SUPPORT_PRIMARY_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0,
        )
    else:
        first_response = client.chat.completions.create(
            model=SUPPORT_PRIMARY_MODEL,
            messages=messages,
            temperature=0,
        )

    first_message = first_response.choices[0].message
    first_tokens = get_total_tokens(first_response)

    tool_calls = first_message.tool_calls

    if not tool_calls:
        final_answer = first_message.content or ""

        log_event(
            "final_answer_without_tool",
            {
                "answer": final_answer,
                "total_tokens": first_tokens,
            },
        )

        return final_answer

    messages.append(
        {
            "role": "user",
            "content": render_prompt_file("final_report_v1.j2"),
        }
    )

    for tool_call in tool_calls:
        tool_name = tool_call.function.name
        raw_arguments = tool_call.function.arguments
        arguments = json.loads(raw_arguments)

        log_event(
            "tool_call",
            {
                "tool_name": tool_name,
                "arguments": arguments,
            },
        )

        tool_schema = None

        for tool in TOOLS:
            if tool["function"]["name"] == tool_name:
                tool_schema = tool["function"]["parameters"]
                break

        if tool_schema is None:
            tool_result = {
                "error": f"Неизвестный tool: {tool_name}"
            }
        elif tool_name not in TOOL_HANDLERS:
            tool_result = {
                "error": f"Для tool {tool_name} не найден Python-обработчик"
            }
        else:
            validate(instance=arguments, schema=tool_schema)

            handler = TOOL_HANDLERS[tool_name]
            tool_result = handler(**arguments)

        log_event(
            "tool_result",
            {
                "tool_name": tool_name,
                "result": tool_result,
            },
        )

        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(tool_result, ensure_ascii=False),
            }
        )

    second_response = client.chat.completions.create(
        model=SUPPORT_PRIMARY_MODEL,
        messages=messages,
        temperature=0,
    )

    final_answer = second_response.choices[0].message.content or ""
    second_tokens = get_total_tokens(second_response)

    log_event(
        "final_answer",
        {
            "answer": final_answer,
            "first_response_tokens": first_tokens,
            "second_response_tokens": second_tokens,
        },
    )

    return final_answer