import asyncio

from app.services.document_generator import generate_documents
from app.services.embeddings import get_embedding_service
from app.services.vector_store import get_vector_store


async def main() -> None:
    print("=== Загрузка каталога проверок ===")

    # 1. Генерируем документы
    documents = generate_documents()
    print(f"Документов: {len(documents)}")

    # 2. Создаём embeddings
    embedding_service = get_embedding_service()

    print("Создаём embeddings...")

    vectors = embedding_service.embed_documents(
        [document.text for document in documents]
    )

    print(f"Embeddings: {len(vectors)}")

    # 3. Получаем VectorStore
    vector_store = get_vector_store()

    await vector_store.ensure_collection()

    # 4. Загружаем документы
    await vector_store.upsert_documents(
        documents,
        vectors,
    )

    print("Каталог успешно загружен в Qdrant.")

    await vector_store.close()


if __name__ == "__main__":
    asyncio.run(main())