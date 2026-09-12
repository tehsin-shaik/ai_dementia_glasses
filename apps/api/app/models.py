"""SQLAlchemy models for the deterministic MemoryCue demo."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    location: Mapped[str] = mapped_column(String(120), nullable=False)
    activity: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ObjectObservation(Base):
    __tablename__ = "object_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    object_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    location: Mapped[str] = mapped_column(String(120), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    memory_id: Mapped[int] = mapped_column(ForeignKey("memories.id"), nullable=False)


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
