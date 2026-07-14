import json
from pathlib import Path

from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim


MODEL_NAME = "intfloat/multilingual-e5-small"
BENCHMARK_PATH = Path("tests/eval/mini_benchmark.json")


def main() -> None:
    benchmark = json.loads(
        BENCHMARK_PATH.read_text(encoding="utf-8-sig")
    )

    sample = benchmark[0]

    model = SentenceTransformer(MODEL_NAME)

    query_vector = model.encode(
        [f"query: {sample['query']}"],
        normalize_embeddings=True,
    )

    document_vectors = model.encode(
        [
            f"passage: {sample['relevant']}",
            f"passage: {sample['irrelevant']}",
        ],
        normalize_embeddings=True,
    )

    relevant_score = float(
        cos_sim(query_vector[0], document_vectors[0]).item()
    )

    irrelevant_score = float(
        cos_sim(query_vector[0], document_vectors[1]).item()
    )

    print(f"Model: {MODEL_NAME}")
    print(f"Vector size: {len(query_vector[0])}")
    print(f"Relevant score: {relevant_score:.4f}")
    print(f"Irrelevant score: {irrelevant_score:.4f}")
    print(f"Relevant is higher: {relevant_score > irrelevant_score}")


if __name__ == "__main__":
    main()
