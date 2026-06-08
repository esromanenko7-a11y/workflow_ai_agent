from jsonschema import validate

from app.tools.schemas import GET_VALIDATION_REPORT_TOOL


def main():
    print("Начинаю проверку JSON Schema...")

    tool_parameters_schema = GET_VALIDATION_REPORT_TOOL["function"]["parameters"]

    arguments = {
        "package_id": "PKG-001"
    }

    validate(instance=arguments, schema=tool_parameters_schema)

    print("JSON Schema валидна")
    print("Аргументы подходят под схему:")
    print(arguments)


if __name__ == "__main__":
    main()