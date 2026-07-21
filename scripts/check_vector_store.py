import asyncio

from app.services.vector_store import get_vector_store


async def main() -> None:
    vector_store = get_vector_store()

    try:
        await vector_store.ensure_collection()

        points_count = await vector_store.get_points_count()

        print(f"Точек в коллекции: {points_count}")

    finally:
        await vector_store.close()


if __name__ == "__main__":
    asyncio.run(main())
    