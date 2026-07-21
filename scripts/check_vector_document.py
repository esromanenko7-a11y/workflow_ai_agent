from app.schemas.vector_document import VectorDocument


def main() -> None:
    document = VectorDocument(
        source="validation_catalog",
        check_code="CHECK_REQUIRED_FILES",
        check_name="Проверка обязательных файлов",
        category="package_structure",
        severity="error",
        chunk_type="recommendation",
        text=(
            "Добавьте отсутствующий обязательный файл "
            "и повторно запустите проверку пакета."
        ),
    )

    print("VectorDocument validation: OK")
    print(document.model_dump_json(indent=2))


if __name__ == "__main__":
    main()