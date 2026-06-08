from app.llm.client import ask_assistant


def main():
    user_input = "Проверь пакет PKG-001. Можно ли его передавать дальше?"

    answer = ask_assistant(user_input)

    print("Ответ ассистента:")
    print(answer)


if __name__ == "__main__":
    main()