"""Patient-scoped endpoints for current proactive cues."""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..identity import get_current_user
from ..models import User
from .schemas import CueDismissResponse, CueListResponse
from .service import CueEngine


router = APIRouter(prefix="/api/cues", tags=["cues"])
cue_engine = CueEngine()


@router.get("", response_model=CueListResponse)
def list_cues(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CueListResponse:
    candidates = cue_engine.evaluate(db, current_user.id)
    cues = candidates[:1]
    if cues:
        cue_engine.mark_presented(db, current_user.id, cues[0].id, datetime.now())
        db.commit()
    return CueListResponse(cues=cues)


@router.post("/{cue_id:path}/dismiss", response_model=CueDismissResponse)
def dismiss_cue(
    cue_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CueDismissResponse:
    cue_engine.dismiss(db, current_user.id, cue_id, datetime.now())
    db.commit()
    return CueDismissResponse(status="dismissed", cue_id=cue_id)
