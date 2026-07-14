from pathlib import Path

import pytest
from sentence_transformers.util import cos_sim

from app.services.embeddings import EmbeddingService


@pytest.fixture
def embedding_service(tmp_path: Path) -> EmbeddingService:
    service = EmbeddingService(
        model_name="intfloat/multilingual-e5-small",
        batch_size=16,
        cache_dir=tmp_path / "embeddings-cache",
    )

    yield service

    service.close()


def test_embed_query_returns_vector(
    embedding_service: EmbeddingService,
) -> None:
    vector = embedding_service.embed_query(
        "Почему пакет отклонён?"
    )

    assert isinstance(vector, list)
    assert len(vector) == 384
    assert all(isinstance(value, float) for value in vector)


def test_embed_documents_preserves_count_and_order(
    embedding_service: EmbeddingService,
) -> None:
    texts = [
        "Пакет содержит критические ошибки.",
        "Пакет прошёл все обязательные проверки.",
    ]

    vectors = embedding_service.embed_documents(texts)

    assert len(vectors) == 2
    assert len(vectors[0]) == 384
    assert len(vectors[1]) == 384
    assert vectors[0] != vectors[1]


def test_embed_documents_returns_empty_list_for_empty_input(
    embedding_service: EmbeddingService,
) -> None:
    result = embedding_service.embed_documents([])

    assert result == []


def test_embedding_cache_is_used(
    embedding_service: EmbeddingService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = "Пакет содержит критические ошибки проверки."

    first_vector = embedding_service.embed_documents([text])[0]

    def fail_encode(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "model.encode не должен вызываться при cache hit"
        )

    monkeypatch.setattr(
        embedding_service.model,
        "encode",
        fail_encode,
    )

    second_vector = embedding_service.embed_documents([text])[0]

    assert second_vector == first_vector


def test_relevant_document_has_higher_similarity(
    embedding_service: EmbeddingService,
) -> None:
    query_vector = embedding_service.embed_query(
        "Почему пакет нельзя передать дальше?"
    )

    document_vectors = embedding_service.embed_documents(
        [
            "Пакет содержит критические ошибки и не может быть передан дальше.",
            "Telegram-бот использует polling для получения сообщений.",
        ]
    )

    relevant_score = float(
        cos_sim(
            query_vector,
            document_vectors[0],
        ).item()
    )

    irrelevant_score = float(
        cos_sim(
            query_vector,
            document_vectors[1],
        ).item()
    )

    assert relevant_score > irrelevant_score
