import requests

URL = "http://127.0.0.1:8000/rag/query"

questions = [
    "Какие обязательные технические поля должны быть в meta-файле?",
    "Что проверяет правило META_FIELDS_EXIST_IN_DATA?",
    "Что означает проверка DATA_FIELDS_EXIST_IN_META?",
    "Какие проверки выполняются для соответствия meta-файла и data-файла?",
    "Какие требования предъявляются к XML-схеме пакета данных?"
]

for i, question in enumerate(questions, start=1):
    print("=" * 80)
    print(f"Вопрос {i}")
    print(question)

    response = requests.post(
        URL,
        json={"question": question},
        timeout=180,
    )

    data = response.json()

    print("\nОтвет:")
    print(data["answer"])

    print(f"\nTop score: {data['top_score']}")

    print("\nИсточники:")

    for source in data["sources"]:
        print(
            f" - {source['source']} "
            f"(score={source['score']:.3f})"
        )

print("\nГотово.")