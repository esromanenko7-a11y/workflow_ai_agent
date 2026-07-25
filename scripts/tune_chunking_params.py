import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from llama_index.core import (  # noqa: E402
    Settings as LlamaIndexSettings,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.core.node_parser.interface import NodeParser  # noqa: E402
from llama_index.embeddings.huggingface import HuggingFaceEmbedding  # noqa: E402
from llama_index.vector_stores.qdrant import QdrantVectorStore  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.services.chunking import recursive  # noqa: E402
from app.services.retrieval_eval import (  # noqa: E402
    evaluate_retrieval,
    load_retrieval_dataset,
)


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


def recreate_collection(
    client: QdrantClient,
    collection_name: str,
) -> None:
    if client.collection_exists(collection_name=collection_name):
        print(f"Удаляем старую коллекцию: {collection_name}")
        client.delete_collection(collection_name=collection_name)


def calculate_avg_chunk_length(nodes: list[Any]) -> float:
    if not nodes:
        return 0.0

    lengths = [
        len(node.get_content())
        for node in nodes
    ]

    return round(sum(lengths) / len(lengths), 2)


def index_experiment(
    client: QdrantClient,
    collection_name: str,
    parser: NodeParser,
    documents: list[Any],
) -> dict[str, Any]:
    recreate_collection(
        client=client,
        collection_name=collection_name,
    )

    nodes = parser.get_nodes_from_documents(documents)

    vector_store = QdrantVectorStore(
        client=client,
        collection_name=collection_name,
    )

    storage_context = StorageContext.from_defaults(
        vector_store=vector_store,
    )

    VectorStoreIndex(
        nodes,
        storage_context=storage_context,
        show_progress=True,
    )

    return {
        "total_chunks": len(nodes),
        "avg_chunk_length": calculate_avg_chunk_length(nodes),
    }


def build_retrieve_fn(
    client: QdrantClient,
    collection_name: str,
    top_k: int,
):
    vector_store = QdrantVectorStore(
        client=client,
        collection_name=collection_name,
    )

    storage_context = StorageContext.from_defaults(
        vector_store=vector_store,
    )

    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store,
        storage_context=storage_context,
    )

    retriever = index.as_retriever(
        similarity_top_k=top_k,
    )

    def retrieve(question: str, requested_top_k: int):
        return retriever.retrieve(question)

    return retrieve


def build_tuning_section(results: list[dict[str, Any]]) -> str:
    lines = [
        "## Подбор параметров",
        "",
        "Для подбора параметров использовалась лучшая базовая стратегия chunking — `recursive`.",
        "",
        "| Эксперимент | Коллекция | chunk_size | overlap | top-K | Чанков | Средняя длина chunk | Hit Rate@5 | MRR@10 | Recall@10 | Скорость retrieval, мс |",
        "|-------------|-----------|:----------:|:-------:|:-----:|:------:|:-------------------:|:----------:|:------:|:---------:|:----------------------:|",
    ]

    for item in results:
        lines.append(
            "| "
            f"{item['experiment']} | "
            f"`{item['collection']}` | "
            f"{item['chunk_size']} | "
            f"{item['overlap']} | "
            f"{item['top_k']} | "
            f"{item['total_chunks']} | "
            f"{item['avg_chunk_length']} | "
            f"{item['hit_rate_at_5']} | "
            f"{item['mrr_at_10']} | "
            f"{item['recall_at_10']} | "
            f"{item['avg_retrieval_ms']} "
            "|"
        )

    lines.extend(
        [
            "",
            "Итоговая конфигурация будет выбрана после анализа результатов.",
            "",
        ]
    )

    return "\n".join(lines)


def update_experiment_doc(results: list[dict[str, Any]]) -> None:
    doc_path = Path("docs/chunking_experiment.md")
    new_section = build_tuning_section(results)

    if not doc_path.exists():
        doc_path.write_text(
            new_section + "\n",
            encoding="utf-8",
        )
        print(f"Создан файл: {doc_path}")
        return

    text = doc_path.read_text(encoding="utf-8")

    start_marker = "## Подбор параметров"
    end_marker = "## Итоговый выбор"

    if start_marker in text and end_marker in text:
        before = text.split(start_marker)[0]
        after = text.split(end_marker, maxsplit=1)[1]

        updated_text = (
            before
            + new_section
            + "\n"
            + end_marker
            + after
        )
    else:
        updated_text = text.rstrip() + "\n\n" + new_section + "\n"

    doc_path.write_text(
        updated_text,
        encoding="utf-8",
    )

    print(f"Обновлён файл: {doc_path}")


def main() -> None:
    settings = get_settings()

    dataset = load_retrieval_dataset(
        Path("tests/eval/retrieval_dataset.json"),
    )

    print(f"Вопросов в golden dataset: {len(dataset)}")

    embed_model = HuggingFaceEmbedding(
        model_name=settings.embedding_model,
    )

    LlamaIndexSettings.embed_model = embed_model

    documents = SimpleDirectoryReader(
        input_dir=str(settings.rag_data_dir),
        recursive=True,
    ).load_data()

    print(f"Документов в корпусе: {len(documents)}")

    experiments = [
        {
            "experiment": "recursive_256_32_top10",
            "collection": "docs_recursive_256_32_top10",
            "chunk_size": 256,
            "overlap": 32,
            "top_k": 10,
        },
        {
            "experiment": "recursive_256_64_top10",
            "collection": "docs_recursive_256_64_top10",
            "chunk_size": 256,
            "overlap": 64,
            "top_k": 10,
        },
        {
            "experiment": "recursive_512_32_top10",
            "collection": "docs_recursive_512_32_top10",
            "chunk_size": 512,
            "overlap": 32,
            "top_k": 10,
        },
        {
            "experiment": "recursive_512_64_top10",
            "collection": "docs_recursive_512_64_top10",
            "chunk_size": 512,
            "overlap": 64,
            "top_k": 10,
        },
        {
            "experiment": "recursive_256_32_top20",
            "collection": "docs_recursive_256_32_top20",
            "chunk_size": 256,
            "overlap": 32,
            "top_k": 20,
        },
        {
            "experiment": "recursive_512_64_top20",
            "collection": "docs_recursive_512_64_top20",
            "chunk_size": 512,
            "overlap": 64,
            "top_k": 20,
        },
    ]

    client = create_qdrant_client(settings)

    try:
        results = []

        for item in experiments:
            print("=" * 80)
            print(f"Эксперимент: {item['experiment']}")
            print(f"Коллекция: {item['collection']}")
            print(f"chunk_size: {item['chunk_size']}")
            print(f"overlap: {item['overlap']}")
            print(f"top-K: {item['top_k']}")

            parser = recursive(
                chunk_size=item["chunk_size"],
                chunk_overlap=item["overlap"],
            )

            index_stats = index_experiment(
                client=client,
                collection_name=item["collection"],
                parser=parser,
                documents=documents,
            )

            retrieve_fn = build_retrieve_fn(
                client=client,
                collection_name=item["collection"],
                top_k=item["top_k"],
            )

            metrics = evaluate_retrieval(
                dataset=dataset,
                retrieve_fn=retrieve_fn,
                hit_k=5,
                mrr_k=10,
                recall_k=10,
            )

            result = {
                **item,
                **index_stats,
                **metrics,
            }

            results.append(result)

            print(f"Чанков: {result['total_chunks']}")
            print(f"Средняя длина chunk: {result['avg_chunk_length']}")
            print(f"Hit Rate@5: {result['hit_rate_at_5']}")
            print(f"MRR@10: {result['mrr_at_10']}")
            print(f"Recall@10: {result['recall_at_10']}")
            print(f"Скорость retrieval, мс: {result['avg_retrieval_ms']}")

        update_experiment_doc(results)

    finally:
        client.close()


if __name__ == "__main__":
    main()