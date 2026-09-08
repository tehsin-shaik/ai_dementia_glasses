"""FastAPI entry point for the MemoryCue vertical slice."""

from datetime import datetime

from fastapi import Depends, File, Form, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models  # noqa: F401 - registers models before table creation
from .database import get_db, init_db
from .media_storage import (
    media_type_for,
    remove_uploaded_image,
    read_uploaded_image,
    safe_media_path,
    save_uploaded_image,
)
from .models import Memory, ObjectObservation, User
from .query_service import answer_question
from .schemas import (
    HealthResponse,
    MemoryListItem,
    MemoryResponse,
    QueryRequest,
    QueryResponse,
    SeedResponse,
)
from .seed import seed_demo_data
from .vision import VisionAnalysis
from .vision import provider as vision_provider
from .vision.provider import VisionProviderError, VisionProviderNotConfiguredError


init_db()

app = FastAPI(title="MemoryCue API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/demo/seed", response_model=SeedResponse)
def seed_demo(db: Session = Depends(get_db)) -> SeedResponse:
    return SeedResponse(status="ok", **seed_demo_data(db))


@app.post("/api/query", response_model=QueryResponse)
def query(request: QueryRequest, db: Session = Depends(get_db)) -> QueryResponse:
    return answer_question(db, request.question)


def first_user(db: Session) -> User | None:
    return db.scalar(select(User).order_by(User.id).limit(1))


def image_url(image_path: str | None) -> str | None:
    if image_path is None:
        return None
    return f"/api/media/{image_path}"


@app.post("/api/memories", response_model=MemoryResponse, status_code=201)
async def create_memory(
    image: UploadFile = File(...),
    timestamp: datetime = Form(...),
    location: str = Form(...),
    description: str = Form(...),
    activity: str | None = Form(default=None),
    object_name: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> MemoryResponse:
    location_value = location.strip()
    description_value = description.strip()
    activity_value = (activity or "").strip()
    object_name_value = (object_name or "").strip()
    if not location_value:
        raise HTTPException(status_code=422, detail="Location cannot be empty.")
    if len(location_value) > 120:
        raise HTTPException(status_code=422, detail="Location cannot exceed 120 characters.")
    if not description_value:
        raise HTTPException(status_code=422, detail="Description cannot be empty.")
    if len(description_value) > 500:
        raise HTTPException(status_code=422, detail="Description cannot exceed 500 characters.")
    if len(activity_value) > 200:
        raise HTTPException(status_code=422, detail="Activity cannot exceed 200 characters.")
    if len(object_name_value) > 120:
        raise HTTPException(status_code=422, detail="Object name cannot exceed 120 characters.")

    # Store timestamps consistently as naive local wall-clock datetimes for SQLite.
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone().replace(tzinfo=None)

    stored_filename = await save_uploaded_image(image)
    try:
        user = first_user(db)
        if user is None:
            user = User(name="Demo User")
            db.add(user)
            db.flush()

        memory = Memory(
            user_id=user.id,
            timestamp=timestamp,
            location=location_value,
            activity=activity_value,
            description=description_value,
            image_path=stored_filename,
        )

        db.add(memory)
        db.flush()

        observation = None
        normalized_object_name = object_name_value.casefold()
        if normalized_object_name:
            observation = ObjectObservation(
                user_id=user.id,
                object_name=normalized_object_name,
                location=location_value,
                observed_at=timestamp,
                memory_id=memory.id,
            )
            db.add(observation)
            db.flush()

        response = MemoryResponse(
            id=memory.id,
            timestamp=memory.timestamp,
            location=memory.location,
            activity=memory.activity or None,
            description=memory.description,
            image_url=image_url(memory.image_path),
            object_observation_id=observation.id if observation else None,
        )
        db.commit()
        return response
    except Exception:
        db.rollback()
        remove_uploaded_image(stored_filename)
        raise


@app.post("/api/vision/analyze", response_model=VisionAnalysis)
async def analyze_vision(
    image: UploadFile = File(...),
    context: str | None = Form(default=None),
) -> VisionAnalysis:
    """Analyze an uploaded image without creating a memory."""

    context_value = context.strip() if context else None
    if context_value and len(context_value) > 500:
        raise HTTPException(status_code=422, detail="Context cannot exceed 500 characters.")

    extension, image_bytes = await read_uploaded_image(image)
    try:
        analyzer = vision_provider.get_vision_analyzer()
    except VisionProviderNotConfiguredError as exc:
        raise HTTPException(
            status_code=503,
            detail="Vision analysis is not configured.",
        ) from exc
    except VisionProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail="Vision analysis is unavailable.",
        ) from exc

    try:
        analysis = await analyzer.analyze_image(
            image_bytes=image_bytes,
            filename=image.filename or f"image{extension}",
            context=context_value,
        )
        return VisionAnalysis.model_validate(analysis)
    except (VisionProviderError, ValidationError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="The image could not be analyzed.",
        ) from exc


@app.get("/api/memories", response_model=list[MemoryListItem])
def list_memories(db: Session = Depends(get_db)) -> list[MemoryListItem]:
    user = first_user(db)
    if user is None:
        return []

    memories = list(
        db.scalars(
            select(Memory)
            .where(Memory.user_id == user.id)
            .order_by(Memory.timestamp.desc(), Memory.id.desc())
        )
    )
    return [
        MemoryListItem(
            id=memory.id,
            timestamp=memory.timestamp,
            location=memory.location,
            description=memory.description,
            image_url=image_url(memory.image_path),
        )
        for memory in memories
    ]


@app.get("/api/media/{filename:path}")
def get_media(filename: str) -> FileResponse:
    path = safe_media_path(filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Media file not found.")
    return FileResponse(path=path, media_type=media_type_for(path.name))
