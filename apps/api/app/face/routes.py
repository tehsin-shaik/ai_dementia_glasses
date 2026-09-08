"""Patient-facing, single-frame known-person recognition endpoint."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..identity import get_current_user
from ..media_storage import read_uploaded_image
from ..models import Person, PersonFaceEnrollment, User
from ..schemas import FaceRecognitionResponse
from . import provider as face_provider
from .base import FaceRecognizerNotConfiguredError, MultipleFacesFoundError, NoFaceFoundError
from .service import MatchCandidate, choose_match, deserialize_embedding


router = APIRouter(prefix="/api/face", tags=["face"])


def unknown_response(confidence: float = 0.0) -> FaceRecognitionResponse:
    return FaceRecognitionResponse(
        recognized=False,
        person_id=None,
        name=None,
        relationship=None,
        confidence=max(0.0, min(1.0, confidence)),
    )


@router.post("/recognize", response_model=FaceRecognitionResponse)
async def recognize_face(
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FaceRecognitionResponse:
    _, image_bytes = await read_uploaded_image(image)
    enrollments = list(
        db.execute(
            select(PersonFaceEnrollment, Person)
            .join(Person, Person.id == PersonFaceEnrollment.person_id)
            .where(
                PersonFaceEnrollment.patient_user_id == current_user.id,
                Person.user_id == current_user.id,
            )
        )
    )
    if not enrollments:
        return unknown_response()

    try:
        recognizer = face_provider.get_face_recognizer()
    except FaceRecognizerNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail="Face recognition is not configured.") from exc

    try:
        query_embedding = recognizer.extract_embedding(image_bytes)
    except (NoFaceFoundError, MultipleFacesFoundError):
        return unknown_response()
    except FaceRecognizerNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail="Face recognition is not configured.") from exc

    candidates: list[MatchCandidate] = []
    people_by_id: dict[int, Person] = {}
    for enrollment, person in enrollments:
        try:
            embedding = deserialize_embedding(enrollment.embedding)
        except (TypeError, ValueError):
            continue
        candidates.append(MatchCandidate(person_id=person.id, embedding=embedding))
        people_by_id[person.id] = person

    decision = choose_match(query_embedding, candidates, recognizer)
    if decision.person_id is None or decision.person_id not in people_by_id:
        return unknown_response(decision.confidence)

    person = people_by_id[decision.person_id]
    return FaceRecognitionResponse(
        recognized=True,
        person_id=person.id,
        name=person.name,
        relationship=person.relationship,
        confidence=decision.confidence,
    )
