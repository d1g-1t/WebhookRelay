import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class EventCreate(BaseModel):
    endpoint_id: uuid.UUID
    event_type: str = Field(max_length=255)
    payload: dict
    idempotency_key: str | None = Field(default=None, max_length=255)


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    endpoint_id: uuid.UUID
    event_type: str
    status: str
    attempt_count: int
    created_at: datetime
    delivered_at: datetime | None = None
    next_retry_at: datetime | None = None


class EventDetailResponse(EventResponse):
    payload: dict
    idempotency_key: str | None = None
    attempts: list["DeliveryAttemptResponse"] = []


class DeliveryAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    event_id: uuid.UUID
    attempt_number: int
    http_status_code: int | None = None
    success: bool
    error_message: str | None = None
    duration_ms: float | None = None
    attempted_at: datetime
    response_body: str | None = None
