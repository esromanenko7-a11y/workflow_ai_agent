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
from app.services.chunking import fixed_size, recursive, semantic  # noqa: E402
from app.services.retrieval_eval import (  # noqa: E402
    evaluate_retrieval,
    load_retrieval_dataset,
)


def create_qdrant_client(settings: Any) -> QdrantClient:
    """
    Создаёт Qdrant-клиент с настройками проекта.
    """

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


def calculate_avg_chunk_length(
    parser: NodeParser,
    documents: list[Any],
) -> float:
    """
    Считает среднюю длину чанка в символах.

    Это нужно для обязательной колонки в отчёте:
    "Средняя длина chunk".
    """

    nodes = parser.get_nodes_from_documents(documents)

    if not nodes:
        return 0.0

    lengths = [
        len(node.get_content())
        for node in nodes
    ]

    return round(sum(lengths) / len(lengths), 2)


def build_retrieve_fn(
    client: QdrantClient,
    collection_name: str,
    top_k: int,
):
    """
    Создаёт функцию поиска по конкретной коллекции Qdrant.

    Эта функция потом передаётся в evaluate_retrieval().
    """

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
        """
        requested_top_k нужен для общего интерфейса evaluate_retrieval().
        В этом эксперименте retriever уже создан с нужным top_k.
        """

        return retriever.retrieve(question)

    return retrieve


def build_results_table(results: list[dict[str, Any]]) -> str:
    """
    Формирует markdown-таблицу с результатами retrieval evaluation.
    """

    lines = [
        "## Результаты retrieval evaluation",
        "",
        "| Стратегия | Hit Rate@5 | MRR@10 | Recall@10 | Средняя длина chunk | Скорость retrieval, мс |",
        "|-----------|:----------:|:------:|:---------:|:-------------------:|:----------------------:|",
    ]

    for item in results:
        lines.append(
            "| "
            f"{item['strategy']} | "
            f"{item['hit_rate_at_5']} | "
            f"{item['mrr_at_10']} | "
            f"{item['recall_at_10']} | "
            f"{item['avg_chunk_length']} | "
            f"{item['avg_retrieval_ms']} "
            "|"
        )

    lines.append("")

    return "\n".join(lines)


def update_experiment_doc(results: list[dict[str, Any]]) -> None:
    """
    Обновляет раздел 'Результаты retrieval evaluation'
    в docs/chunking_experiment.md.
    """

    doc_path = Path("docs/chunking_experiment.md")
    new_section = build_results_table(results)

    if not doc_path.exists():
        doc_path.write_text(
            new_section + "\n",
            encoding="utf-8",
        )
        print(f"Создан файл: {doc_path}")
        return

    text = doc_path.read_text(encoding="utf-8")

    start_marker = "## Результаты retrieval evaluation"
    end_marker = "## Re-ranker"

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

    dataset_path = Path("tests/eval/retrieval_dataset.json")
    dataset = load_retrieval_dataset(dataset_path)

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

    top_k = 10

    strategies = [
        {
            "strategy": "fixed",
            "collection": "docs_fixed",
            "parser": fixed_size(
                chunk_size=512,
                chunk_overlap=64,
            ),
        },
        {
            "strategy": "recursive",
            "collection": "docs_recursive",
            "parser": recursive(
                chunk_size=512,
                chunk_overlap=64,
            ),
        },
        {
            "strategy": "semantic",
            "collection": "docs_semantic",
            "parser": semantic(
                embed_model=embed_model,
                buffer_size=1,
                breakpoint_percentile_threshold=95,
            ),
        },
    ]

    client = create_qdrant_client(settings)

    try:
        results = []

        for item in strategies:
            print("=" * 80)
            print(f"Оцениваем стратегию: {item['strategy']}")
            print(f"Коллекция: {item['collection']}")

            avg_chunk_length = calculate_avg_chunk_length(
                parser=item["parser"],
                documents=documents,
            )

            retrieve_fn = build_retrieve_fn(
                client=client,
                collection_name=item["collection"],
                top_k=top_k,
            )

            metrics = evaluate_retrieval(
                dataset=dataset,
                retrieve_fn=retrieve_fn,
                hit_k=5,
                mrr_k=10,
                recall_k=10,
            )

            result = {
                "strategy": item["strategy"],
                "collection": item["collection"],
                "avg_chunk_length": avg_chunk_length,
                **metrics,
            }

            results.append(result)

            print(f"Hit Rate@5: {result['hit_rate_at_5']}")
            print(f"MRR@10: {result['mrr_at_10']}")
            print(f"Recall@10: {result['recall_at_10']}")
            print(f"Средняя длина chunk: {result['avg_chunk_length']}")
            print(f"Средняя скорость retrieval, мс: {result['avg_retrieval_ms']}")

        update_experiment_doc(results)

    finally:
        client.close()


if __name__ == "__main__":
    main()