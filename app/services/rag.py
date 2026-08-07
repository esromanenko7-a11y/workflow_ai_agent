import re
from typing import Any

from llama_index.core import (
    Settings as LlamaIndexSettings,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import NodeWithScore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from app.core.config import get_settings
from app.services.reranker import CrossEncoderReranker


FALLBACK_ANSWER = (
    "По базе не нашёл, могу эскалировать вопрос специалисту."
)


class RAGService:
    def __init__(self) -> None:
        self.settings = get_settings()

        self.client: QdrantClient | None = None
        self.vector_store: QdrantVectorStore | None = None
        self.index: VectorStoreIndex | None = None
        self.retriever: Any | None = None
        self.llm: Ollama | None = None
        self.reranker: CrossEncoderReranker | None = None

    def _configure_llama_index(self) -> None:
        embed_model = HuggingFaceEmbedding(
            model_name=self.settings.embedding_model,
        )

        llm = Ollama(
            model=self.settings.llm.default_model,
            base_url=self.settings.llm.ollama_base_url,
            request_timeout=self.settings.llm.request_timeout,
        )

        LlamaIndexSettings.embed_model = embed_model
        LlamaIndexSettings.llm = llm
        LlamaIndexSettings.node_parser = SentenceSplitter(
            chunk_size=self.settings.rag_chunk_size,
            chunk_overlap=self.settings.rag_chunk_overlap,
        )

        self.llm = llm

    def _create_qdrant_client(self) -> QdrantClient:
        api_key = (
            self.settings.qdrant_api_key.get_secret_value()
            if self.settings.qdrant_api_key
            else None
        )

        return QdrantClient(
            url=self.settings.qdrant_url,
            api_key=api_key,
            trust_env=False,
        )

    def build(self) -> None:
        self._configure_llama_index()
        self.client = self._create_qdrant_client()

        collection_exists = self.client.collection_exists(
            collection_name=self.settings.rag_collection,
        )

        if not collection_exists:
            raise RuntimeError(
                f"Коллекция {self.settings.rag_collection} не найдена. "
                "Сначала запустите: python scripts/ingest.py data"
            )

        collection_info = self.client.get_collection(
            collection_name=self.settings.rag_collection,
        )

        points_count = collection_info.points_count or 0

        if points_count == 0:
            raise RuntimeError(
                f"Коллекция {self.settings.rag_collection} пуста. "
                "Сначала запустите: python scripts/ingest.py data"
            )

        self.vector_store = QdrantVectorStore(
            client=self.client,
            collection_name=self.settings.rag_collection,
        )

        storage_context = StorageContext.from_defaults(
            vector_store=self.vector_store,
        )

        self.index = VectorStoreIndex.from_vector_store(
            vector_store=self.vector_store,
            storage_context=storage_context,
        )

        self.retriever = self.index.as_retriever(
            similarity_top_k=self.settings.rag_similarity_top_k,
        )

        if self.settings.rag_reranker_enabled:
            self.reranker = CrossEncoderReranker(
                top_n=self.settings.rag_reranker_top_n,
            )

        print(
            f"RAG подключён к коллекции {self.settings.rag_collection}. "
            f"Точек в Qdrant: {points_count}"
        )

    def answer(self, question: str) -> dict[str, Any]:
        if not question.strip():
            raise ValueError("Вопрос не должен быть пустым.")

        if self.retriever is None or self.llm is None:
            raise RuntimeError(
                "RAGService ещё не инициализирован. "
                "Сначала вызовите build()."
            )

        retrieved_nodes = self.retriever.retrieve(question)

        for node in retrieved_nodes:
            node.node.metadata["_retrieval_score"] = self._get_node_score(node)

        top_score = self._get_top_retrieval_score(retrieved_nodes)

        if top_score < self.settings.rag_score_threshold:
            return self._build_fallback_response(top_score=top_score)

        selected_nodes = self._rerank_nodes(
            question=question,
            nodes=retrieved_nodes,
        )

        sources = self._build_sources(selected_nodes)
        context = self._build_numbered_context(selected_nodes)
        prompt = self._build_prompt(
            question=question,
            context=context,
        )

        llm_response = self.llm.complete(prompt)
        answer = getattr(llm_response, "text", str(llm_response)).strip()

        if self._is_fallback_answer(answer):
            answer = self._build_extractive_answer(sources)

        answer = self._ensure_citations(answer, sources)

        return {
            "answer": answer,
            "top_score": round(top_score, 3),
            "confident": True,
            "sources": sources,
        }

    def _rerank_nodes(
            self,
            question: str,
            nodes: list[NodeWithScore],
    ) -> list[NodeWithScore]:
        if not nodes:
            return []

        if self.reranker is None:
            return nodes[: self.settings.rag_reranker_top_n]

        return self.reranker.rerank(
            question,
            nodes,
        )

    def _get_node_score(self, node: NodeWithScore) -> float:
        if node.score is None:
            return 0.0

        return float(node.score)

    def _get_top_retrieval_score(
        self,
        nodes: list[NodeWithScore],
    ) -> float:
        if not nodes:
            return 0.0

        scores = [
            self._get_node_score(node)
            for node in nodes
        ]

        return max(scores)

    def _build_fallback_response(self, top_score: float) -> dict[str, Any]:
        print(
            "RAG score guard: "
            f"top_score={top_score:.3f}, "
            f"threshold={self.settings.rag_score_threshold:.3f}"
        )

        return {
            "answer": FALLBACK_ANSWER,
            "top_score": round(top_score, 3),
            "confident": False,
            "sources": [],
        }

    def _build_sources(
        self,
        nodes: list[NodeWithScore],
    ) -> list[dict[str, Any]]:
        sources = []

        for index, node in enumerate(nodes, start=1):
            metadata = node.metadata
            score = metadata.get(
                "_retrieval_score",
                self._get_node_score(node),
            )

            sources.append(
                {
                    "id": str(index),
                    "file_name": (
                        metadata.get("file_name")
                        or metadata.get("source")
                    ),
                    "page": (
                        metadata.get("page")
                        or metadata.get("page_label")
                        or metadata.get("page_number")
                    ),
                    "score": round(float(score), 3),
                    "snippet": self._make_snippet(node.text),
                }
            )

        return sources

    def _build_numbered_context(
        self,
        nodes: list[NodeWithScore],
    ) -> str:
        context_parts = []

        for index, node in enumerate(nodes, start=1):
            metadata = node.metadata
            file_name = metadata.get("file_name") or metadata.get("source")
            page = (
                metadata.get("page")
                or metadata.get("page_label")
                or metadata.get("page_number")
            )

            source_header = f"[{index}]"
            if file_name:
                source_header += f" {file_name}"
            if page:
                source_header += f", page {page}"

            context_parts.append(
                f"{source_header}\n{node.text.strip()}"
            )

        return "\n\n".join(context_parts)

    def _build_prompt(
        self,
        question: str,
        context: str,
    ) -> str:
        return f"""
Ты корпоративный RAG-ассистент по проверке пакетов данных.

Отвечай только на основе контекста ниже.
Не используй знания вне контекста.
Если в контексте нет достаточной информации, ответь:
"{FALLBACK_ANSWER}"

В ответе обязательно указывай источники в формате [1], [2].
Объясняй простым языком: что не так, насколько это критично и что исправить.

Контекст:
{context}

Вопрос пользователя:
{question}

Ответ:
""".strip()

    def _is_fallback_answer(self, answer: str) -> bool:
        normalized_answer = answer.lower().replace("ё", "е")

        has_not_found = "не наш" in normalized_answer
        has_base = "баз" in normalized_answer
        has_escalation = "эскал" in normalized_answer
        has_not_enough_info = (
                "недостаточно" in normalized_answer
                and "информац" in normalized_answer
        )

        return (
                has_base and has_not_found
        ) or (
                has_not_found and has_escalation
        ) or has_not_enough_info

    def _build_extractive_answer(
            self,
            sources: list[dict[str, Any]],
    ) -> str:
        if not sources:
            return FALLBACK_ANSWER

        answer_parts = [
            "В базе знаний найдена релевантная информация.",
            "",
            "Ключевые фрагменты:",
        ]

        for source in sources[:3]:
            answer_parts.append(
                f"[{source['id']}] {source['snippet']}"
            )

        answer_parts.append("")
        answer_parts.append(
            "Проверьте указанные требования в пакете данных и исправьте найденные несоответствия."
        )

        return "\n".join(answer_parts)

    def _make_snippet(
        self,
        text: str,
        max_length: int = 500,
    ) -> str:
        snippet = " ".join(text.split())

        if len(snippet) <= max_length:
            return snippet

        return snippet[:max_length].rstrip() + "..."

    def _ensure_citations(
        self,
        answer: str,
        sources: list[dict[str, Any]],
    ) -> str:
        if not sources:
            return answer

        has_citation = re.search(r"\[\d+\]", answer) is not None

        if has_citation:
            return answer

        source_refs = ", ".join(
            f"[{source['id']}]"
            for source in sources[:2]
        )

        return f"{answer}\n\nИсточники: {source_refs}"

    def close(self) -> None:
        if self.client is not None:
            self.client.close()


def main() -> None:
    rag_service = RAGService()

    try:
        rag_service.build()

        result = rag_service.answer(
            "Какие обязательные технические поля должны быть в meta-файле?"
        )

        print()
        print(result)

    finally:
        rag_service.close()


if __name__ == "__main__":
    main()