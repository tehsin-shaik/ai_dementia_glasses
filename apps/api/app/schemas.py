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


class PersonCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    relationship: str = Field(min_length=1, max_length=120)


class PersonPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    relationship: str | None = Field(default=None, min_length=1, max_length=120)


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


class QueryResponse(BaseModel):
    answer: str
    intent: Intent
    source_ids: list[str]


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
