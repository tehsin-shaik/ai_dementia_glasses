"""Pydantic request and response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Intent = Literal[
    "recent_activity",
    "object_location",
    "person_lookup",
    "schedule",
    "unknown",
]

Language = Literal["en", "ar"]


class HealthResponse(BaseModel):
    status: Literal["ok"]


class SeedResponse(BaseModel):
    status: Literal["ok"]
    user_ids: list[int]
    user_count: int
    caregiver_ids: list[int]
    caregiver_count: int
    access_count: int
    profile_count: int
    memory_count: int
    observation_count: int
    person_count: int
    schedule_count: int
    important_object_count: int
    note_count: int


class PatientSummary(BaseModel):
    user_id: int
    name: str
    preferred_name: str | None
    role: str
    can_manage_profile: bool
    can_manage_people: bool
    can_manage_schedule: bool
    can_manage_objects: bool
    can_manage_notes: bool


class PatientProfileResponse(BaseModel):
    user_id: int
    preferred_name: str
    short_bio: str | None
    home_context: str | None
    response_style: str | None


class PatientProfilePatch(BaseModel):
    preferred_name: str | None = Field(default=None, max_length=120)
    short_bio: str | None = Field(default=None, max_length=1000)
    home_context: str | None = Field(default=None, max_length=1000)
    response_style: str | None = Field(default=None, max_length=120)


class PersonResponse(BaseModel):
    id: int
    name: str
    relationship: str
    face_enrolled: bool = False


class PersonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    relationship: str = Field(min_length=1, max_length=120)


class PersonPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    relationship: str | None = Field(default=None, min_length=1, max_length=120)


class FaceEnrollmentStatus(BaseModel):
    person_id: int
    enrolled: bool
    created_at: datetime | None


class FaceRecognitionResponse(BaseModel):
    recognized: bool
    person_id: int | None
    name: str | None
    relationship: str | None
    confidence: float = Field(ge=0, le=1)


class ImportantObjectResponse(BaseModel):
    id: int
    name: str
    notes: str | None


class ImportantObjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)


class ImportantObjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)


class ScheduleResponse(BaseModel):
    id: int
    title: str
    scheduled_at: datetime


class ScheduleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    scheduled_at: datetime


class SchedulePatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    scheduled_at: datetime | None = None


class CaregiverNoteResponse(BaseModel):
    id: int
    caregiver_id: int
    note: str
    created_at: datetime


class CaregiverNoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    language: Language = "en"


class QueryEvidence(BaseModel):
    """Human-readable provenance for one stored record behind an answer."""

    source_id: str
    label: str
    detail: str
    recorded_at: datetime | None
    image_url: str | None = None
    corrected_at: datetime | None = None
    corrected_by: str | None = None


MomentSource = Literal["capture", "sample"]


class RewindMoment(BaseModel):
    """One saved moment shown in the recent strip or a recap."""

    memory_id: int
    recorded_at: datetime
    location: str
    activity: str | None
    description: str
    image_url: str | None
    source: MomentSource
    corrected_at: datetime | None = None
    corrected_by: str | None = None


class RewindResponse(BaseModel):
    summary: str
    moments: list[RewindMoment] = Field(default_factory=list)
    window_minutes: int
    within_window: bool
    has_earlier: bool
    language: Language = "en"


CorrectionField = Literal["description", "object_name", "object_location"]


class MemoryCorrectionCreate(BaseModel):
    field: CorrectionField
    value: str = Field(min_length=1, max_length=200)


class MemoryCorrectionResponse(BaseModel):
    id: int
    memory_id: int
    caregiver_id: int
    caregiver_name: str
    field: CorrectionField
    old_value: str
    new_value: str
    corrected_at: datetime


class SavedMomentResponse(BaseModel):
    """A saved moment as the caregiver reviews it, with its correction history."""

    memory_id: int
    recorded_at: datetime
    location: str
    description: str
    image_url: str | None
    object_name: str | None
    object_location: str | None
    corrections: list[MemoryCorrectionResponse] = Field(default_factory=list)


class QueryResponse(BaseModel):
    answer: str
    intent: Intent
    source_ids: list[str]
    evidence: list[QueryEvidence] = Field(default_factory=list)
    language: Language = "en"


class MemoryResponse(BaseModel):
    id: int
    timestamp: datetime
    location: str
    activity: str | None
    description: str
    image_url: str
    object_observation_id: int | None


class MemoryListItem(BaseModel):
    id: int
    timestamp: datetime
    location: str
    description: str
    image_url: str | None
