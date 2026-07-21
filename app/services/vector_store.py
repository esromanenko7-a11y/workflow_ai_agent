from functools import lru_cache
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    Filter,
    PayloadSchemaType,
    PointStruct,
    ScoredPoint,
    VectorParams,
)

from app.core.config import get_settings
from app.schemas.vector_document import VectorDocument


# Максимальное количество точек в одном запросе upsert.
UPSERT_BATCH_SIZE = 128


class VectorStore:
    """Сервис для работы с векторной базой Qdrant."""

    def __init__(
        self,
        url: str,
        api_key: str | None,
        collection: str,
        embedding_dim: int,
    ) -> None:
        self.client = AsyncQdrantClient(
            url=url,
            api_key=api_key,
        )
        self.collection = collection
        self.embedding_dim = embedding_dim

    async def ensure_collection(self) -> None:
        """
        Создаёт коллекцию, если её ещё нет.

        Если коллекция уже существует:
        - проверяет размерность векторов;
        - создаёт недостающие payload-индексы.
        """
        collections_response = await self.client.get_collections()

        existing_collection_names = {
            collection.name
            for collection in collections_response.collections
        }

        if self.collection not in existing_collection_names:
            await self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(
                    size=self.embedding_dim,
                    distance=Distance.COSINE,
                ),
            )

            # Индексы создаём сразу после создания коллекции,
            # до первой загрузки документов.
            await self.ensure_payload_indexes()
            return

        collection_info = await self.client.get_collection(
            collection_name=self.collection,
        )

        vectors_config = collection_info.config.params.vectors
        actual_dimension = vectors_config.size

        if actual_dimension != self.embedding_dim:
            raise ValueError(
                "Размерность существующей коллекции Qdrant "
                "не совпадает с настройкой EMBEDDING_DIM: "
                f"в коллекции {actual_dimension}, "
                f"в конфигурации {self.embedding_dim}."
            )

        await self.ensure_payload_indexes()

    async def ensure_payload_indexes(self) -> None:
        """
        Создаёт индексы для полей, используемых в фильтрах.

        Метод можно запускать повторно:
        существующие индексы повторно не создаются.
        """
        collection_info = await self.client.get_collection(
            collection_name=self.collection,
        )

        existing_indexes = set(
            (collection_info.payload_schema or {}).keys()
        )

        required_indexes = {
            "source": PayloadSchemaType.KEYWORD,
            "category": PayloadSchemaType.KEYWORD,
            "severity": PayloadSchemaType.KEYWORD,
            "chunk_type": PayloadSchemaType.KEYWORD,
        }

        for field_name, field_schema in required_indexes.items():
            if field_name in existing_indexes:
                continue

            await self.client.create_payload_index(
                collection_name=self.collection,
                field_name=field_name,
                field_schema=field_schema,
                wait=True,
            )

    async def upsert_documents(
        self,
        documents: list[VectorDocument],
        vectors: list[list[float]],
    ) -> int:
        """
        Загружает документы и их векторы в Qdrant пакетами.

        Возвращает количество обработанных точек.

        Детерминированный UUID5 гарантирует, что повторная
        загрузка того же документа обновит существующую точку,
        а не создаст дубликат.
        """
        if len(documents) != len(vectors):
            raise ValueError(
                "Количество документов не совпадает "
                "с количеством векторов."
            )

        if not documents:
            return 0

        points: list[PointStruct] = []

        for document, vector in zip(
            documents,
            vectors,
            strict=True,
        ):
            if len(vector) != self.embedding_dim:
                raise ValueError(
                    f"Вектор документа {document.check_code} "
                    f"имеет размерность {len(vector)}, "
                    f"ожидалось {self.embedding_dim}."
                )

            point_id = str(
                uuid5(
                    NAMESPACE_URL,
                    (
                        f"{document.source}:"
                        f"{document.check_code}:"
                        f"{document.chunk_type}"
                    ),
                )
            )

            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=document.model_dump(),
                )
            )

        total_points = len(points)

        for batch_start in range(
            0,
            total_points,
            UPSERT_BATCH_SIZE,
        ):
            batch_end = batch_start + UPSERT_BATCH_SIZE
            batch = points[batch_start:batch_end]

            is_last_batch = batch_end >= total_points

            await self.client.upsert(
                collection_name=self.collection,
                points=batch,
                # Ждём завершения обработки последнего пакета.
                wait=is_last_batch,
            )

        return total_points

    async def search(
        self,
        query_vector: list[float],
        limit: int = 5,
        query_filter: Filter | None = None,
    ) -> list[ScoredPoint]:
        """
        Ищет документы, наиболее близкие к вектору запроса.

        query_vector:
            Embedding пользовательского запроса.

        limit:
            Максимальное количество результатов.

        query_filter:
            Необязательный фильтр по payload-полям.
        """
        if len(query_vector) != self.embedding_dim:
            raise ValueError(
                f"Вектор запроса имеет размерность "
                f"{len(query_vector)}, "
                f"ожидалось {self.embedding_dim}."
            )

        if limit <= 0:
            raise ValueError(
                "Параметр limit должен быть больше нуля."
            )

        response = await self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        return response.points

    async def get_points_count(self) -> int:
        """Возвращает количество точек в коллекции."""
        collection_info = await self.client.get_collection(
            collection_name=self.collection,
        )

        return collection_info.points_count or 0

    async def close(self) -> None:
        """Закрывает сетевые соединения клиента Qdrant."""
        await self.client.close()


@lru_cache
def get_vector_store() -> VectorStore:
    """
    Возвращает один экземпляр VectorStore для всего приложения.

    lru_cache не позволяет создавать новый Qdrant-клиент
    при каждом вызове функции.
    """
    settings = get_settings()

    api_key = None

    if settings.qdrant_api_key is not None:
        api_key = settings.qdrant_api_key.get_secret_value()

    return VectorStore(
        url=settings.qdrant_url,
        api_key=api_key,
        collection=settings.qdrant_collection,
        embedding_dim=settings.embedding_dim,
    )