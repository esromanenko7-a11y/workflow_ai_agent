from app.services.embeddings import get_embedding_service
from qdrant_client.models import PointStruct
import asyncio

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

from app.config import (
    EMBEDDING_DIM,
    QDRANT_API_KEY,
    QDRANT_COLLECTION,
    QDRANT_URL,
)

DOT_COLLECTION = "documents_dot"
QUERIES = [
    "Ошибка разархивирования пакета",
    "В meta-файле отсутствуют обязательные технические поля",
    "Поля data-файла не совпадают с полями meta-файла",
    "Неверный формат meta-файла",
    "Некорректное имя файла в пакете",
]
async def search_ids(
    client: AsyncQdrantClient,
    collection_name: str,
    query_vector: list[float],
) -> list[str]:
    result = await client.query_points(
        collection_name=collection_name,
        query=query_vector,
        limit=5,
        with_payload=True,
    )

    return [str(point.id) for point in result.points]
async def main() -> None:
    client = AsyncQdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY,
    )

    collections = await client.get_collections()
    names = {collection.name for collection in collections.collections}

    if DOT_COLLECTION in names:
        print(f"Коллекция '{DOT_COLLECTION}' уже существует.")
    else:
        print(f"Создаём коллекцию '{DOT_COLLECTION}'...")

        await client.create_collection(
            collection_name=DOT_COLLECTION,
            vectors_config=VectorParams(
                size=EMBEDDING_DIM,
                distance=Distance.DOT,
            ),
        )

        print("Коллекция создана.")
    print("Копируем точки...")

    offset = None
    total = 0

    while True:
        points, offset = await client.scroll(
            collection_name=QDRANT_COLLECTION,
            limit=100,
            offset=offset,
            with_vectors=True,
            with_payload=True,
        )

        if not points:
            break

        dot_points = [
            PointStruct(
                id=point.id,
                vector=point.vector,
                payload=point.payload,
            )
            for point in points
        ]

        await client.upsert(
            collection_name=DOT_COLLECTION,
            points=dot_points,
            wait=True,
        )

        total += len(points)

        if offset is None:
            break

    print(f"Скопировано точек: {total}")
    embedding_service = get_embedding_service()

    print()
    print("=== Сравнение COSINE и DOT ===")

    for query in QUERIES:
        query_vector = embedding_service.embed_query(query)

        cosine_ids = await search_ids(
            client=client,
            collection_name=QDRANT_COLLECTION,
            query_vector=query_vector,
        )

        dot_ids = await search_ids(
            client=client,
            collection_name=DOT_COLLECTION,
            query_vector=query_vector,
        )

        same_ranking = cosine_ids == dot_ids

        print()
        print(f"Запрос: {query}")
        print(f"COSINE: {cosine_ids}")
        print(f"DOT:    {dot_ids}")
        print(
            "Ранжирование совпало:",
            "ДА" if same_ranking else "НЕТ",
        )
    print()
    print("Удаляем временную коллекцию documents_dot...")

    await client.delete_collection(DOT_COLLECTION)

    print("Коллекция удалена.")
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())