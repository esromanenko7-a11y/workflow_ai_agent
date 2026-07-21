import asyncio

from app.services.embeddings import get_embedding_service
from app.services.vector_store import get_vector_store


QUERY = "Какие обязательные поля должны быть в meta-файле?"
LIMIT = 5


async def main() -> None:
    embedding_service = get_embedding_service()
    vector_store = get_vector_store()

    try:
        query_vector = embedding_service.embed_query(QUERY)

        results = await vector_store.search(
            query_vector=query_vector,
            limit=LIMIT,
        )

        print(f"Запрос: {QUERY}")
        print(f"Найдено результатов: {len(results)}")
        print()

        for index, result in enumerate(results, start=1):
            payload = result.payload or {}

            print(f"Результат #{index}")
            print(f"Score: {result.score:.4f}")
            print(f"Код: {payload.get('check_code')}")
            print(f"Проверка: {payload.get('check_name')}")
            print(f"Категория: {payload.get('category')}")
            print(f"Критичность: {payload.get('severity')}")
            print(f"Тип документа: {payload.get('chunk_type')}")
            print("Текст:")
            print(payload.get("text"))
            print("-" * 80)

    finally:
        await vector_store.close()


if __name__ == "__main__":
    asyncio.run(main())