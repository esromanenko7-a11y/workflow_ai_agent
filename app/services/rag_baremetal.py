import asyncio
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from openai import OpenAI
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.core.config import get_settings
from app.services.embeddings import get_embedding_service


SUPPORTED_SUFFIXES = {".md", ".txt"}
UPSERT_BATCH_SIZE = 128


class BareMetalRAGService:
    """
    RAG без LlamaIndex.

    Весь pipeline выполняется вручную:

    1. Чтение файлов.
    2. Наивный чанкинг.
    3. Создание эмбеддингов.
    4. Загрузка в Qdrant.
    5. Поиск через query_points().
    6. Сборка промпта.
    7. Вызов LLM.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.embedding_service = get_embedding_service()

        api_key = (
            self.settings.qdrant_api_key.get_secret_value()
            if self.settings.qdrant_api_key
            else None
        )

        self.qdrant_client = AsyncQdrantClient(
            url=self.settings.qdrant_url,
            api_key=api_key,
        )

        self.llm_client = OpenAI(
            base_url=self.settings.llm.openai_base_url,
            api_key=self.settings.llm.openai_api_key.get_secret_value(),
            timeout=self.settings.llm.request_timeout,
        )

    def _read_files(self) -> list[tuple[Path, str]]:
        """
        Читает все .md и .txt файлы корпуса.

        Возвращает список пар:
        (путь к файлу, содержимое файла).
        """
        data_dir = self.settings.rag_data_dir

        if not data_dir.exists():
            raise FileNotFoundError(
                f"Папка корпуса не найдена: {data_dir}"
            )

        documents: list[tuple[Path, str]] = []

        for file_path in sorted(data_dir.rglob("*")):
            if not file_path.is_file():
                continue

            if file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue

            text = file_path.read_text(
                encoding="utf-8",
            ).strip()

            if text:
                documents.append(
                    (file_path, text)
                )

        return documents

    def _split_text(self, text: str) -> list[str]:
        """
        Наивно разбивает текст по словам.

        rag_chunk_size:
            максимальное количество слов в чанке.

        rag_chunk_overlap:
            количество слов, повторяющихся между соседними чанками.

        Это упрощённый аналог SentenceSplitter.
        """
        words = text.split()

        if not words:
            return []

        chunk_size = self.settings.rag_chunk_size
        chunk_overlap = self.settings.rag_chunk_overlap

        if chunk_overlap >= chunk_size:
            raise ValueError(
                "RAG_CHUNK_OVERLAP должен быть меньше "
                "RAG_CHUNK_SIZE."
            )

        chunks: list[str] = []
        step = chunk_size - chunk_overlap

        for start in range(0, len(words), step):
            end = start + chunk_size
            chunk_words = words[start:end]

            if not chunk_words:
                break

            chunks.append(
                " ".join(chunk_words)
            )

            if end >= len(words):
                break

        return chunks

    async def _ensure_collection(self) -> bool:
        """
        Создаёт bare-metal коллекцию, если её нет.

        Возвращает True, если коллекция уже содержит точки.
        """
        collection_name = (
            self.settings.rag_baremetal_collection
        )

        collection_exists = await self.qdrant_client.collection_exists(
            collection_name=collection_name,
        )

        if not collection_exists:
            await self.qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=self.settings.embedding_dim,
                    distance=Distance.COSINE,
                ),
            )

            return False

        collection_info = await self.qdrant_client.get_collection(
            collection_name=collection_name,
        )

        vectors_config = collection_info.config.params.vectors
        actual_dimension = vectors_config.size

        if actual_dimension != self.settings.embedding_dim:
            raise ValueError(
                "Размерность bare-metal коллекции не совпадает "
                "с EMBEDDING_DIM: "
                f"{actual_dimension} != "
                f"{self.settings.embedding_dim}."
            )

        return (collection_info.points_count or 0) > 0

    async def build(self) -> None:
        """
        Индексирует корпус при первом запуске.

        Если коллекция уже заполнена, повторная индексация
        не выполняется.
        """
        collection_has_points = await self._ensure_collection()

        if collection_has_points:
            print(
                "Подключаемся к готовой bare-metal коллекции "
                f"{self.settings.rag_baremetal_collection}."
            )
            return

        documents = self._read_files()

        points: list[PointStruct] = []
        all_chunks_count = 0

        for file_path, document_text in documents:
            chunks = self._split_text(document_text)

            vectors = self.embedding_service.embed_documents(
                chunks
            )

            for chunk_index, (chunk, vector) in enumerate(
                zip(chunks, vectors, strict=True)
            ):
                point_id = str(
                    uuid5(
                        NAMESPACE_URL,
                        (
                            f"{file_path.as_posix()}:"
                            f"{chunk_index}:"
                            f"{chunk}"
                        ),
                    )
                )

                points.append(
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "text": chunk,
                            "source": file_path.name,
                            "file_path": str(file_path),
                            "chunk_index": chunk_index,
                        },
                    )
                )

                all_chunks_count += 1

        for batch_start in range(
            0,
            len(points),
            UPSERT_BATCH_SIZE,
        ):
            batch = points[
                batch_start:
                batch_start + UPSERT_BATCH_SIZE
            ]

            await self.qdrant_client.upsert(
                collection_name=(
                    self.settings.rag_baremetal_collection
                ),
                points=batch,
                wait=True,
            )

        print(f"Документов прочитано: {len(documents)}")
        print(f"Чанков загружено: {all_chunks_count}")

    async def answer(
        self,
        question: str,
    ) -> dict[str, Any]:
        """
        Выполняет поиск и формирует ответ через LLM.
        """
        clean_question = question.strip()

        if not clean_question:
            raise ValueError(
                "Вопрос не должен быть пустым."
            )

        query_vector = self.embedding_service.embed_query(
            clean_question
        )

        search_response = await self.qdrant_client.query_points(
            collection_name=(
                self.settings.rag_baremetal_collection
            ),
            query=query_vector,
            limit=self.settings.rag_similarity_top_k,
            with_payload=True,
            with_vectors=False,
        )

        points = search_response.points

        sources: list[dict[str, Any]] = []
        context_parts: list[str] = []

        for point in points:
            payload = point.payload or {}
            text = str(payload.get("text", ""))
            source = payload.get("source")

            sources.append(
                {
                    "text": text[:300],
                    "source": source,
                    "score": round(point.score, 3),
                }
            )

            context_parts.append(
                f"Источник: {source}\n{text}"
            )

        context = "\n\n---\n\n".join(
            context_parts
        )

        system_prompt = (
            "Ты отвечаешь только на основании переданного контекста. "
            "Не добавляй факты, которых нет в контексте. "
            "Если в контексте недостаточно информации, честно скажи: "
            "«В базе знаний не нашлось информации для ответа»."
        )

        user_prompt = (
            f"Контекст:\n{context}\n\n"
            f"Вопрос:\n{clean_question}"
        )

        response = self.llm_client.chat.completions.create(
            model=self.settings.llm.default_model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            temperature=0,
        )

        answer_text = (
            response.choices[0].message.content
            or ""
        )

        top_score = (
            points[0].score
            if points
            else 0.0
        )

        return {
            "answer": answer_text,
            "top_score": round(top_score, 3),
            "sources": sources,
        }

    async def close(self) -> None:
        """
        Закрывает соединения и кеш эмбеддингов.
        """
        await self.qdrant_client.close()
        self.embedding_service.close()


async def main() -> None:
    service = BareMetalRAGService()

    try:
        await service.build()

        result = await service.answer(
            "Какие обязательные технические поля "
            "должны быть в meta-файле?"
        )

        print()
        print(result)

    finally:
        await service.close()


if __name__ == "__main__":
    asyncio.run(main())