from llama_index.core import SimpleDirectoryReader
from llama_index.core.node_parser import SentenceSplitter


INPUT_DIR = "data/rag-block-03"
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64


def main() -> None:
    documents = SimpleDirectoryReader(
        input_dir=INPUT_DIR,
        recursive=True,
    ).load_data()

    splitter = SentenceSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    nodes = splitter.get_nodes_from_documents(documents)

    print(f"Исходных документов: {len(documents)}")
    print(f"Получено нод: {len(nodes)}")
    print()

    for index, node in enumerate(nodes, start=1):
        print("=" * 80)
        print(f"Нода {index}")
        print(f"Источник: {node.metadata.get('file_name')}")
        print(f"Символов: {len(node.text)}")
        print()
        print(node.text[:300])
        print()


if __name__ == "__main__":
    main()