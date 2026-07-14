import time

from app.services.embeddings import EmbeddingService


TEXT = "Пакет содержит критические ошибки проверки."


def main() -> None:
    service = EmbeddingService()

    started = time.perf_counter()
    first = service.embed_texts([TEXT])
    first_duration = time.perf_counter() - started

    started = time.perf_counter()
    second = service.embed_texts([TEXT])
    second_duration = time.perf_counter() - started

    print(f"Vector size: {len(first[0])}")
    print(f"First call: {first_duration:.6f} sec")
    print(f"Second call: {second_duration:.6f} sec")
    print(f"Vectors equal: {first == second}")
    print(
        "Second call is faster:",
        second_duration < first_duration,
    )

    service.close()


if __name__ == "__main__":
    main()
