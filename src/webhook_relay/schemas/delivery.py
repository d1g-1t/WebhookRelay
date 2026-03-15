import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
    pages: int


class DeadLetterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    endpoint_id: uuid.UUID
    original_payload: dict
    event_type: str
    total_attempts: int
    last_error: str | None = None
    last_http_status: int | None = None
    replayed_at: datetime | None = None
    replay_count: int
    dead_lettered_at: datetime


class ReplayResponse(BaseModel):
    original_dlq_id: uuid.UUID
    new_event_id: uuid.UUID
    enqueued: bool


class BulkReplayRequest(BaseModel):
    endpoint_id: uuid.UUID | None = None
    event_type: str | None = None
    force: bool = False


class BulkReplayResponse(BaseModel):
    replayed: int
    errors: int
    results: list[ReplayResponse]


class HealthResponse(BaseModel):
    status: str
    database: str
    redis: str


class StatsResponse(BaseModel):
    total_events: int
    pending: int
    delivered: int
    failed: int
    dead_lettered: int
    dlq_count: int
    success_rate: float
    open_circuits: list[str] = Field(default_factory=list)


class HMACVerifyRequest(BaseModel):
    secret: str
    body: str


class HMACVerifyResponse(BaseModel):
    valid: bool
    timestamp_age_seconds: int | None = None
    error: str | None = None
