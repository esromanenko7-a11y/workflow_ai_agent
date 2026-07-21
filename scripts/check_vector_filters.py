import asyncio

from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
)

from app.services.embeddings import get_embedding_service
from app.services.vector_store import get_vector_store


QUERY = "meta файл"


async def main() -> None:
    embedding_service = get_embedding_service()
    vector_store = get_vector_store()

    try:
        query_vector = embedding_service.embed_query(QUERY)

        query_filter = Filter(
            must=[
                FieldCondition(
                    key="category",
                    match=MatchValue(
                        value="Проверка meta-файла",
                    ),
                ),
            ],
        )

        results = await vector_store.search(
            query_vector=query_vector,
            limit=5,
            query_filter=query_filter,
        )

        print(f"Найдено: {len(results)}")

        for result in results:
            payload = result.payload

            print("-" * 80)
            print(payload["check_code"])
            print(payload["chunk_type"])
            print(payload["category"])
            print(result.score)

    finally:
        await vector_store.close()


if __name__ == "__main__":
    asyncio.run(main())