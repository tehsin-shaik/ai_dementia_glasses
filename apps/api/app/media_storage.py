"""Safe local storage for uploaded memory images."""

from pathlib import Path, PureWindowsPath
import mimetypes
import os
from urllib.parse import unquote
from uuid import uuid4

from fastapi import HTTPException, UploadFile


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_CONTENT_TYPES = {
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".webp": {"image/webp"},
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


def configured_media_directory() -> Path:
    """Return the configured media directory without exposing it to clients."""

    configured_path = os.getenv("MEDIA_DIR") or "data/media"
    return Path(configured_path).resolve()


def safe_media_path(filename: str) -> Path:
    """Resolve a generated filename and reject traversal or absolute paths."""

    if unquote(filename) != filename:
        raise HTTPException(status_code=404, detail="Media file not found.")

    windows_path = PureWindowsPath(filename)
    if (
        not filename
        or Path(filename).name != filename
        or windows_path.name != filename
        or Path(filename).is_absolute()
        or windows_path.drive
        or windows_path.root
    ):
        raise HTTPException(status_code=404, detail="Media file not found.")

    if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=404, detail="Media file not found.")

    media_directory = configured_media_directory()
    candidate = (media_directory / filename).resolve()
    try:
        candidate.relative_to(media_directory)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Media file not found.") from exc
    return candidate


async def save_uploaded_image(upload: UploadFile) -> str:
    """Store a supported image under a unique local filename."""

    extension, image_bytes = await read_uploaded_image(upload)

    media_directory = configured_media_directory()
    media_directory.mkdir(parents=True, exist_ok=True)
    unique_name = f"{uuid4().hex}{extension}"
    final_path = media_directory / unique_name
    temporary_path = media_directory / f".{uuid4().hex}.upload"

    try:
        temporary_path.write_bytes(image_bytes)
        temporary_path.replace(final_path)
        return unique_name
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def validate_image_extension(filename: str | None) -> str:
    """Return a supported image extension or raise a client-facing error."""

    extension = Path(filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type. Use one of: {allowed}.",
        )
    return extension


def validate_image_content_type(filename: str | None, content_type: str | None) -> None:
    """Reject a declared MIME type that does not match the allowed extension."""

    extension = validate_image_extension(filename)
    normalized_content_type = (content_type or "").split(";", 1)[0].strip().casefold()
    if normalized_content_type and normalized_content_type not in ALLOWED_CONTENT_TYPES[extension]:
        raise HTTPException(status_code=400, detail="The image content type does not match its file type.")


async def read_uploaded_image(upload: UploadFile) -> tuple[str, bytes]:
    """Read a supported image for temporary analysis using the upload size limit."""

    extension = validate_image_extension(upload.filename)
    validate_image_content_type(upload.filename, upload.content_type)
    chunks: list[bytes] = []
    total_bytes = 0

    while chunk := await upload.read(CHUNK_SIZE):
        total_bytes += len(chunk)
        if total_bytes > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail="Image is too large. The maximum size is 10 MB.",
            )
        chunks.append(chunk)

    if total_bytes == 0:
        raise HTTPException(status_code=400, detail="Image file cannot be empty.")

    return extension, b"".join(chunks)


def remove_uploaded_image(filename: str) -> None:
    """Remove a generated upload after a failed database transaction."""

    try:
        path = safe_media_path(filename)
    except HTTPException:
        return
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        # Cleanup is best effort and should not mask the original database error.
        return


def media_type_for(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"
