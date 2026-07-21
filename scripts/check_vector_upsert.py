import asyncio

from app.schemas.vector_document import VectorDocument
from app.services.embeddings import get_embedding_service
from app.services.vector_store import get_vector_store


async def main() -> None:
    documents = [
        VectorDocument(
            source="validation_catalog",
            check_code="CHECK_REQUIRED_FILES",
            check_name="Проверка обязательных файлов",
            category="package_structure",
            severity="error",
            chunk_type="description",
            text=(
                "Проверка контролирует наличие всех обязательных "
                "файлов в пакете данных."
            ),
        ),
        VectorDocument(
            source="validation_catalog",
            check_code="CHECK_REQUIRED_FILES",
            check_name="Проверка обязательных файлов",
            category="package_structure",
            severity="error",
            chunk_type="recommendation",
            text=(
                "Добавьте отсутствующий обязательный файл "
                "и повторно запустите проверку."
            ),
        ),
    ]

    embedding_service = get_embedding_service()
    vector_store = get_vector_store()

    try:
        await vector_store.ensure_collection()

        vectors = embedding_service.embed_documents(
            [document.text for document in documents]
        )

        uploaded_count = await vector_store.upsert_documents(
            documents=documents,
            vectors=vectors,
        )

        collection_info = await vector_store.client.get_collection(
            collection_name=vector_store.collection,
        )

        print("Upsert: OK")
        print(f"Uploaded: {uploaded_count}")
        print(f"Points count: {collection_info.points_count}")
    finally:
        await vector_store.close()


if __name__ == "__main__":
    asyncio.run(main())