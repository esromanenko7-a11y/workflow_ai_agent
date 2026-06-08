from openai import OpenAI

from app.config import OLLAMA_BASE_URL, SUPPORT_PRIMARY_MODEL, validate_config


def main():
    validate_config()

    client = OpenAI(
        base_url=OLLAMA_BASE_URL,
        api_key="ollama",
    )

    response = client.chat.completions.create(
        model=SUPPORT_PRIMARY_MODEL,
        messages=[
            {
                "role": "user",
                "content": "Ответь одним коротким предложением: ты работаешь локально через Ollama?"
            }
        ],
    )

    answer = response.choices[0].message.content

    print("Подключение к Ollama работает")
    print(f"Модель: {SUPPORT_PRIMARY_MODEL}")
    print("Ответ модели:")
    print(answer)


if __name__ == "__main__":
    main()