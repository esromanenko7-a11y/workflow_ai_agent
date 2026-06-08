from app.prompts.loader import load_tool_description


GET_VALIDATION_REPORT_TOOL = {
    "type": "function",
    "function": {
        "name": "get_validation_report",
        "description": load_tool_description("get_validation_report"),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "package_id": {
                    "type": "string",
                    "description": "Идентификатор пакета данных в формате PKG-001",
                    "pattern": "^PKG-[0-9]{3}$"
                }
            },
            "required": ["package_id"],
            "additionalProperties": False
        }
    }
}


TOOLS = [
    GET_VALIDATION_REPORT_TOOL
]