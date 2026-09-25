"""Caregiver corrections of saved details, kept beside the original record."""

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .authorization import CaregiverPermission
from .formatting import media_url
from .models import Caregiver, Memory, MemoryCorrection, ObjectObservation
from .schemas import (
    CorrectionField,
    MemoryCorrectionResponse,
    SavedMomentResponse,
)

FIELD_PERMISSIONS: dict[str, CaregiverPermission] = {
    "description": "manage_notes",
    "object_name": "manage_objects",
    "object_location": "manage_objects",
}


def required_permission(field: CorrectionField) -> CaregiverPermission:
    return FIELD_PERMISSIONS[field]


def get_memory(db: Session, patient_user_id: int, memory_id: int) -> Memory:
    memory = db.scalar(
        select(Memory).where(Memory.id == memory_id, Memory.user_id == patient_user_id)
    )
    if memory is None:
        raise HTTPException(status_code=404, detail="Saved moment not found.")
    return memory


def memory_observation(db: Session, memory_id: int) -> ObjectObservation | None:
    return db.scalar(
        select(ObjectObservation).where(ObjectObservation.memory_id == memory_id)
    )


def latest_correction(db: Session, memory_id: int) -> tuple[datetime, str] | None:
    """The newest caregiver correction for a moment, kept apart from its capture."""

    row = db.execute(
        select(MemoryCorrection.corrected_at, Caregiver.name)
        .join(Caregiver, Caregiver.id == MemoryCorrection.caregiver_id)
        .where(MemoryCorrection.memory_id == memory_id)
        .order_by(MemoryCorrection.corrected_at.desc(), MemoryCorrection.id.desc())
        .limit(1)
    ).first()
    return (row[0], row[1]) if row else None


def correction_history(db: Session, memory_id: int) -> list[MemoryCorrectionResponse]:
    rows = db.execute(
        select(MemoryCorrection, Caregiver.name)
        .join(Caregiver, Caregiver.id == MemoryCorrection.caregiver_id)
        .where(MemoryCorrection.memory_id == memory_id)
        .order_by(MemoryCorrection.corrected_at.desc(), MemoryCorrection.id.desc())
    ).all()
    return [
        MemoryCorrectionResponse(
            id=correction.id,
            memory_id=correction.memory_id,
            caregiver_id=correction.caregiver_id,
            caregiver_name=caregiver_name,
            field=correction.field,  # type: ignore[arg-type]
            old_value=correction.old_value,
            new_value=correction.new_value,
            corrected_at=correction.corrected_at,
        )
        for correction, caregiver_name in rows
    ]


def saved_moment(db: Session, memory: Memory) -> SavedMomentResponse:
    observation = memory_observation(db, memory.id)
    return SavedMomentResponse(
        memory_id=memory.id,
        recorded_at=memory.timestamp,
        location=memory.location,
        description=memory.description,
        image_url=media_url(memory.image_path),
        object_name=observation.object_name if observation else None,
        object_location=observation.location if observation else None,
        corrections=correction_history(db, memory.id),
    )


def apply_correction(
    db: Session,
    patient_user_id: int,
    memory: Memory,
    caregiver_id: int,
    field: CorrectionField,
    value: str,
    now: datetime | None = None,
) -> SavedMomentResponse:
    """Correct one saved detail, leaving the capture and its observed time alone."""

    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="Correction cannot be empty.")

    if field == "description":
        old_value = memory.description
        memory.description = cleaned
    else:
        observation = memory_observation(db, memory.id)
        if observation is None:
            raise HTTPException(
                status_code=422,
                detail="This saved moment has no recorded object to correct.",
            )
        if field == "object_name":
            old_value = observation.object_name
            observation.object_name = cleaned
        else:
            old_value = observation.location
            observation.location = cleaned

    db.add(
        MemoryCorrection(
            memory_id=memory.id,
            patient_user_id=patient_user_id,
            caregiver_id=caregiver_id,
            field=field,
            old_value=old_value,
            new_value=cleaned,
            corrected_at=now or datetime.now(),
        )
    )
    db.commit()
    return saved_moment(db, memory)
