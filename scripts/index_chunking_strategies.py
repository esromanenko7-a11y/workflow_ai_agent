import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from llama_index.core import (
    Settings as LlamaIndexSettings,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.core.node_parser.interface import NodeParser
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from app.core.config import get_settings
from app.services.chunking import fixed_size, recursive, semantic


def create_qdrant_client(settings: Any) -> QdrantClient:
    """
    Создаёт клиента Qdrant.

    trust_env=False нужен, чтобы Qdrant-клиент не брал proxy-настройки
    из окружения Windows/PowerShell.
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


def recreate_collection(
    client: QdrantClient,
    collection_name: str,
) -> None:
    """
    Удаляет коллекцию, если она уже существует.

    Это нужно для честного эксперимента:
    каждый запуск создаёт коллекцию заново,
    а не добавляет новые чанки поверх старых.
    """

    if client.collection_exists(collection_name=collection_name):
        print(f"Удаляем старую коллекцию: {collection_name}")
        client.delete_collection(collection_name=collection_name)


def calculate_chunk_stats(
    strategy_name: str,
    collection_name: str,
    documents_count: int,
    nodes: list[Any],
) -> dict[str, Any]:
    """
    Считает статистику чанков для отчёта.
    """

    total_chunks = len(nodes)

    if documents_count > 0:
        avg_chunks_per_document = total_chunks / documents_count
    else:
        avg_chunks_per_document = 0

    chunk_lengths = [
        len(node.get_content())
        for node in nodes
    ]

    if chunk_lengths:
        avg_chunk_length = sum(chunk_lengths) / len(chunk_lengths)
    else:
        avg_chunk_length = 0

    return {
        "strategy": strategy_name,
        "collection": collection_name,
        "documents_count": documents_count,
        "total_chunks": total_chunks,
        "avg_chunks_per_document": round(avg_chunks_per_document, 2),
        "avg_chunk_length": round(avg_chunk_length, 2),
    }


def index_strategy(
    client: QdrantClient,
    strategy_name: str,
    collection_name: str,
    parser: NodeParser,
    documents: list[Any],
) -> dict[str, Any]:
    """
    Индексирует документы одной chunking-стратегией.
    """

    print("=" * 80)
    print(f"Стратегия: {strategy_name}")
    print(f"Коллекция: {collection_name}")

    recreate_collection(
        client=client,
        collection_name=collection_name,
    )

    nodes = parser.get_nodes_from_documents(documents)

    print(f"Документов: {len(documents)}")
    print(f"Чанков: {len(nodes)}")

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

    stats = calculate_chunk_stats(
        strategy_name=strategy_name,
        collection_name=collection_name,
        documents_count=len(documents),
        nodes=nodes,
    )

    print(f"Среднее число чанков на документ: {stats['avg_chunks_per_document']}")
    print(f"Средняя длина чанка: {stats['avg_chunk_length']} символов")

    return stats


def write_experiment_doc(results: list[dict[str, Any]]) -> None:
    """
    Создаёт первичный markdown-отчёт по chunking-эксперименту.

    На следующих шагах мы добавим сюда retrieval-метрики,
    re-ranker и итоговый выбор конфигурации.
    """

    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)

    output_path = docs_dir / "chunking_experiment.md"

    lines = [
        "# Блок 5.4. Chunking и оптимизация качества",
        "",
        "## Статистика индексации",
        "",
        "| Стратегия | Коллекция Qdrant | Документов | Всего чанков | Среднее число чанков на документ | Средняя длина чанка, символов |",
        "|-----------|------------------|:----------:|:------------:|:--------------------------------:|:-----------------------------:|",
    ]

    for item in results:
        lines.append(
            "| "
            f"{item['strategy']} | "
            f"`{item['collection']}` | "
            f"{item['documents_count']} | "
            f"{item['total_chunks']} | "
            f"{item['avg_chunks_per_document']} | "
            f"{item['avg_chunk_length']} "
            "|"
        )

    lines.extend(
        [
            "",
            "## Результаты retrieval evaluation",
            "",
            "Будет заполнено после реализации метрик `Hit Rate@5`, `MRR@10`, `Recall@10`.",
            "",
            "| Стратегия | Hit Rate@5 | MRR@10 | Recall@10 | Средняя длина chunk | Скорость retrieval, мс |",
            "|-----------|:----------:|:------:|:---------:|:-------------------:|:----------------------:|",
            "",
            "## Re-ranker",
            "",
            "Будет заполнено после подключения re-ranker.",
            "",
            "## Подбор параметров",
            "",
            "Будет заполнено после экспериментов с `chunk_size`, `overlap` и `top-K`.",
            "",
            "## Итоговый выбор",
            "",
            "Будет заполнено после сравнения всех результатов.",
            "",
        ]
    )

    output_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    print()
    print(f"Отчёт создан: {output_path}")


def main() -> None:
    settings = get_settings()

    embed_model = HuggingFaceEmbedding(
        model_name=settings.embedding_model,
    )

    LlamaIndexSettings.embed_model = embed_model

    documents = SimpleDirectoryReader(
        input_dir=str(settings.rag_data_dir),
        recursive=True,
    ).load_data()

    print(f"Прочитано документов: {len(documents)}")
    print(f"Папка с документами: {settings.rag_data_dir}")

    client = create_qdrant_client(settings)

    try:
        strategies = [
            {
                "strategy_name": "fixed",
                "collection_name": "docs_fixed",
                "parser": fixed_size(
                    chunk_size=512,
                    chunk_overlap=64,
                ),
            },
            {
                "strategy_name": "recursive",
                "collection_name": "docs_recursive",
                "parser": recursive(
                    chunk_size=512,
                    chunk_overlap=64,
                ),
            },
            {
                "strategy_name": "semantic",
                "collection_name": "docs_semantic",
                "parser": semantic(
                    embed_model=embed_model,
                    buffer_size=1,
                    breakpoint_percentile_threshold=95,
                ),
            },
        ]

        results = []

        for item in strategies:
            stats = index_strategy(
                client=client,
                strategy_name=item["strategy_name"],
                collection_name=item["collection_name"],
                parser=item["parser"],
                documents=documents,
            )

            results.append(stats)

        write_experiment_doc(results)

    finally:
        client.close()


if __name__ == "__main__":
    main()