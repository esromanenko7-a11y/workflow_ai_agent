from llama_index.llms.ollama import Ollama
from llama_index.core import Settings, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from app.core.config import get_settings


settings = get_settings()


def main() -> None:
    Settings.embed_model = HuggingFaceEmbedding(
        model_name=settings.embedding_model,
    )

    Settings.llm = Ollama(
        model="llama3.2:latest",
        base_url="http://localhost:11434",
        request_timeout=120.0,
    )

    Settings.node_parser = SentenceSplitter(
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
    )

    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=(
            settings.qdrant_api_key.get_secret_value()
            if settings.qdrant_api_key
            else None
        ),
        trust_env=False,
    )

    vector_store = QdrantVectorStore(
        client=client,
        collection_name=settings.rag_collection,
    )

    storage_context = StorageContext.from_defaults(
        vector_store=vector_store,
    )

    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store,
        storage_context=storage_context,
    )

    query_engine = index.as_query_engine(
        similarity_top_k=settings.rag_similarity_top_k,
    )

    response = query_engine.query(
        "Какие обязательные технические поля должны быть в meta-файле?"
    )

    print("=" * 80)
    print(response)
    print("=" * 80)

    print("\nИсточники:\n")

    for i, node in enumerate(response.source_nodes, start=1):
        print(f"{i}. {node.metadata.get('file_name')}")
        print(f"Score: {node.score:.3f}")
        print(node.text[:250])
        print("-" * 80)

    client.close()


if __name__ == "__main__":
    main()