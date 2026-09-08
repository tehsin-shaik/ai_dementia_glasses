"""Development caregiver identity and centralized patient access checks."""

from typing import Literal

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Caregiver, CaregiverPatientAccess


CAREGIVER_ID_HEADER = "X-MemoryCue-Caregiver-Id"
CaregiverPermission = Literal[
    "view",
    "manage_profile",
    "manage_people",
    "manage_schedule",
    "manage_objects",
    "manage_notes",
]


def get_current_caregiver(
    caregiver_id_header: str | None = Header(default=None, alias=CAREGIVER_ID_HEADER),
    db: Session = Depends(get_db),
) -> Caregiver:
    """Resolve the explicitly selected development caregiver for one request."""

    if caregiver_id_header is None or not caregiver_id_header.strip():
        raise HTTPException(status_code=401, detail="Caregiver identity is required.")

    try:
        caregiver_id = int(caregiver_id_header.strip())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Caregiver not found.") from exc

    caregiver = db.get(Caregiver, caregiver_id)
    if caregiver is None:
        raise HTTPException(status_code=404, detail="Caregiver not found.")
    return caregiver


def require_caregiver_access(
    db: Session,
    caregiver: Caregiver,
    patient_user_id: int,
    permission: CaregiverPermission,
) -> CaregiverPatientAccess:
    """Require a link and, for mutations, the matching explicit permission."""

    access = db.scalar(
        select(CaregiverPatientAccess).where(
            CaregiverPatientAccess.caregiver_id == caregiver.id,
            CaregiverPatientAccess.patient_user_id == patient_user_id,
        )
    )
    if access is None:
        raise HTTPException(status_code=404, detail="Patient access not found.")

    if permission == "view":
        return access
    if permission == "manage_profile":
        allowed = access.role == "primary"
    else:
        allowed = bool(getattr(access, f"can_{permission}"))
    if not allowed:
        raise HTTPException(status_code=403, detail="Caregiver permission required.")
    return access
