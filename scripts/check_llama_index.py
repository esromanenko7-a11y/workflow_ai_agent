from llama_index.core import (
    Settings,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from app.core.config import get_settings


settings = get_settings()


def main() -> None:
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=(
            settings.qdrant_api_key.get_secret_value()
            if settings.qdrant_api_key
            else None
        ),
        trust_env=False,
    )

    print("Читаем документы...")

    documents = SimpleDirectoryReader(
        input_dir=str(settings.rag_data_dir),
        recursive=True,
    ).load_data()

    Settings.embed_model = HuggingFaceEmbedding(
        model_name=settings.embedding_model,
    )

    Settings.node_parser = SentenceSplitter(
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
    )

    vector_store = QdrantVectorStore(
        client=client,
        collection_name=settings.rag_collection,
    )

    storage_context = StorageContext.from_defaults(
        vector_store=vector_store,
    )

    print("Создаём индекс...")

    VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
    )

    collection_info = client.get_collection(
        collection_name=settings.rag_collection,
    )

    print()
    print(f"Документов прочитано: {len(documents)}")
    print(f"Точек в коллекции: {collection_info.points_count}")
    print("Индекс успешно создан.")

    client.close()


if __name__ == "__main__":
    main()