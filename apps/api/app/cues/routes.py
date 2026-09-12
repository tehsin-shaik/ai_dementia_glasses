"""Patient-scoped endpoints for current proactive cues."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..identity import get_current_user
from ..models import User
from .schemas import (
    CueDismissResponse,
    CueListResponse,
    CuePresentationRequest,
    CuePresentationResponse,
)
from .service import CueEngine, CueNotEligibleError, CuePresentationConflictError


router = APIRouter(prefix="/api/cues", tags=["cues"])
cue_engine = CueEngine()


@router.get("", response_model=CueListResponse)
def list_cues(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CueListResponse:
    candidates = cue_engine.evaluate(db, current_user.id)
    return CueListResponse(cues=candidates[:1])


@router.post("/present", response_model=CuePresentationResponse)
def acknowledge_cue_presentation(
    payload: CuePresentationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CuePresentationResponse:
    try:
        status, presented_at = cue_engine.acknowledge_presentation(
            db,
            current_user.id,
            payload.cue_id,
            str(payload.presentation_id),
            datetime.now(),
        )
    except (CueNotEligibleError, CuePresentationConflictError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return CuePresentationResponse(
        status=status,
        cue_id=payload.cue_id,
        presented_at=presented_at,
    )


@router.post("/{cue_id:path}/dismiss", response_model=CueDismissResponse)
def dismiss_cue(
    cue_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CueDismissResponse:
    cue_engine.dismiss(db, current_user.id, cue_id, datetime.now())
    db.commit()
    return CueDismissResponse(status="dismissed", cue_id=cue_id)
