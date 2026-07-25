from llama_index.core import SimpleDirectoryReader


reader = SimpleDirectoryReader(
    input_dir="data/rag-block-03",
    recursive=True,
)

documents = reader.load_data()

print(f"Документов: {len(documents)}")
print()

for index, document in enumerate(documents, start=1):
    print("=" * 80)
    print(f"Документ {index}")
    print()

    print("Metadata:")
    print(document.metadata)
    print()

    print("Первые 250 символов:")
    print(document.text[:250])
    print()