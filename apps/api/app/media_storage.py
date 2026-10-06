"""Safe local storage for uploaded memory images."""

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
import mimetypes
import os
from urllib.parse import unquote
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from .models import MediaBlob


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_CONTENT_TYPES = {
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".webp": {"image/webp"},
}
IMAGE_SIGNATURES = {
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


def configured_media_directory() -> Path:
    """Return the configured media directory without exposing it to clients."""

    configured_path = os.getenv("MEDIA_DIR") or "data/media"
    return Path(configured_path).resolve()


def uses_database_media() -> bool:
    """Whether uploaded images are stored as database rows instead of local files."""

    return (os.getenv("MEDIA_STORAGE") or "").strip().casefold() == "database"


def new_media_filename(extension: str) -> str:
    return f"{uuid4().hex}{extension}"


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
    unique_name = new_media_filename(extension)
    write_media_file(unique_name, image_bytes)
    return unique_name


def write_media_file(filename: str, data: bytes) -> None:
    media_directory = configured_media_directory()
    media_directory.mkdir(parents=True, exist_ok=True)
    final_path = media_directory / filename
    temporary_path = media_directory / f".{uuid4().hex}.upload"
    try:
        temporary_path.write_bytes(data)
        temporary_path.replace(final_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


@dataclass
class StoredImage:
    filename: str
    data: bytes
    in_database: bool


async def store_uploaded_image(db: Session, user_id: int, upload: UploadFile) -> StoredImage:
    """Persist an upload as a file or, with MEDIA_STORAGE=database, as a row in this session."""

    extension, data = await read_uploaded_image(upload)
    filename = new_media_filename(extension)
    if uses_database_media():
        db.add(MediaBlob(filename=filename, user_id=user_id, content_type=media_type_for(filename), data=data))
        return StoredImage(filename, data, True)
    write_media_file(filename, data)
    return StoredImage(filename, data, False)


def discard_stored_image(stored: StoredImage | None) -> None:
    """Undo a file write after a failed transaction; database rows roll back on their own."""

    if stored is not None and not stored.in_database:
        remove_uploaded_image(stored.filename)


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


def has_image_signature(extension: str, data: bytes) -> bool:
    if extension == ".webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return any(data.startswith(signature) for signature in IMAGE_SIGNATURES.get(extension, ()))


def validate_image_signature(extension: str, data: bytes) -> None:
    """Reject bytes that are not the image format their extension claims."""

    if not has_image_signature(extension, data):
        raise HTTPException(status_code=400, detail="The file is not a valid image of its stated type.")


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

    data = b"".join(chunks)
    validate_image_signature(extension, data)
    return extension, data


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
