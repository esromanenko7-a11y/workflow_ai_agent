import json
import time
from pathlib import Path
from typing import Any, Callable

from llama_index.core.schema import NodeWithScore


RetrievalFunction = Callable[[str, int], list[NodeWithScore]]


def load_retrieval_dataset(dataset_path: str | Path) -> list[dict[str, Any]]:
    """
    Загружает golden dataset для retrieval evaluation.

    Ожидаемый формат элемента:
    {
        "question": "...",
        "relevant_doc_ids": ["meta_required_tech_fields.md"]
    }
    """

    path = Path(dataset_path)

    with path.open("r", encoding="utf-8") as file:
        dataset = json.load(file)

    if not isinstance(dataset, list):
        raise ValueError("retrieval_dataset.json должен содержать список объектов.")

    return dataset


def extract_source_id(node: NodeWithScore) -> str | None:
    """
    Достаёт id документа из найденного чанка.

    В нашем корпусе в качестве id документа используем имя файла:
    meta_required_tech_fields.md, file_naming.md и т.д.
    """

    metadata = node.node.metadata

    source = metadata.get("file_name")

    if source is None:
        source = metadata.get("file_path")

    if source is None:
        return None

    return Path(str(source)).name


def retrieved_doc_ids(nodes: list[NodeWithScore], top_k: int) -> list[str]:
    """
    Преобразует найденные чанки в список id документов.

    Один документ может встретиться несколько раз, если было найдено
    несколько чанков из одного файла. Для метрик retrieval нам важно
    учитывать документ один раз.
    """

    result = []
    seen = set()

    for node in nodes[:top_k]:
        source_id = extract_source_id(node)

        if source_id is None:
            continue

        if source_id in seen:
            continue

        result.append(source_id)
        seen.add(source_id)

    return result


def hit_rate_at_k(
    retrieved: list[str],
    relevant: list[str],
    k: int,
) -> float:
    """
    Hit Rate@K.

    Возвращает 1, если среди первых K найденных документов есть
    хотя бы один эталонный документ.

    Иначе возвращает 0.
    """

    retrieved_top_k = set(retrieved[:k])
    relevant_set = set(relevant)

    return 1.0 if retrieved_top_k & relevant_set else 0.0


def mrr_at_k(
    retrieved: list[str],
    relevant: list[str],
    k: int,
) -> float:
    """
    MRR@K — Mean Reciprocal Rank.

    Для одного вопроса:
    - если первый релевантный документ найден на позиции 1, score = 1;
    - если на позиции 2, score = 1/2;
    - если на позиции 3, score = 1/3;
    - если релевантный документ не найден в top-K, score = 0.
    """

    relevant_set = set(relevant)

    for index, doc_id in enumerate(retrieved[:k], start=1):
        if doc_id in relevant_set:
            return 1.0 / index

    return 0.0


def recall_at_k(
    retrieved: list[str],
    relevant: list[str],
    k: int,
) -> float:
    """
    Recall@K.

    Показывает, какую долю эталонных документов удалось найти
    среди первых K результатов.
    """

    relevant_set = set(relevant)

    if not relevant_set:
        return 0.0

    retrieved_top_k = set(retrieved[:k])
    found = retrieved_top_k & relevant_set

    return len(found) / len(relevant_set)


def evaluate_retrieval(
    dataset: list[dict[str, Any]],
    retrieve_fn: RetrievalFunction,
    hit_k: int = 5,
    mrr_k: int = 10,
    recall_k: int = 10,
) -> dict[str, float]:
    """
    Единая функция-обёртка для расчёта retrieval-метрик.

    retrieve_fn — функция, которая принимает:
    - question;
    - top_k;

    и возвращает список найденных NodeWithScore.
    """

    if not dataset:
        raise ValueError("Dataset пустой. Невозможно посчитать метрики.")

    hit_scores = []
    mrr_scores = []
    recall_scores = []
    retrieval_times_ms = []

    top_k = max(hit_k, mrr_k, recall_k)

    for item in dataset:
        question = item["question"]
        relevant_doc_ids = item["relevant_doc_ids"]

        start_time = time.perf_counter()
        nodes = retrieve_fn(question, top_k)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        retrieved_ids = retrieved_doc_ids(nodes, top_k=top_k)

        hit_scores.append(
            hit_rate_at_k(
                retrieved=retrieved_ids,
                relevant=relevant_doc_ids,
                k=hit_k,
            )
        )

        mrr_scores.append(
            mrr_at_k(
                retrieved=retrieved_ids,
                relevant=relevant_doc_ids,
                k=mrr_k,
            )
        )

        recall_scores.append(
            recall_at_k(
                retrieved=retrieved_ids,
                relevant=relevant_doc_ids,
                k=recall_k,
            )
        )

        retrieval_times_ms.append(elapsed_ms)

    return {
        "hit_rate_at_5": round(sum(hit_scores) / len(hit_scores), 3),
        "mrr_at_10": round(sum(mrr_scores) / len(mrr_scores), 3),
        "recall_at_10": round(sum(recall_scores) / len(recall_scores), 3),
        "avg_retrieval_ms": round(
            sum(retrieval_times_ms) / len(retrieval_times_ms),
            2,
        ),
    }