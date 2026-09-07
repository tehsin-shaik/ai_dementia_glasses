"""Safe local storage for uploaded memory images."""

from pathlib import Path
import mimetypes
import os
from uuid import uuid4

from fastapi import HTTPException, UploadFile


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


def configured_media_directory() -> Path:
    """Return the configured media directory without exposing it to clients."""

    configured_path = os.getenv("MEDIA_DIR") or "data/media"
    return Path(configured_path).resolve()


def safe_media_path(filename: str) -> Path:
    """Resolve a generated filename and reject traversal or absolute paths."""

    media_directory = configured_media_directory()
    candidate = (media_directory / filename).resolve()
    try:
        candidate.relative_to(media_directory)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Media file not found.") from exc
    if not filename or Path(filename).name != filename:
        raise HTTPException(status_code=404, detail="Media file not found.")
    return candidate


async def save_uploaded_image(upload: UploadFile) -> str:
    """Stream a supported image to a unique local filename."""

    extension = Path(upload.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type. Use one of: {allowed}.",
        )

    media_directory = configured_media_directory()
    media_directory.mkdir(parents=True, exist_ok=True)
    unique_name = f"{uuid4().hex}{extension}"
    final_path = media_directory / unique_name
    temporary_path = media_directory / f".{uuid4().hex}.upload"
    total_bytes = 0

    try:
        with temporary_path.open("wb") as destination:
            while chunk := await upload.read(CHUNK_SIZE):
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="Image is too large. The maximum size is 10 MB.",
                    )
                destination.write(chunk)

        if total_bytes == 0:
            raise HTTPException(status_code=400, detail="Image file cannot be empty.")

        temporary_path.replace(final_path)
        return unique_name
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def remove_uploaded_image(filename: str) -> None:
    """Remove a generated upload after a failed database transaction."""

    try:
        path = safe_media_path(filename)
    except HTTPException:
        return
    if path.is_file():
        path.unlink()


def media_type_for(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"
