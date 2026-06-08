from jsonschema import validate

from app.tools.handlers import TOOL_HANDLERS
from app.tools.schemas import GET_VALIDATION_REPORT_TOOL


def main():
    print("Начинаю локальный цикл tool...")

    tool_name = GET_VALIDATION_REPORT_TOOL["function"]["name"]
    tool_parameters_schema = GET_VALIDATION_REPORT_TOOL["function"]["parameters"]

    arguments = {
        "package_id": "PKG-001"
    }

    print("1. Проверяю аргументы по JSON Schema...")
    validate(instance=arguments, schema=tool_parameters_schema)

    print("2. Ищу Python-обработчик для tool...")
    handler = TOOL_HANDLERS[tool_name]

    print("3. Вызываю обработчик tool...")
    result = handler(**arguments)

    print("4. Результат работы tool:")
    print(result)


if __name__ == "__main__":
    main()