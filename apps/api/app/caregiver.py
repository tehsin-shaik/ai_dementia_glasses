"""Small caregiver setup API with explicit patient access checks."""

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .authorization import get_current_caregiver, require_caregiver_access
from .database import get_db
from .models import (
    Caregiver,
    CaregiverNote,
    CaregiverPatientAccess,
    ImportantObject,
    PatientProfile,
    Person,
    PersonFaceEnrollment,
    RecognitionEvent,
    ScheduleItem,
    User,
)
from .schemas import (
    CaregiverNoteCreate,
    CaregiverNoteResponse,
    FaceEnrollmentStatus,
    ImportantObjectCreate,
    ImportantObjectPatch,
    ImportantObjectResponse,
    PatientProfilePatch,
    PatientProfileResponse,
    PatientSummary,
    PersonCreate,
    PersonPatch,
    PersonResponse,
    ScheduleCreate,
    SchedulePatch,
    ScheduleResponse,
)
from .face import provider as face_provider
from .face.base import FaceRecognizerNotConfiguredError, MultipleFacesFoundError, NoFaceFoundError
from .face.service import serialize_embedding
from .media_storage import read_uploaded_image


router = APIRouter(prefix="/api/caregiver", tags=["caregiver"])


def _required_text(value: str, field_name: str, max_length: int) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail=f"{field_name} cannot be empty.")
    if len(cleaned) > max_length:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} cannot exceed {max_length} characters.",
        )
    return cleaned


def _optional_text(value: str | None, field_name: str, max_length: int) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if len(cleaned) > max_length:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} cannot exceed {max_length} characters.",
        )
    return cleaned or None


def _profile_response(profile: PatientProfile) -> PatientProfileResponse:
    return PatientProfileResponse(
        user_id=profile.user_id,
        preferred_name=profile.preferred_name,
        short_bio=profile.short_bio,
        home_context=profile.home_context,
        response_style=profile.response_style,
    )


def _get_profile(db: Session, patient_user_id: int) -> PatientProfile:
    profile = db.scalar(select(PatientProfile).where(PatientProfile.user_id == patient_user_id))
    if profile is None:
        raise HTTPException(status_code=404, detail="Patient profile not found.")
    return profile


def _get_person(db: Session, patient_user_id: int, person_id: int) -> Person:
    person = db.scalar(
        select(Person).where(Person.id == person_id, Person.user_id == patient_user_id)
    )
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found.")
    return person


def _get_object(db: Session, patient_user_id: int, object_id: int) -> ImportantObject:
    important_object = db.scalar(
        select(ImportantObject).where(
            ImportantObject.id == object_id,
            ImportantObject.user_id == patient_user_id,
        )
    )
    if important_object is None:
        raise HTTPException(status_code=404, detail="Important object not found.")
    return important_object


def _get_schedule_item(db: Session, patient_user_id: int, item_id: int) -> ScheduleItem:
    item = db.scalar(
        select(ScheduleItem).where(
            ScheduleItem.id == item_id,
            ScheduleItem.user_id == patient_user_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Schedule item not found.")
    return item


def _get_note(db: Session, patient_user_id: int, note_id: int) -> CaregiverNote:
    note = db.scalar(
        select(CaregiverNote).where(
            CaregiverNote.id == note_id,
            CaregiverNote.user_id == patient_user_id,
        )
    )
    if note is None:
        raise HTTPException(status_code=404, detail="Caregiver note not found.")
    return note


def _face_enrollment(db: Session, person_id: int) -> PersonFaceEnrollment | None:
    return db.scalar(
        select(PersonFaceEnrollment).where(PersonFaceEnrollment.person_id == person_id)
    )


def _person_response(db: Session, person: Person) -> PersonResponse:
    return PersonResponse(
        id=person.id,
        name=person.name,
        relationship=person.relationship,
        face_enrolled=_face_enrollment(db, person.id) is not None,
    )


def _schedule_response(item: ScheduleItem) -> ScheduleResponse:
    return ScheduleResponse(id=item.id, title=item.title, scheduled_at=item.scheduled_at)


def _local_datetime(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone().replace(tzinfo=None)
    return value


@router.get("/patients", response_model=list[PatientSummary])
def list_patients(
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> list[PatientSummary]:
    access_rows = list(
        db.scalars(
            select(CaregiverPatientAccess)
            .where(CaregiverPatientAccess.caregiver_id == current_caregiver.id)
            .order_by(CaregiverPatientAccess.patient_user_id)
        )
    )
    patient_ids = [access.patient_user_id for access in access_rows]
    if not patient_ids:
        return []
    access_by_patient = {access.patient_user_id: access for access in access_rows}
    users = list(db.scalars(select(User).where(User.id.in_(patient_ids)).order_by(User.id)))
    profiles = {
        profile.user_id: profile
        for profile in db.scalars(
            select(PatientProfile).where(PatientProfile.user_id.in_(patient_ids))
        )
    }
    return [
        PatientSummary(
            user_id=user.id,
            name=user.name,
            preferred_name=profiles[user.id].preferred_name if user.id in profiles else None,
            role=access_by_patient[user.id].role,
            can_manage_profile=access_by_patient[user.id].role == "primary",
            can_manage_people=access_by_patient[user.id].can_manage_people,
            can_manage_schedule=access_by_patient[user.id].can_manage_schedule,
            can_manage_objects=access_by_patient[user.id].can_manage_objects,
            can_manage_notes=access_by_patient[user.id].can_manage_notes,
        )
        for user in users
    ]


@router.get("/patients/{patient_user_id}/profile", response_model=PatientProfileResponse)
def get_patient_profile(
    patient_user_id: int,
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> PatientProfileResponse:
    require_caregiver_access(db, current_caregiver, patient_user_id, "view")
    return _profile_response(_get_profile(db, patient_user_id))


@router.patch("/patients/{patient_user_id}/profile", response_model=PatientProfileResponse)
def update_patient_profile(
    patient_user_id: int,
    payload: PatientProfilePatch,
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> PatientProfileResponse:
    require_caregiver_access(db, current_caregiver, patient_user_id, "manage_profile")
    profile = _get_profile(db, patient_user_id)
    fields = payload.model_dump(exclude_unset=True)
    if "preferred_name" in fields:
        profile.preferred_name = _required_text(fields["preferred_name"] or "", "Preferred name", 120)
    if "short_bio" in fields:
        profile.short_bio = _optional_text(fields["short_bio"], "Short bio", 1000)
    if "home_context" in fields:
        profile.home_context = _optional_text(fields["home_context"], "Home context", 1000)
    if "response_style" in fields:
        profile.response_style = _optional_text(fields["response_style"], "Response style", 120)
    db.commit()
    return _profile_response(profile)


@router.get("/patients/{patient_user_id}/people", response_model=list[PersonResponse])
def list_people(
    patient_user_id: int,
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> list[PersonResponse]:
    require_caregiver_access(db, current_caregiver, patient_user_id, "view")
    return [
        _person_response(db, person)
        for person in db.scalars(
            select(Person)
            .where(Person.user_id == patient_user_id)
            .order_by(Person.name, Person.id)
        )
    ]


@router.post("/patients/{patient_user_id}/people", response_model=PersonResponse, status_code=201)
def create_person(
    patient_user_id: int,
    payload: PersonCreate,
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> PersonResponse:
    require_caregiver_access(db, current_caregiver, patient_user_id, "manage_people")
    person = Person(
        user_id=patient_user_id,
        name=_required_text(payload.name, "Name", 120),
        relationship=_required_text(payload.relationship, "Relationship", 120),
    )
    db.add(person)
    db.commit()
    return _person_response(db, person)


@router.patch("/patients/{patient_user_id}/people/{person_id}", response_model=PersonResponse)
def update_person(
    patient_user_id: int,
    person_id: int,
    payload: PersonPatch,
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> PersonResponse:
    require_caregiver_access(db, current_caregiver, patient_user_id, "manage_people")
    person = _get_person(db, patient_user_id, person_id)
    fields = payload.model_dump(exclude_unset=True)
    if fields.get("name") is not None:
        person.name = _required_text(fields["name"], "Name", 120)
    if fields.get("relationship") is not None:
        person.relationship = _required_text(fields["relationship"], "Relationship", 120)
    db.commit()
    return _person_response(db, person)


@router.delete("/patients/{patient_user_id}/people/{person_id}", status_code=204)
def delete_person(
    patient_user_id: int,
    person_id: int,
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> Response:
    require_caregiver_access(db, current_caregiver, patient_user_id, "manage_people")
    person = _get_person(db, patient_user_id, person_id)
    enrollment = _face_enrollment(db, person.id)
    if enrollment is not None:
        db.delete(enrollment)
    db.execute(delete(RecognitionEvent).where(RecognitionEvent.person_id == person.id))
    db.delete(person)
    db.commit()
    return Response(status_code=204)


@router.get(
    "/patients/{patient_user_id}/people/{person_id}/face/status",
    response_model=FaceEnrollmentStatus,
)
def get_face_enrollment_status(
    patient_user_id: int,
    person_id: int,
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> FaceEnrollmentStatus:
    require_caregiver_access(db, current_caregiver, patient_user_id, "view")
    person = _get_person(db, patient_user_id, person_id)
    enrollment = _face_enrollment(db, person.id)
    return FaceEnrollmentStatus(
        person_id=person.id,
        enrolled=enrollment is not None,
        created_at=enrollment.created_at if enrollment else None,
    )


@router.post(
    "/patients/{patient_user_id}/people/{person_id}/face",
    response_model=FaceEnrollmentStatus,
)
async def enroll_face(
    patient_user_id: int,
    person_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> FaceEnrollmentStatus:
    require_caregiver_access(db, current_caregiver, patient_user_id, "manage_people")
    person = _get_person(db, patient_user_id, person_id)
    _, image_bytes = await read_uploaded_image(image)

    try:
        recognizer = face_provider.get_face_recognizer()
        embedding = recognizer.extract_embedding(image_bytes)
    except FaceRecognizerNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail="Face recognition is not configured.") from exc
    except NoFaceFoundError as exc:
        raise HTTPException(status_code=422, detail="No usable face was found.") from exc
    except MultipleFacesFoundError as exc:
        raise HTTPException(
            status_code=422,
            detail="Multiple faces were found. Please upload a photo containing one person.",
        ) from exc

    enrollment = _face_enrollment(db, person.id)
    if enrollment is None:
        enrollment = PersonFaceEnrollment(
            person_id=person.id,
            patient_user_id=patient_user_id,
            embedding=serialize_embedding(embedding),
        )
        db.add(enrollment)
    else:
        enrollment.embedding = serialize_embedding(embedding)
        enrollment.created_at = datetime.now()
    db.commit()
    return FaceEnrollmentStatus(
        person_id=person.id,
        enrolled=True,
        created_at=enrollment.created_at,
    )


@router.delete(
    "/patients/{patient_user_id}/people/{person_id}/face",
    status_code=204,
)
def delete_face_enrollment(
    patient_user_id: int,
    person_id: int,
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> Response:
    require_caregiver_access(db, current_caregiver, patient_user_id, "manage_people")
    person = _get_person(db, patient_user_id, person_id)
    enrollment = _face_enrollment(db, person.id)
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Face enrollment not found.")
    db.delete(enrollment)
    db.commit()
    return Response(status_code=204)


@router.get("/patients/{patient_user_id}/objects", response_model=list[ImportantObjectResponse])
def list_important_objects(
    patient_user_id: int,
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> list[ImportantObjectResponse]:
    require_caregiver_access(db, current_caregiver, patient_user_id, "view")
    return [
        ImportantObjectResponse(id=item.id, name=item.name, notes=item.notes)
        for item in db.scalars(
            select(ImportantObject)
            .where(ImportantObject.user_id == patient_user_id)
            .order_by(ImportantObject.name, ImportantObject.id)
        )
    ]


@router.post("/patients/{patient_user_id}/objects", response_model=ImportantObjectResponse, status_code=201)
def create_important_object(
    patient_user_id: int,
    payload: ImportantObjectCreate,
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> ImportantObjectResponse:
    require_caregiver_access(db, current_caregiver, patient_user_id, "manage_objects")
    item = ImportantObject(
        user_id=patient_user_id,
        name=_required_text(payload.name, "Object name", 120),
        notes=_optional_text(payload.notes, "Object notes", 1000),
    )
    db.add(item)
    db.commit()
    return ImportantObjectResponse(id=item.id, name=item.name, notes=item.notes)


@router.patch("/patients/{patient_user_id}/objects/{object_id}", response_model=ImportantObjectResponse)
def update_important_object(
    patient_user_id: int,
    object_id: int,
    payload: ImportantObjectPatch,
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> ImportantObjectResponse:
    require_caregiver_access(db, current_caregiver, patient_user_id, "manage_objects")
    item = _get_object(db, patient_user_id, object_id)
    fields = payload.model_dump(exclude_unset=True)
    if fields.get("name") is not None:
        item.name = _required_text(fields["name"], "Object name", 120)
    if "notes" in fields:
        item.notes = _optional_text(fields["notes"], "Object notes", 1000)
    db.commit()
    return ImportantObjectResponse(id=item.id, name=item.name, notes=item.notes)


@router.delete("/patients/{patient_user_id}/objects/{object_id}", status_code=204)
def delete_important_object(
    patient_user_id: int,
    object_id: int,
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> Response:
    require_caregiver_access(db, current_caregiver, patient_user_id, "manage_objects")
    db.delete(_get_object(db, patient_user_id, object_id))
    db.commit()
    return Response(status_code=204)


@router.get("/patients/{patient_user_id}/schedule", response_model=list[ScheduleResponse])
def list_schedule(
    patient_user_id: int,
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> list[ScheduleResponse]:
    require_caregiver_access(db, current_caregiver, patient_user_id, "view")
    return [
        _schedule_response(item)
        for item in db.scalars(
            select(ScheduleItem)
            .where(ScheduleItem.user_id == patient_user_id)
            .order_by(ScheduleItem.scheduled_at, ScheduleItem.id)
        )
    ]


@router.post("/patients/{patient_user_id}/schedule", response_model=ScheduleResponse, status_code=201)
def create_schedule_item(
    patient_user_id: int,
    payload: ScheduleCreate,
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> ScheduleResponse:
    require_caregiver_access(db, current_caregiver, patient_user_id, "manage_schedule")
    item = ScheduleItem(
        user_id=patient_user_id,
        title=_required_text(payload.title, "Title", 200),
        scheduled_at=_local_datetime(payload.scheduled_at),
    )
    db.add(item)
    db.commit()
    return _schedule_response(item)


@router.patch("/patients/{patient_user_id}/schedule/{item_id}", response_model=ScheduleResponse)
def update_schedule_item(
    patient_user_id: int,
    item_id: int,
    payload: SchedulePatch,
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> ScheduleResponse:
    require_caregiver_access(db, current_caregiver, patient_user_id, "manage_schedule")
    item = _get_schedule_item(db, patient_user_id, item_id)
    fields = payload.model_dump(exclude_unset=True)
    if fields.get("title") is not None:
        item.title = _required_text(fields["title"], "Title", 200)
    if fields.get("scheduled_at") is not None:
        item.scheduled_at = _local_datetime(fields["scheduled_at"])
    db.commit()
    return _schedule_response(item)


@router.delete("/patients/{patient_user_id}/schedule/{item_id}", status_code=204)
def delete_schedule_item(
    patient_user_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> Response:
    require_caregiver_access(db, current_caregiver, patient_user_id, "manage_schedule")
    db.delete(_get_schedule_item(db, patient_user_id, item_id))
    db.commit()
    return Response(status_code=204)


@router.get("/patients/{patient_user_id}/notes", response_model=list[CaregiverNoteResponse])
def list_notes(
    patient_user_id: int,
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> list[CaregiverNoteResponse]:
    require_caregiver_access(db, current_caregiver, patient_user_id, "view")
    return [
        CaregiverNoteResponse(
            id=note.id,
            caregiver_id=note.caregiver_id,
            note=note.note,
            created_at=note.created_at,
        )
        for note in db.scalars(
            select(CaregiverNote)
            .where(CaregiverNote.user_id == patient_user_id)
            .order_by(CaregiverNote.created_at.desc(), CaregiverNote.id.desc())
        )
    ]


@router.post("/patients/{patient_user_id}/notes", response_model=CaregiverNoteResponse, status_code=201)
def create_note(
    patient_user_id: int,
    payload: CaregiverNoteCreate,
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> CaregiverNoteResponse:
    require_caregiver_access(db, current_caregiver, patient_user_id, "manage_notes")
    note = CaregiverNote(
        user_id=patient_user_id,
        caregiver_id=current_caregiver.id,
        note=_required_text(payload.note, "Note", 2000),
    )
    db.add(note)
    db.commit()
    return CaregiverNoteResponse(
        id=note.id,
        caregiver_id=note.caregiver_id,
        note=note.note,
        created_at=note.created_at,
    )


@router.delete("/patients/{patient_user_id}/notes/{note_id}", status_code=204)
def delete_note(
    patient_user_id: int,
    note_id: int,
    db: Session = Depends(get_db),
    current_caregiver: Caregiver = Depends(get_current_caregiver),
) -> Response:
    require_caregiver_access(db, current_caregiver, patient_user_id, "manage_notes")
    db.delete(_get_note(db, patient_user_id, note_id))
    db.commit()
    return Response(status_code=204)
