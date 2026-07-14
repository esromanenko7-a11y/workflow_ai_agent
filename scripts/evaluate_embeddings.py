import json
from pathlib import Path

from sentence_transformers.util import cos_sim

from app.services.embeddings import EmbeddingService


BENCHMARK_PATH = Path("tests/eval/mini_benchmark.json")


def main() -> None:
    benchmark = json.loads(
        BENCHMARK_PATH.read_text(encoding="utf-8-sig")
    )

    service = EmbeddingService()

    passed = 0

    for index, item in enumerate(benchmark, start=1):
        query_vector = service.embed_query(item["query"])

        document_vectors = service.embed_documents(
            [
                item["relevant"],
                item["irrelevant"],
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

        is_correct = relevant_score > irrelevant_score

        if is_correct:
            passed += 1

        print(f"Case {index}:")
        print(f"  relevant:   {relevant_score:.4f}")
        print(f"  irrelevant: {irrelevant_score:.4f}")
        print(f"  passed:     {is_correct}")

    accuracy = passed / len(benchmark)

    print()
    print(f"Passed: {passed}/{len(benchmark)}")
    print(f"Accuracy: {accuracy:.2%}")

    service.close()


if __name__ == "__main__":
    main()
