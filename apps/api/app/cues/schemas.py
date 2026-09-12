"""Public schemas for proactive cues."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


CueType = Literal["schedule_upcoming", "recognized_person", "important_object"]


class ProactiveCue(BaseModel):
    id: str = Field(min_length=1, max_length=255)
    type: CueType
    title: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=500)
    priority: int = Field(ge=0)
    source_ids: list[str]
    expires_at: datetime | None = None


class CueListResponse(BaseModel):
    cues: list[ProactiveCue]


class CueDismissResponse(BaseModel):
    status: Literal["dismissed"]
    cue_id: str


class CuePresentationRequest(BaseModel):
    cue_id: str = Field(min_length=1, max_length=255)
    presentation_id: UUID


class CuePresentationResponse(BaseModel):
    status: Literal["presented", "already_presented"]
    cue_id: str
    presented_at: datetime
