from app.core.config import get_settings
import hashlib
import json
import os
import time
from functools import lru_cache
from pathlib import Path

from diskcache import Cache
from sentence_transformers import SentenceTransformer


DEFAULT_MODEL_NAME = "intfloat/multilingual-e5-small"
DEFAULT_BATCH_SIZE = 32
DEFAULT_CACHE_DIR = ".cache/embeddings"


class EmbeddingService:
    """
    Локальный сервис эмбеддингов с батчингом и дисковым кешем.

    Для E5-модели:
    - запросы получают префикс "query:"
    - документы получают префикс "passage:"
    """

    def __init__(
        self,
        model_name: str | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        cache_dir: str | Path | None = None,
    ) -> None:
        settings = get_settings()

        self.model_name = (
                model_name
                or settings.embedding_model
        )
        self.batch_size = int(
            os.getenv(
                "EMBEDDING_BATCH_SIZE",
                str(batch_size),
            )
        )

        resolved_cache_dir = (
            Path(cache_dir)
            if cache_dir is not None
            else Path(
                os.getenv(
                    "EMBEDDING_CACHE_DIR",
                    DEFAULT_CACHE_DIR,
                )
            )
        )

        resolved_cache_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.cache = Cache(
            str(resolved_cache_dir),
        )

        self.model = SentenceTransformer(
            self.model_name,
        )

    def _cache_key(
        self,
        text: str,
        kind: str,
    ) -> str:
        """
        Создаёт уникальный ключ кеша.

        В ключ входят:
        - имя модели;
        - тип текста query/document;
        - содержимое текста.
        """
        payload = {
            "model": self.model_name,
            "kind": kind,
            "text": text,
        }

        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        )

        digest = hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest()

        return digest

    def _get_cached_vector(
        self,
        text: str,
        kind: str,
    ) -> list[float] | None:
        key = self._cache_key(
            text=text,
            kind=kind,
        )

        cached = self.cache.get(key)

        if cached is None:
            return None

        return list(cached)

    def _save_vector_to_cache(
        self,
        text: str,
        kind: str,
        vector: list[float],
    ) -> None:
        key = self._cache_key(
            text=text,
            kind=kind,
        )

        self.cache.set(
            key,
            vector,
        )

    def embed_query(
        self,
        text: str,
    ) -> list[float]:
        """
        Создаёт эмбеддинг для пользовательского запроса.
        """
        clean_text = text.strip()

        cached = self._get_cached_vector(
            text=clean_text,
            kind="query",
        )

        if cached is not None:
            return cached

        prepared_text = f"query: {clean_text}"

        vector = self.model.encode(
            prepared_text,
            normalize_embeddings=True,
        ).tolist()

        self._save_vector_to_cache(
            text=clean_text,
            kind="query",
            vector=vector,
        )

        return vector

    def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        """
        Создаёт эмбеддинги для фрагментов документов.

        Уже известные тексты берутся из кеша.
        Остальные считаются батчами.
        """
        if not texts:
            return []

        clean_texts = [
            text.strip()
            for text in texts
        ]

        results: list[list[float] | None] = [
            None
            for _ in clean_texts
        ]

        missing_texts: list[str] = []
        missing_indexes: list[int] = []

        for index, text in enumerate(clean_texts):
            cached = self._get_cached_vector(
                text=text,
                kind="document",
            )

            if cached is not None:
                results[index] = cached
            else:
                missing_texts.append(text)
                missing_indexes.append(index)

        if missing_texts:
            prepared_texts = [
                f"passage: {text}"
                for text in missing_texts
            ]

            vectors = self.model.encode(
                prepared_texts,
                batch_size=self.batch_size,
                normalize_embeddings=True,
                show_progress_bar=False,
            ).tolist()

            for index, text, vector in zip(
                missing_indexes,
                missing_texts,
                vectors,
                strict=True,
            ):
                results[index] = vector

                self._save_vector_to_cache(
                    text=text,
                    kind="document",
                    vector=vector,
                )

        return [
            vector
            for vector in results
            if vector is not None
        ]

    def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        """
        Публичный интерфейс из задания.

        Тексты считаются документами.
        """
        return self.embed_documents(texts)

    def close(self) -> None:
        self.cache.close()


@lru_cache(maxsize=1)
def get_embedding_service() -> EmbeddingService:
    """
    Возвращает один экземпляр сервиса на процесс.
    """
    return EmbeddingService()


def embed_query(
    text: str,
) -> list[float]:
    return get_embedding_service().embed_query(text)


def embed_documents(
    texts: list[str],
) -> list[list[float]]:
    return get_embedding_service().embed_documents(texts)


def embed_texts(
    texts: list[str],
) -> list[list[float]]:
    return get_embedding_service().embed_texts(texts)
