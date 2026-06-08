from app.llm.client import ask_assistant


TEST_CASES = [
    {
        "name": "Случай A: запрос точно требует tool",
        "input": "Проверь пакет PKG-001. Можно ли его передавать дальше?"
    },
    {
        "name": "Случай B: запрос точно не требует tool",
        "input": "Что означает статус BLOCKED при проверке пакета данных?"
    },
    {
        "name": "Случай C: пограничный запрос",
        "input": "Кажется, с пакетом есть проблемы. Можно ли его передавать дальше?"
    },
]


def main():
    for index, case in enumerate(TEST_CASES, start=1):
        print("=" * 80)
        print(f"{index}. {case['name']}")
        print(f"Запрос пользователя: {case['input']}")
        print("-" * 80)

        answer = ask_assistant(case["input"])

        print("Ответ ассистента:")
        print(answer)
        print()


if __name__ == "__main__":
    main()