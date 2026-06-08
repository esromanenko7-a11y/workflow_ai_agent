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
                    "description": "Идентификатор пакета данных, например PKG-001"
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