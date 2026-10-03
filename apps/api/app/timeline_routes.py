"""Read and write endpoints for observations, events, and episodes.

`POST /api/observations` is the source-agnostic capture entry point: any
device sends the same fields and names itself in `source`.
"""

from datetime import date, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from .database import get_db
from .episode_service import consolidate_and_commit, consolidate_in_background
from .formatting import media_url
from .identity import get_current_user
from .media_storage import StoredImage, discard_stored_image, store_uploaded_image
from .memory_text import episode_to_text, event_to_text, observation_to_text
from .models import Episode, Event, Observation, User
from .observation_service import (
    ObservationInput,
    ObservationValidationError,
    analyze_image,
    apply_analysis,
    create_observation,
)
from .retention_service import cleanup_in_background
from .retrieval_service import (
    episode_links,
    event_ids_for_observations,
    list_episodes,
    list_events,
    list_observations,
    observation_ids_for_events,
)
from .schemas import (
    ConsolidationResponse,
    EpisodeResponse,
    EventResponse,
    NamedEntity,
    ObservationResponse,
    ObservationSource,
)

router = APIRouter(prefix="/api", tags=["timeline"])


def _entities(entries: list | None) -> list[NamedEntity]:
    return [NamedEntity.model_validate(entry) for entry in entries or [] if isinstance(entry, dict)]


def observation_response(observation: Observation, event_ids: list[int]) -> ObservationResponse:
    return ObservationResponse(
        id=observation.id,
        timestamp=observation.timestamp,
        source=observation.source,
        image_url=media_url(observation.image_path),
        transcript=observation.transcript,
        latitude=observation.latitude,
        longitude=observation.longitude,
        location_label=observation.location_label,
        description=observation.description,
        activity=observation.activity,
        people=_entities(observation.detected_people),
        objects=_entities(observation.detected_objects),
        reviewed=observation.reviewed,
        analysis=(observation.extra or {}).get("analysis"),
        metadata=observation.extra or {},
        event_ids=event_ids,
        text=observation_to_text(observation),
        created_at=observation.created_at,
    )


def event_response(event: Event, observation_ids: list[int]) -> EventResponse:
    return EventResponse(
        id=event.id,
        start_time=event.start_time,
        end_time=event.end_time,
        event_type=event.event_type,
        title=event.title,
        description=event.description,
        confidence=event.confidence,
        inference=event.inference,
        location=event.location,
        people=_entities(event.people),
        objects=_entities(event.objects),
        observation_ids=observation_ids,
        text=event_to_text(event),
        created_at=event.created_at,
    )


def episode_response(episode: Episode, event_ids: list[int], observation_ids: list[int]) -> EpisodeResponse:
    return EpisodeResponse(
        id=episode.id,
        start_time=episode.start_time,
        end_time=episode.end_time,
        title=episode.title,
        summary=episode.summary,
        inference=episode.inference,
        location=episode.location,
        people=_entities(episode.people),
        objects=_entities(episode.objects),
        confidence=episode.confidence,
        event_ids=event_ids,
        representative_observation_ids=observation_ids,
        text=episode_to_text(episode),
        created_at=episode.created_at,
        updated_at=episode.updated_at,
    )


def _names(value: str | None) -> list[str]:
    return [name.strip() for name in (value or "").split(",") if name.strip()]


@router.post("/observations", response_model=ObservationResponse, status_code=201)
async def post_observation(
    background_tasks: BackgroundTasks,
    timestamp: datetime = Form(...),
    source: ObservationSource = Form(...),
    image: UploadFile | None = File(default=None),
    transcript: str | None = Form(default=None),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
    location_label: str | None = Form(default=None),
    people: str | None = Form(default=None, description="Comma-separated names mentioned or present."),
    analyze: bool = Form(default=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ObservationResponse:
    data = ObservationInput(
        timestamp=timestamp,
        source=source,
        transcript=transcript,
        latitude=latitude,
        longitude=longitude,
        location_label=location_label,
        people=_names(people),
    )
    stored: StoredImage | None = None
    try:
        if image is not None:
            stored = await store_uploaded_image(db, current_user.id, image)
            data.image_path = stored.filename
            if analyze:
                analysis, outcome = await analyze_image(stored.data, image.filename or stored.filename)
                data.metadata["analysis"] = outcome
                if analysis is not None:
                    apply_analysis(data, analysis, outcome)
        observation = create_observation(db, current_user.id, data)
        response = observation_response(observation, event_ids_for_observations(db, [observation.id])[observation.id])
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
    background_tasks.add_task(cleanup_in_background, db.get_bind(), current_user.id)
    return response


@router.get("/observations", response_model=list[ObservationResponse])
def get_observations(
    day: date | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ObservationResponse]:
    observations = list_observations(db, current_user.id, day=day, since=since, limit=limit)
    linked = event_ids_for_observations(db, [observation.id for observation in observations])
    return [observation_response(observation, linked[observation.id]) for observation in observations]


@router.get("/events", response_model=list[EventResponse])
def get_events(
    day: date | None = Query(default=None),
    since: datetime | None = Query(default=None),
    min_confidence: float = Query(default=0.0, ge=0.0, le=1.0),
    limit: int = Query(default=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EventResponse]:
    events = list_events(db, current_user.id, day=day, since=since, min_confidence=min_confidence, limit=limit)
    linked = observation_ids_for_events(db, [event.id for event in events])
    return [event_response(event, linked[event.id]) for event in events]


@router.get("/episodes", response_model=list[EpisodeResponse])
def get_episodes(
    day: date | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EpisodeResponse]:
    episodes = list_episodes(db, current_user.id, day=day, since=since, limit=limit)
    event_ids, observation_ids = episode_links(db, [episode.id for episode in episodes])
    return [episode_response(episode, event_ids[episode.id], observation_ids[episode.id]) for episode in episodes]


@router.post("/episodes/consolidate", response_model=ConsolidationResponse)
def post_consolidate(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConsolidationResponse:
    """Group any events not yet in an episode; safe to call repeatedly or on a schedule."""

    episodes = consolidate_and_commit(db, current_user.id)
    return ConsolidationResponse(episode_ids=sorted(episode.id for episode in episodes))
