import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from llama_index.core import (  # noqa: E402
    Settings as LlamaIndexSettings,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding  # noqa: E402
from llama_index.vector_stores.qdrant import QdrantVectorStore  # noqa: E402
from qdrant_client import QdrantClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.services.reranker import CrossEncoderReranker  # noqa: E402
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


def build_base_retrieve_fn(
    client: QdrantClient,
    collection_name: str,
    top_k: int,
):
    """
    Создаёт обычный retriever без re-ranker.
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
        return retriever.retrieve(question)

    return retrieve


def build_rerank_retrieve_fn(
    client: QdrantClient,
    collection_name: str,
    candidate_top_k: int,
    rerank_top_n: int,
):
    """
    Создаёт retriever с re-ranker.

    Сначала из Qdrant берём candidate_top_k кандидатов,
    потом cross-encoder пересортировывает их и возвращает rerank_top_n.
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
        similarity_top_k=candidate_top_k,
    )

    reranker = CrossEncoderReranker(
        model_name="BAAI/bge-reranker-v2-m3",
        top_n=rerank_top_n,
    )

    def retrieve(question: str, requested_top_k: int):
        candidates = retriever.retrieve(question)

        return reranker.rerank(
            query=question,
            candidates=candidates,
        )

    return retrieve


def build_reranker_section(results: list[dict[str, Any]]) -> str:
    """
    Формирует markdown-раздел с результатами re-ranker.
    """

    lines = [
        "## Re-ranker",
        "",
        "Для сравнения использовалась лучшая стратегия chunking по результатам предыдущего шага — `recursive`.",
        "",
        "В качестве re-ranker подключён open-source cross-encoder:",
        "",
        "```text",
        "BAAI/bge-reranker-v2-m3",
        "```",
        "",
        "| Эксперимент | Стратегия | Candidate top-K | Rerank top-N | Hit Rate@5 | MRR@10 | Recall@10 | Скорость retrieval, мс |",
        "|-------------|-----------|:---------------:|:------------:|:----------:|:------:|:---------:|:----------------------:|",
    ]

    for item in results:
        lines.append(
            "| "
            f"{item['experiment']} | "
            f"{item['strategy']} | "
            f"{item['candidate_top_k']} | "
            f"{item['rerank_top_n']} | "
            f"{item['hit_rate_at_5']} | "
            f"{item['mrr_at_10']} | "
            f"{item['recall_at_10']} | "
            f"{item['avg_retrieval_ms']} "
            "|"
        )

    lines.extend(
        [
            "",
            "Вывод по re-ranker будет добавлен после анализа полученных чисел.",
            "",
        ]
    )

    return "\n".join(lines)


def update_experiment_doc(results: list[dict[str, Any]]) -> None:
    """
    Обновляет раздел 'Re-ranker' в docs/chunking_experiment.md.
    """

    doc_path = Path("docs/chunking_experiment.md")
    new_section = build_reranker_section(results)

    if not doc_path.exists():
        doc_path.write_text(
            new_section + "\n",
            encoding="utf-8",
        )
        print(f"Создан файл: {doc_path}")
        return

    text = doc_path.read_text(encoding="utf-8")

    start_marker = "## Re-ranker"
    end_marker = "## Подбор параметров"

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

    collection_name = "docs_recursive"
    strategy_name = "recursive"

    candidate_top_k = 20
    rerank_top_n = 10

    client = create_qdrant_client(settings)

    try:
        results = []

        print("=" * 80)
        print("Эксперимент: recursive без re-ranker")

        base_retrieve_fn = build_base_retrieve_fn(
            client=client,
            collection_name=collection_name,
            top_k=rerank_top_n,
        )

        base_metrics = evaluate_retrieval(
            dataset=dataset,
            retrieve_fn=base_retrieve_fn,
            hit_k=5,
            mrr_k=10,
            recall_k=10,
        )

        base_result = {
            "experiment": "Без re-ranker",
            "strategy": strategy_name,
            "candidate_top_k": rerank_top_n,
            "rerank_top_n": "-",
            **base_metrics,
        }

        results.append(base_result)

        print(f"Hit Rate@5: {base_result['hit_rate_at_5']}")
        print(f"MRR@10: {base_result['mrr_at_10']}")
        print(f"Recall@10: {base_result['recall_at_10']}")
        print(f"Скорость retrieval, мс: {base_result['avg_retrieval_ms']}")

        print("=" * 80)
        print("Эксперимент: recursive + re-ranker")
        print("Первый запуск может быть долгим: модель re-ranker может скачиваться.")

        rerank_retrieve_fn = build_rerank_retrieve_fn(
            client=client,
            collection_name=collection_name,
            candidate_top_k=candidate_top_k,
            rerank_top_n=rerank_top_n,
        )

        rerank_metrics = evaluate_retrieval(
            dataset=dataset,
            retrieve_fn=rerank_retrieve_fn,
            hit_k=5,
            mrr_k=10,
            recall_k=10,
        )

        rerank_result = {
            "experiment": "С re-ranker",
            "strategy": strategy_name,
            "candidate_top_k": candidate_top_k,
            "rerank_top_n": rerank_top_n,
            **rerank_metrics,
        }

        results.append(rerank_result)

        print(f"Hit Rate@5: {rerank_result['hit_rate_at_5']}")
        print(f"MRR@10: {rerank_result['mrr_at_10']}")
        print(f"Recall@10: {rerank_result['recall_at_10']}")
        print(f"Скорость retrieval, мс: {rerank_result['avg_retrieval_ms']}")

        update_experiment_doc(results)

    finally:
        client.close()


if __name__ == "__main__":
    main()
