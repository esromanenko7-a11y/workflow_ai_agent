from typing import Any

from llama_index.core.schema import NodeWithScore
from sentence_transformers import CrossEncoder


class CrossEncoderReranker:
    """
    Re-ranker на базе open-source cross-encoder.

    Retriever сначала находит кандидатов по embedding similarity.
    Re-ranker получает вопрос и тексты кандидатов,
    затем пересортировывает их по более точной оценке релевантности.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        top_n: int = 5,
    ) -> None:
        self.model_name = model_name
        self.top_n = top_n
        self.model = CrossEncoder(model_name)

    def rerank(
        self,
        query: str,
        candidates: list[NodeWithScore],
    ) -> list[NodeWithScore]:
        """
        Пересортировывает список найденных кандидатов.

        Вход:
        - query: вопрос пользователя;
        - candidates: список найденных чанков.

        Выход:
        - top-N кандидатов, отсортированных по score re-ranker.
        """

        if not candidates:
            return []

        pairs = [
            [query, candidate.node.get_content()]
            for candidate in candidates
        ]

        scores = self.model.predict(pairs)

        reranked = []

        for candidate, score in zip(candidates, scores):
            candidate.score = float(score)
            reranked.append(candidate)

        reranked.sort(
            key=lambda item: item.score if item.score is not None else 0.0,
            reverse=True,
        )

        return reranked[: self.top_n]


def rerank_candidates(
    query: str,
    candidates: list[NodeWithScore],
    model_name: str = "BAAI/bge-reranker-v2-m3",
    top_n: int = 5,
) -> list[NodeWithScore]:
    """
    Удобная функция-обёртка.

    Её можно использовать в скриптах без ручного создания класса.
    """

    reranker = CrossEncoderReranker(
        model_name=model_name,
        top_n=top_n,
    )

    return reranker.rerank(
        query=query,
        candidates=candidates,
    )