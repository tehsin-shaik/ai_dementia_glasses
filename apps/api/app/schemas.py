"""Pydantic request and response schemas."""

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
    user_id: int
    memory_count: int
    observation_count: int
    person_count: int
    schedule_count: int


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class QueryResponse(BaseModel):
    answer: str
    intent: Intent
    source_ids: list[str]
