"""The single entry point that turns any capture source into an Observation.

The service never branches on `source`: a browser camera, a phone, or glasses
all produce the same record, so new capture hardware only needs to call it.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import os

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .event_service import events_for_observation
from .models import Observation, Person, User
from .vision import VisionAnalysis
from .vision import provider as vision_provider
from .vision.provider import VisionProviderError, VisionProviderNotConfiguredError

OBSERVATION_SOURCES = (
    "browser_camera",
    "iphone_camera",
    "meta_glasses",
    "uploaded_image",
    "other",
)
FUTURE_TOLERANCE = timedelta(days=1)
logger = logging.getLogger(__name__)
EARLIEST_TIMESTAMP = datetime(2000, 1, 1)


class ObservationValidationError(ValueError):
    """Raised when an observation cannot be stored as given."""


@dataclass
class ObservationInput:
    timestamp: datetime
    source: str = "other"
    image_path: str | None = None
    transcript: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_label: str | None = None
    description: str | None = None
    activity: str | None = None
    people: list[str] = field(default_factory=list)
    objects: list[dict] = field(default_factory=list)
    raw_analysis: dict | None = None
    reviewed: bool = False
    metadata: dict = field(default_factory=dict)


def normalize_timestamp(value: datetime) -> datetime:
    """Store naive local wall-clock time, matching the rest of the schema."""

    if value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value


def _clean(value: str | None, label: str, limit: int) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if len(cleaned) > limit:
        raise ObservationValidationError(f"{label} cannot exceed {limit} characters.")
    return cleaned or None


def normalize_objects(objects: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    seen: set[str] = set()
    for entry in objects:
        name = str(entry.get("name") or "").strip().casefold()
        if not name or name in seen:
            continue
        seen.add(name)
        location = entry.get("location")
        confidence = entry.get("confidence")
        normalized.append(
            {
                "name": name[:120],
                "location": str(location).strip()[:120] if location else None,
                "confidence": float(confidence) if confidence is not None else None,
            }
        )
    return normalized


def match_people(db: Session, user_id: int, names: list[str]) -> list[dict]:
    """Attach caregiver-entered Person ids to names; unknown names stay unlinked."""

    people: list[dict] = []
    seen: set[str] = set()
    for raw_name in names:
        name = raw_name.strip()
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        person = db.scalar(
            select(Person).where(Person.user_id == user_id, Person.name.ilike(name)).order_by(Person.id).limit(1)
        )
        people.append({"name": person.name if person else name[:120], "person_id": person.id if person else None})
    return people


def apply_analysis(data: ObservationInput, analysis: VisionAnalysis, provider: str) -> ObservationInput:
    """Keep the provider's raw output and fill only fields the capture left empty."""

    data.raw_analysis = {"provider": provider, "response": analysis.model_dump(mode="json")}
    data.description = data.description or analysis.description
    data.location_label = data.location_label or analysis.location
    data.activity = data.activity or analysis.activity
    data.objects = [*data.objects, *(item.model_dump() for item in analysis.objects)]
    return data


async def analyze_image(image_bytes: bytes, filename: str, context: str | None = None) -> tuple[VisionAnalysis | None, str]:
    """Run the existing vision pipeline; returns (analysis, outcome) and never raises.

    Outcomes: "demo_scene", "<provider name>", "not_configured", or "failed".
    A missing or failing provider still lets the observation be stored.
    """

    demo = vision_provider.demo_vision_analysis(filename)
    if demo is not None:
        return demo, "demo_scene"
    try:
        analyzer = vision_provider.get_vision_analyzer()
    except VisionProviderNotConfiguredError:
        return None, "not_configured"
    except VisionProviderError:
        return None, "failed"
    try:
        result = await analyzer.analyze_image(image_bytes=image_bytes, filename=filename, context=context)
        return VisionAnalysis.model_validate(result), (os.getenv("VISION_PROVIDER") or "").strip().casefold()
    except (VisionProviderError, ValidationError, TypeError, ValueError):
        return None, "failed"


def validate(data: ObservationInput) -> ObservationInput:
    if data.source not in OBSERVATION_SOURCES:
        raise ObservationValidationError(
            f"Source must be one of: {', '.join(OBSERVATION_SOURCES)}."
        )
    data.timestamp = normalize_timestamp(data.timestamp)
    if data.timestamp < EARLIEST_TIMESTAMP or data.timestamp > datetime.now() + FUTURE_TOLERANCE:
        raise ObservationValidationError("Timestamp is outside the accepted range.")
    if (data.latitude is None) != (data.longitude is None):
        raise ObservationValidationError("Latitude and longitude must be provided together.")
    if data.latitude is not None and not -90 <= data.latitude <= 90:
        raise ObservationValidationError("Latitude must be between -90 and 90.")
    if data.longitude is not None and not -180 <= data.longitude <= 180:
        raise ObservationValidationError("Longitude must be between -180 and 180.")
    data.transcript = _clean(data.transcript, "Transcript", 2000)
    data.location_label = _clean(data.location_label, "Location", 120)
    data.description = _clean(data.description, "Description", 500)
    data.activity = _clean(data.activity, "Activity", 200)
    return data


def create_observation(
    db: Session,
    user_id: int,
    data: ObservationInput,
    *,
    generate_events: bool = True,
) -> Observation:
    """Validate and store one observation, then derive conservative events from it."""

    if db.get(User, user_id) is None:
        raise ObservationValidationError("Unknown user.")
    data = validate(data)
    observation = Observation(
        user_id=user_id,
        timestamp=data.timestamp,
        source=data.source,
        image_path=data.image_path,
        transcript=data.transcript,
        latitude=data.latitude,
        longitude=data.longitude,
        location_label=data.location_label,
        description=data.description,
        activity=data.activity,
        detected_people=match_people(db, user_id, data.people),
        detected_objects=normalize_objects(data.objects),
        raw_analysis=data.raw_analysis,
        reviewed=data.reviewed,
        extra=data.metadata,
        created_at=datetime.now(),
    )
    db.add(observation)
    db.flush()
    if generate_events:
        try:
            with db.begin_nested():
                events_for_observation(db, observation)
        except Exception:
            logger.exception("Event inference failed for observation %s; it is kept without events.", observation.id)
    return observation
