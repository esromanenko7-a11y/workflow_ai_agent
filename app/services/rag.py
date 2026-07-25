from typing import Any

from llama_index.core import (
    Settings as LlamaIndexSettings,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from app.core.config import get_settings


class RAGService:
    """
    RAG-сервис на LlamaIndex.

    build() создаёт индекс при первом запуске
    или подключается к уже заполненной коллекции.

    answer() принимает вопрос и возвращает:
    - ответ;
    - максимальный score;
    - найденные источники.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

        self.client: QdrantClient | None = None
        self.vector_store: QdrantVectorStore | None = None
        self.index: VectorStoreIndex | None = None
        self.query_engine: Any | None = None

    def _configure_llama_index(self) -> None:
        """
        Настраивает компоненты LlamaIndex:
        embed-модель, LLM и чанкинг.
        """

        LlamaIndexSettings.embed_model = HuggingFaceEmbedding(
            model_name=self.settings.embedding_model,
        )

        LlamaIndexSettings.llm = Ollama(
            model=self.settings.llm.default_model,
            base_url=self.settings.llm.ollama_base_url,
            request_timeout=self.settings.llm.request_timeout,
        )

        LlamaIndexSettings.node_parser = SentenceSplitter(
            chunk_size=self.settings.rag_chunk_size,
            chunk_overlap=self.settings.rag_chunk_overlap,
        )

    def _create_qdrant_client(self) -> QdrantClient:
        """
        Создаёт синхронный клиент Qdrant.
        """

        api_key = (
            self.settings.qdrant_api_key.get_secret_value()
            if self.settings.qdrant_api_key
            else None
        )

        return QdrantClient(
            url=self.settings.qdrant_url,
            api_key=api_key,
            trust_env=False,
        )

    def build(self) -> None:
        """
        Инициализирует RAG.

        Если коллекция отсутствует или пуста:
        читает документы и индексирует их.

        Если коллекция уже заполнена:
        подключается без повторной индексации.
        """

        self._configure_llama_index()
        self.client = self._create_qdrant_client()

        collection_exists = self.client.collection_exists(
            collection_name=self.settings.rag_collection,
        )

        collection_has_points = False

        if collection_exists:
            collection_info = self.client.get_collection(
                collection_name=self.settings.rag_collection,
            )

            collection_has_points = (
                collection_info.points_count is not None
                and collection_info.points_count > 0
            )

        self.vector_store = QdrantVectorStore(
            client=self.client,
            collection_name=self.settings.rag_collection,
        )

        storage_context = StorageContext.from_defaults(
            vector_store=self.vector_store,
        )

        if collection_has_points:
            print(
                f"Подключаемся к готовой коллекции "
                f"{self.settings.rag_collection}."
            )

            self.index = VectorStoreIndex.from_vector_store(
                vector_store=self.vector_store,
                storage_context=storage_context,
            )

        else:
            print(
                f"Индексируем документы в коллекцию "
                f"{self.settings.rag_collection}."
            )

            documents = SimpleDirectoryReader(
                input_dir=str(self.settings.rag_data_dir),
                recursive=True,
            ).load_data()

            self.index = VectorStoreIndex.from_documents(
                documents,
                storage_context=storage_context,
            )

            print(f"Прочитано документов: {len(documents)}")

        self.query_engine = self.index.as_query_engine(
            similarity_top_k=self.settings.rag_similarity_top_k,
        )

    def answer(self, question: str) -> dict[str, Any]:
        """
        Выполняет RAG-запрос.

        Возвращает словарь в формате домашнего задания.
        """

        if not question.strip():
            raise ValueError("Вопрос не должен быть пустым.")

        if self.query_engine is None:
            raise RuntimeError(
                "RAGService ещё не инициализирован. "
                "Сначала вызовите build()."
            )

        response = self.query_engine.query(question)
        source_nodes = response.source_nodes

        if source_nodes and source_nodes[0].score is not None:
            top_score = source_nodes[0].score
        else:
            top_score = 0.0

        sources = []

        for node in source_nodes:
            score = node.score if node.score is not None else 0.0

            sources.append(
                {
                    "text": node.text[:300],
                    "source": node.metadata.get("file_name"),
                    "score": round(score, 3),
                }
            )

        return {
            "answer": str(response),
            "top_score": round(top_score, 3),
            "sources": sources,
        }

    def close(self) -> None:
        """
        Закрывает соединение с Qdrant.
        """

        if self.client is not None:
            self.client.close()


def main() -> None:
    """
    Проверка отдельного запуска:

    python -m app.services.rag
    """

    rag_service = RAGService()

    try:
        rag_service.build()

        result = rag_service.answer(
            "Какие обязательные технические поля "
            "должны быть в meta-файле?"
        )

        print()
        print(result)

    finally:
        rag_service.close()


if __name__ == "__main__":
    main()