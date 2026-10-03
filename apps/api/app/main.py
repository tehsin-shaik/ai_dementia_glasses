"""FastAPI entry point for the MemoryCue vertical slice."""

from datetime import datetime
import os

from fastapi import BackgroundTasks, Depends, File, Form, FastAPI, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models  # noqa: F401 - registers models before table creation
from .caregiver import router as caregiver_router
from .cues.routes import router as cues_router
from .database import SessionLocal, engine, get_db, init_db
from .migrations import run_migrations
from .face.routes import router as face_router
from .identity import get_current_user
from .episode_service import consolidate_in_background
from .media_storage import (
    StoredImage,
    discard_stored_image,
    media_type_for,
    read_uploaded_image,
    safe_media_path,
    store_uploaded_image,
)
from .memory_service import save_reviewed_moment
from .models import MediaBlob, Memory, Observation, User
from .observation_service import ObservationValidationError
from .query_service import answer_question
from .retrieval_service import episodes_by_id
from .rewind_service import DEFAULT_WINDOW_MINUTES, build_rewind
from .runtime import allowed_origins, seed_if_empty
from .schemas import (
    HealthResponse,
    Language,
    MemoryListItem,
    MemoryResponse,
    ObservationSource,
    QueryRequest,
    QueryResponse,
    RewindResponse,
    SeedResponse,
)
from .seed import seed_demo_data
from .timeline_routes import router as timeline_router
from .vision import VisionAnalysis
from .vision import provider as vision_provider
from .vision.provider import VisionProviderError, VisionProviderNotConfiguredError


init_db()
run_migrations(engine, SessionLocal)

if os.getenv("SEED_ON_STARTUP") == "1":
    with SessionLocal() as startup_session:
        seed_if_empty(startup_session)

app = FastAPI(title="MemoryCue API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)
app.include_router(caregiver_router)
app.include_router(face_router)
app.include_router(cues_router)
app.include_router(timeline_router)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/demo/seed", response_model=SeedResponse)
def seed_demo(db: Session = Depends(get_db)) -> SeedResponse:
    return SeedResponse(status="ok", **seed_demo_data(db))


@app.post("/api/query", response_model=QueryResponse)
def query(
    request: QueryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QueryResponse:
    return answer_question(db, current_user.id, request.question, request.language)


@app.get("/api/rewind", response_model=RewindResponse)
def rewind(
    window_minutes: int = Query(default=DEFAULT_WINDOW_MINUTES, ge=1, le=1440),
    include_earlier: bool = False,
    language: Language = "en",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RewindResponse:
    return build_rewind(
        db,
        current_user.id,
        window_minutes=window_minutes,
        include_earlier=include_earlier,
        language=language,
    )


def image_url(image_path: str | None) -> str | None:
    if image_path is None:
        return None
    return f"/api/media/{image_path}"


@app.post("/api/memories", response_model=MemoryResponse, status_code=201)
async def create_memory(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...),
    timestamp: datetime = Form(...),
    location: str = Form(...),
    description: str = Form(...),
    activity: str | None = Form(default=None),
    object_name: str | None = Form(default=None),
    source: ObservationSource = Form(default="other"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryResponse:
    """Save a reviewed moment: Observation -> Events -> Memory; episodes group afterwards."""

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

    stored: StoredImage | None = None
    try:
        stored = await store_uploaded_image(db, current_user.id, image)
        saved = save_reviewed_moment(
            db,
            current_user.id,
            timestamp=timestamp,
            location=location_value,
            description=description_value,
            activity=activity_value,
            object_name=object_name_value,
            image_path=stored.filename,
            source=source,
        )
        memory = saved.memory
        response = MemoryResponse(
            id=memory.id,
            timestamp=memory.timestamp,
            location=memory.location,
            activity=memory.activity or None,
            description=memory.description,
            image_url=image_url(memory.image_path),
            object_observation_id=saved.object_observation.id if saved.object_observation else None,
        )
        db.commit()
    except ObservationValidationError as exc:
        db.rollback()
        discard_stored_image(stored)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        discard_stored_image(stored)
        raise
    background_tasks.add_task(consolidate_in_background, db.get_bind(), current_user.id)
    return response


@app.post("/api/vision/analyze", response_model=VisionAnalysis)
async def analyze_vision(
    image: UploadFile = File(...),
    context: str | None = Form(default=None),
    _current_user: User = Depends(get_current_user),
) -> VisionAnalysis:
    """Analyze an uploaded image without creating a memory."""

    context_value = context.strip() if context else None
    if context_value and len(context_value) > 500:
        raise HTTPException(status_code=422, detail="Context cannot exceed 500 characters.")

    extension, image_bytes = await read_uploaded_image(image)
    demo_analysis = vision_provider.demo_vision_analysis(image.filename)
    if demo_analysis:
        return demo_analysis
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
def list_memories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[MemoryListItem]:
    memories = list(
        db.scalars(
            select(Memory)
            .where(Memory.user_id == current_user.id)
            .order_by(Memory.timestamp.desc(), Memory.id.desc())
        )
    )
    episodes = episodes_by_id(db, current_user.id, {memory.episode_id for memory in memories if memory.episode_id})
    return [
        MemoryListItem(
            id=memory.id,
            timestamp=memory.timestamp,
            location=memory.location,
            description=memory.description,
            image_url=image_url(memory.image_path),
            title=memory.title,
            episode_id=memory.episode_id,
            episode_title=episodes[memory.episode_id].title if memory.episode_id in episodes else None,
        )
        for memory in memories
    ]


@app.get("/api/media/{filename:path}")
def get_media(
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    path = safe_media_path(filename)
    memory = db.scalar(
        select(Memory.id).where(
            Memory.user_id == current_user.id,
            Memory.image_path == filename,
        )
    )
    observation = db.scalar(
        select(Observation.id).where(
            Observation.user_id == current_user.id,
            Observation.image_path == filename,
        )
    )
    if memory is None and observation is None:
        raise HTTPException(status_code=404, detail="Media file not found.")
    blob = db.get(MediaBlob, filename)
    if blob is not None:
        return Response(content=blob.data, media_type=blob.content_type)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Media file not found.")
    return FileResponse(path=path, media_type=media_type_for(path.name))
