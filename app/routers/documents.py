import re
import shutil
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    HTTPException,
    UploadFile,
    status,
)

from app.core.config import get_settings
from app.services.ingestion import SUPPORTED_EXTENSIONS
from app.services.ingestion_pipeline import run_ingestion_pipeline


router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


def sanitize_name(
    value: str | None,
    default: str,
) -> str:
    raw_name = Path(value or default).name.strip()
    safe_name = re.sub(
        r"[^0-9A-Za-zА-Яа-яЁё._-]+",
        "_",
        raw_name,
    )

    return safe_name or default


def build_unique_path(
    directory: Path,
    file_name: str,
) -> Path:
    file_path = directory / file_name

    if not file_path.exists():
        return file_path

    stem = file_path.stem
    suffix = file_path.suffix

    counter = 1

    while True:
        candidate = directory / f"{stem}_{counter}{suffix}"

        if not candidate.exists():
            return candidate

        counter += 1


@router.post(
    "/upload",
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    category: str = "uploads",
) -> dict[str, str]:
    settings = get_settings()

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Имя файла не передано.",
        )

    extension = Path(file.filename).suffix.lower()

    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Неподдерживаемый формат файла. "
                f"Поддерживаются: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
        )

    safe_category = sanitize_name(
        value=category,
        default="uploads",
    )
    safe_file_name = sanitize_name(
        value=file.filename,
        default=f"uploaded_document{extension}",
    )

    upload_dir = Path(settings.rag_data_dir) / safe_category
    upload_dir.mkdir(parents=True, exist_ok=True)

    output_path = build_unique_path(
        directory=upload_dir,
        file_name=safe_file_name,
    )

    try:
        with output_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

    finally:
        await file.close()

    background_tasks.add_task(
        run_ingestion_pipeline,
        Path(settings.rag_data_dir),
    )

    return {
        "status": "accepted",
        "message": "Файл сохранён. Индексация запущена в фоне.",
        "file_name": output_path.name,
        "category": safe_category,
        "path": str(output_path),
    }