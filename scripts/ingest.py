import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from llama_index.core.ingestion import DocstoreStrategy, IngestionPipeline  # noqa: E402
from llama_index.core.node_parser import SentenceSplitter  # noqa: E402
from llama_index.core.storage.docstore import SimpleDocumentStore  # noqa: E402
from llama_index.embeddings.huggingface import HuggingFaceEmbedding  # noqa: E402
from llama_index.vector_stores.qdrant import QdrantVectorStore  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.services.ingestion import load_documents_from_directory  # noqa: E402


DOCSTORE_PATH = Path(".cache/rag_docstore.json")


def create_qdrant_client(settings: Any) -> QdrantClient:
    api_key = (
        settings.qdrant_api_key.get_secret_value()
        if settings.qdrant_api_key
        else None
    )

    return QdrantClient(
        url=settings.qdrant_url,
        api_key=api_key,
        trust_env=False,
    )


def load_docstore() -> SimpleDocumentStore:
    DOCSTORE_PATH.parent.mkdir(parents=True, exist_ok=True)

    if DOCSTORE_PATH.exists():
        return SimpleDocumentStore.from_persist_path(
            persist_path=str(DOCSTORE_PATH),
        )

    return SimpleDocumentStore()


def persist_docstore(docstore: SimpleDocumentStore) -> None:
    DOCSTORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    docstore.persist(persist_path=str(DOCSTORE_PATH))


def load_previous_manifest(manifest_path: Path) -> dict[str, dict[str, Any]]:
    if not manifest_path.exists():
        return {}

    with manifest_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def build_current_manifest(documents: list[Any]) -> dict[str, dict[str, Any]]:
    manifest = {}

    for document in documents:
        document_id = document.metadata["document_id"]

        manifest[document_id] = {
            "file_path": document.metadata.get("file_path"),
            "last_modified": document.metadata.get("last_modified"),
            "file_size_bytes": document.metadata.get("file_size_bytes"),
        }

    return manifest


def calculate_manifest_stats(
    previous: dict[str, dict[str, Any]],
    current: dict[str, dict[str, Any]],
) -> dict[str, int]:
    changed = 0
    unchanged = 0

    for document_id, current_item in current.items():
        previous_item = previous.get(document_id)

        if previous_item == current_item:
            unchanged += 1
        else:
            changed += 1

    deleted = len(set(previous) - set(current))

    return {
        "changed": changed,
        "unchanged": unchanged,
        "deleted": deleted,
    }


def save_manifest(
    manifest_path: Path,
    manifest: dict[str, dict[str, Any]],
) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    with manifest_path.open("w", encoding="utf-8") as file:
        json.dump(
            manifest,
            file,
            ensure_ascii=False,
            indent=2,
        )


def build_pipeline(
    settings: Any,
    client: QdrantClient,
    docstore: SimpleDocumentStore,
) -> IngestionPipeline:
    vector_store = QdrantVectorStore(
        client=client,
        collection_name=settings.rag_collection,
    )

    splitter = SentenceSplitter(
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
    )

    embed_model = HuggingFaceEmbedding(
        model_name=settings.embedding_model,
    )

    return IngestionPipeline(
        transformations=[
            splitter,
            embed_model,
        ],
        docstore=docstore,
        vector_store=vector_store,
        docstore_strategy=DocstoreStrategy.UPSERTS,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Индексация документов для корпоративного RAG.",
    )

    parser.add_argument(
        "data_dir",
        type=str,
        help="Папка с документами, например: data",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()

    data_dir = Path(args.data_dir)

    documents, failed_files = load_documents_from_directory(data_dir)

    print(f"Папка с документами: {data_dir}")
    print(f"Загружено документов LlamaIndex: {len(documents)}")
    print(f"Ошибок чтения файлов: {len(failed_files)}")

    if failed_files:
        print("Файлы с ошибками:")
        for item in failed_files:
            print(f"- {item['file_path']}: {item['error']}")

    manifest_path = Path(".cache/rag_ingestion_manifest.json")
    previous_manifest = load_previous_manifest(manifest_path)
    current_manifest = build_current_manifest(documents)

    manifest_stats = calculate_manifest_stats(
        previous=previous_manifest,
        current=current_manifest,
    )

    print(
        "Изменения документов: "
        f"{manifest_stats['changed']} changed, "
        f"{manifest_stats['unchanged']} unchanged, "
        f"{manifest_stats['deleted']} deleted"
    )

    if not documents:
        print("Нет документов для индексации.")
        return

    docstore = load_docstore()
    client = create_qdrant_client(settings)

    try:
        pipeline = build_pipeline(
            settings=settings,
            client=client,
            docstore=docstore,
        )

        nodes = pipeline.run(
            documents=documents,
            show_progress=True,
        )

        persist_docstore(docstore)
        save_manifest(
            manifest_path=manifest_path,
            manifest=current_manifest,
        )

        print(f"Коллекция Qdrant: {settings.rag_collection}")
        print(f"Создано или обновлено чанков: {len(nodes)}")
        print(f"Docstore сохранён: {DOCSTORE_PATH}")

    finally:
        client.close()


if __name__ == "__main__":
    main()