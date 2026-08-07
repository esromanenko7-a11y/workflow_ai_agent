import json
from pathlib import Path
from typing import Any

from llama_index.core.ingestion import DocstoreStrategy, IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from app.core.config import get_settings
from app.services.ingestion import load_documents_from_directory


DOCSTORE_PATH = Path(".cache/rag_docstore.json")
MANIFEST_PATH = Path(".cache/rag_ingestion_manifest.json")


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


def load_previous_manifest() -> dict[str, dict[str, Any]]:
    if not MANIFEST_PATH.exists():
        return {}

    with MANIFEST_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_manifest(manifest: dict[str, dict[str, Any]]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)

    with MANIFEST_PATH.open("w", encoding="utf-8") as file:
        json.dump(
            manifest,
            file,
            ensure_ascii=False,
            indent=2,
        )


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


def mark_failed_files(
    failed_files: list[dict[str, str]],
) -> list[dict[str, str]]:
    marked_files = []

    for item in failed_files:
        file_path = Path(item["file_path"])

        if not file_path.exists():
            marked_files.append(item)
            continue

        failed_path = file_path.with_name(f"{file_path.name}.failed")
        counter = 1

        while failed_path.exists():
            failed_path = file_path.with_name(
                f"{file_path.name}.{counter}.failed"
            )
            counter += 1

        file_path.rename(failed_path)

        marked_item = {
            **item,
            "failed_path": str(failed_path),
        }
        marked_files.append(marked_item)

    return marked_files


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


def run_ingestion_pipeline(data_dir: str | Path) -> dict[str, Any]:
    settings = get_settings()
    data_path = Path(data_dir)

    documents, failed_files = load_documents_from_directory(data_path)
    marked_failed_files = mark_failed_files(failed_files)

    previous_manifest = load_previous_manifest()
    current_manifest = build_current_manifest(documents)

    manifest_stats = calculate_manifest_stats(
        previous=previous_manifest,
        current=current_manifest,
    )

    if not documents:
        return {
            "documents": 0,
            "nodes": 0,
            "failed_files": marked_failed_files,
            "manifest": manifest_stats,
        }

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
        save_manifest(current_manifest)

        result = {
            "documents": len(documents),
            "nodes": len(nodes),
            "failed_files": marked_failed_files,
            "manifest": manifest_stats,
            "collection": settings.rag_collection,
        }

        print(f"Background ingestion completed: {result}")

        return result

    finally:
        client.close()