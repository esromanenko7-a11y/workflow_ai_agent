import os
import time

from qdrant_client import QdrantClient


def main() -> None:
    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    api_key = os.getenv("QDRANT_API_KEY") or None
    timeout_seconds = int(os.getenv("QDRANT_WAIT_TIMEOUT_SECONDS", "60"))

    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            client = QdrantClient(
                url=url,
                api_key=api_key,
            )
            client.get_collections()

            try:
                client.close()
            except Exception:
                pass

            print(f"Qdrant is ready: {url}")
            return

        except Exception as error:
            last_error = error
            print(f"Qdrant is not ready yet: {error}")
            time.sleep(2)

    raise RuntimeError(
        f"Qdrant is not ready after {timeout_seconds} seconds: {last_error}"
    )


if __name__ == "__main__":
    main()