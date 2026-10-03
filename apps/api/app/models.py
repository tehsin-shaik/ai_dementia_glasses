"""SQLAlchemy models for the deterministic MemoryCue demo."""

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class PatientProfile(Base):
    __tablename__ = "patient_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, unique=True, index=True
    )
    preferred_name: Mapped[str] = mapped_column(String(120), nullable=False)
    short_bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    home_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_style: Mapped[str | None] = mapped_column(String(120), nullable=True)


class Caregiver(Base):
    __tablename__ = "caregivers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class CaregiverPatientAccess(Base):
    __tablename__ = "caregiver_patient_access"
    __table_args__ = (
        UniqueConstraint("caregiver_id", "patient_user_id", name="uq_caregiver_patient"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    caregiver_id: Mapped[int] = mapped_column(ForeignKey("caregivers.id"), nullable=False, index=True)
    patient_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(40), nullable=False, default="viewer")
    can_manage_people: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_manage_schedule: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_manage_objects: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_manage_notes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Observation(Base):
    """One captured moment from any source: raw evidence, not interpretation."""

    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    activity: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # [{"name": str, "person_id": int | None}]
    detected_people: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # [{"name": str, "location": str | None, "confidence": float | None}]
    detected_objects: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    raw_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extra: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    embedding_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=datetime.now)


class Event(Base):
    """A meaningful action or state interpreted from one or more observations."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    # How the event was produced: "reviewed", "rule:<name>", or "legacy_migration".
    inference: Mapped[str] = mapped_column(String(60), nullable=False)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    people: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    objects: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    embedding_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=datetime.now)


class Episode(Base):
    """A coherent stretch of activity grouping several events."""

    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    # The last evidence time; never extended past the newest event.
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # "rule:<name>" for a themed title, "locations" for a descriptive one.
    inference: Mapped[str] = mapped_column(String(60), nullable=False)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    people: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    objects: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    embedding_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=datetime.now)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=datetime.now, onupdate=datetime.now
    )


class EventObservation(Base):
    __tablename__ = "event_observations"

    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id"), primary_key=True, index=True)


class EpisodeEvent(Base):
    __tablename__ = "episode_events"

    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"), primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), primary_key=True, index=True)


class EpisodeObservation(Base):
    """Representative observations shown for an episode."""

    __tablename__ = "episode_observations"

    episode_id: Mapped[int] = mapped_column(ForeignKey("episodes.id"), primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id"), primary_key=True, index=True)


class Memory(Base):
    """The user-facing record worth retrieving later; reviewed before it is saved."""

    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    location: Mapped[str] = mapped_column(String(120), nullable=False)
    activity: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Columns below were added with the observation hierarchy and are nullable so
    # existing rows stay valid; see migrations.MEMORY_COLUMNS.
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    people: Mapped[list | None] = mapped_column(JSON, nullable=True)
    objects: Mapped[list | None] = mapped_column(JSON, nullable=True)
    episode_id: Mapped[int | None] = mapped_column(ForeignKey("episodes.id"), nullable=True, index=True)
    importance: Mapped[float | None] = mapped_column(Float, nullable=True)
    embedding_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MemoryObservation(Base):
    __tablename__ = "memory_observations"

    memory_id: Mapped[int] = mapped_column(ForeignKey("memories.id"), primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id"), primary_key=True, index=True)


class MemoryEvent(Base):
    __tablename__ = "memory_events"

    memory_id: Mapped[int] = mapped_column(ForeignKey("memories.id"), primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), primary_key=True, index=True)


class MediaBlob(Base):
    """Image bytes kept in the database so hosted photos outlive a serverless instance."""

    __tablename__ = "media_blobs"

    filename: Mapped[str] = mapped_column(String(255), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    content_type: Mapped[str] = mapped_column(String(40), nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class ObjectObservation(Base):
    __tablename__ = "object_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    object_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    location: Mapped[str] = mapped_column(String(120), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    memory_id: Mapped[int] = mapped_column(ForeignKey("memories.id"), nullable=False)


class MemoryCorrection(Base):
    """One caregiver correction of a saved detail, kept beside the original."""

    __tablename__ = "memory_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    memory_id: Mapped[int] = mapped_column(ForeignKey("memories.id"), nullable=False, index=True)
    patient_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    caregiver_id: Mapped[int] = mapped_column(ForeignKey("caregivers.id"), nullable=False, index=True)
    field: Mapped[str] = mapped_column(String(40), nullable=False)
    old_value: Mapped[str] = mapped_column(Text, nullable=False)
    new_value: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class Person(Base):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    relationship: Mapped[str] = mapped_column(String(120), nullable=False)


class PersonFaceEnrollment(Base):
    """One caregiver-approved local face embedding for a patient person record."""

    __tablename__ = "person_face_enrollments"
    __table_args__ = (UniqueConstraint("person_id", name="uq_person_face_enrollment_person"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), nullable=False, index=True)
    patient_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    embedding: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, index=True)


class RecognitionEvent(Base):
    """The latest explicit recognition event for one patient person."""

    __tablename__ = "recognition_events"
    __table_args__ = (UniqueConstraint("user_id", "person_id", name="uq_recognition_event_person"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), nullable=False, index=True)
    recognized_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class ScheduleItem(Base):
    __tablename__ = "schedule_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class ImportantObject(Base):
    __tablename__ = "important_objects"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_important_object_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CaregiverNote(Base):
    __tablename__ = "caregiver_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    caregiver_id: Mapped[int] = mapped_column(ForeignKey("caregivers.id"), nullable=False, index=True)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, index=True)


class CueState(Base):
    """Patient-scoped presentation and dismissal state for one cue key."""

    __tablename__ = "cue_states"
    __table_args__ = (UniqueConstraint("user_id", "cue_key", name="uq_cue_state_user_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    cue_key: Mapped[str] = mapped_column(String(255), nullable=False)
    last_shown_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CuePresentation(Base):
    """Idempotency record for one client-reported visible cue presentation."""

    __tablename__ = "cue_presentations"
    __table_args__ = (
        UniqueConstraint("user_id", "presentation_id", name="uq_cue_presentation_user_token"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    cue_key: Mapped[str] = mapped_column(String(255), nullable=False)
    presentation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    presented_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
