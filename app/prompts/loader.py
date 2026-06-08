from functools import lru_cache
from pathlib import Path

from jinja2 import Template


PROMPTS_DIR = Path(__file__).parent


@lru_cache(maxsize=8)
def render_system_prompt(version: str = "v1", **context) -> str:
    """
    Загружает system prompt из файла.

    version="v1" означает:
    нужно прочитать файл app/prompts/system_v1.j2
    """
    prompt_path = PROMPTS_DIR / f"system_{version}.j2"
    text = prompt_path.read_text(encoding="utf-8")

    return Template(text).render(**context)

@lru_cache(maxsize=16)
def render_prompt_file(file_name: str, **context) -> str:
    """
    Загружает любой prompt-файл из app/prompts/ и подставляет переменные, если они есть.

    Пример:
    render_prompt_file("final_report_v1.j2")
    """
    prompt_path = PROMPTS_DIR / file_name
    text = prompt_path.read_text(encoding="utf-8")

    return Template(text).render(**context)

@lru_cache(maxsize=16)
def load_tool_description(tool_name: str) -> str:
    """
    Загружает описание tool из файла app/prompts/tools/<tool_name>.md
    """
    description_path = PROMPTS_DIR / "tools" / f"{tool_name}.md"

    return description_path.read_text(encoding="utf-8")