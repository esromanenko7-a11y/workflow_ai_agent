from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any
from xml.etree import ElementTree
from zipfile import ZipFile

from llama_index.core import Document
from llama_index.readers.file import (
    DocxReader,
    HTMLTagReader,
    MarkdownReader,
    PyMuPDFReader,
)


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".html",
    ".htm",
    ".md",
    ".markdown",
    ".txt",
}

EXCLUDED_EMBED_METADATA_KEYS = [
    "source",
    "file_name",
    "file_path",
    "extension",
    "file_size_bytes",
    "created_at",
    "last_modified",
    "author",
    "category",
    "version",
    "page",
    "page_label",
]


def collect_supported_files(data_dir: str | Path) -> list[Path]:
    root = Path(data_dir)

    if not root.exists():
        raise FileNotFoundError(f"Папка не найдена: {root}")

    files = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        if path.name.endswith(".failed"):
            continue

        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path)

    return sorted(files)


def format_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc,
    ).isoformat()


def extract_category(file_path: Path, data_dir: Path) -> str:
    try:
        relative_path = file_path.relative_to(data_dir)
    except ValueError:
        return "unknown"

    if len(relative_path.parts) <= 1:
        return "root"

    return relative_path.parts[0]


def extract_version(file_path: Path) -> str | None:
    pattern = r"(?:^|[_\-\s])v(?:ersion)?[_\-\s]?(\d+(?:\.\d+)*)"
    match = re.search(pattern, file_path.stem, flags=re.IGNORECASE)

    if match is None:
        return None

    return match.group(1)


def extract_docx_author(file_path: Path) -> str | None:
    if file_path.suffix.lower() != ".docx":
        return None

    try:
        with ZipFile(file_path) as archive:
            xml_content = archive.read("docProps/core.xml")
    except Exception:
        return None

    try:
        root = ElementTree.fromstring(xml_content)
    except ElementTree.ParseError:
        return None

    namespace = {
        "dc": "http://purl.org/dc/elements/1.1/",
    }

    creator = root.find("dc:creator", namespace)

    if creator is None or creator.text is None:
        return None

    return creator.text.strip() or None


def build_file_metadata(
    file_path: Path,
    data_dir: Path,
) -> dict[str, Any]:
    stat = file_path.stat()

    return {
        "source": file_path.name,
        "file_name": file_path.name,
        "file_path": str(file_path),
        "extension": file_path.suffix.lower(),
        "file_size_bytes": stat.st_size,
        "created_at": format_timestamp(stat.st_ctime),
        "last_modified": format_timestamp(stat.st_mtime),
        "author": extract_docx_author(file_path),
        "category": extract_category(
            file_path=file_path,
            data_dir=data_dir,
        ),
        "version": extract_version(file_path),
    }


def read_txt_file(file_path: Path) -> list[Document]:
    text = file_path.read_text(encoding="utf-8")

    return [
        Document(text=text)
    ]


def load_with_reader(
    reader: Any,
    file_path: Path,
) -> list[Document]:
    try:
        return reader.load_data(file_path=file_path)
    except TypeError:
        try:
            return reader.load_data(file=file_path)
        except TypeError:
            return reader.load_data(file_path)


def read_file(file_path: Path) -> list[Document]:
    extension = file_path.suffix.lower()

    if extension == ".pdf":
        return load_with_reader(
            reader=PyMuPDFReader(),
            file_path=file_path,
        )

    if extension == ".docx":
        return load_with_reader(
            reader=DocxReader(),
            file_path=file_path,
        )

    if extension in {".html", ".htm"}:
        return load_with_reader(
            reader=HTMLTagReader(),
            file_path=file_path,
        )

    if extension in {".md", ".markdown"}:
        return load_with_reader(
            reader=MarkdownReader(),
            file_path=file_path,
        )

    if extension == ".txt":
        return read_txt_file(file_path)

    raise ValueError(f"Неподдерживаемый формат файла: {file_path}")


def enrich_document_metadata(
    document: Document,
    file_metadata: dict[str, Any],
    document_index: int,
) -> Document:
    page = (
        document.metadata.get("page")
        or document.metadata.get("page_label")
        or document.metadata.get("page_number")
    )

    document.metadata.update(file_metadata)

    if page is not None:
        document.metadata["page"] = page

    document_id = (
        f"{file_metadata['file_path']}"
        f"::part-{document_index}"
    )

    document.id_ = document_id
    document.metadata["document_id"] = document_id

    document.excluded_embed_metadata_keys = EXCLUDED_EMBED_METADATA_KEYS
    document.excluded_llm_metadata_keys = [
        "file_path",
        "file_size_bytes",
        "created_at",
        "last_modified",
        "document_id",
    ]

    return document


def load_documents_from_directory(
    data_dir: str | Path,
) -> tuple[list[Document], list[dict[str, str]]]:
    root = Path(data_dir)
    documents: list[Document] = []
    failed_files: list[dict[str, str]] = []

    for file_path in collect_supported_files(root):
        try:
            file_documents = read_file(file_path)
            metadata = build_file_metadata(
                file_path=file_path,
                data_dir=root,
            )

            for document_index, document in enumerate(file_documents):
                documents.append(
                    enrich_document_metadata(
                        document=document,
                        file_metadata=metadata,
                        document_index=document_index,
                    )
                )

        except Exception as error:
            failed_files.append(
                {
                    "file_path": str(file_path),
                    "error": str(error),
                }
            )

    return documents, failed_files