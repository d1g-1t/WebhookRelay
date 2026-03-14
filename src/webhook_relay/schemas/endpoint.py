import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class EndpointCreate(BaseModel):
    name: str = Field(max_length=255)
    url: HttpUrl
    max_retries: int = Field(default=5, ge=1, le=20)
    retry_backoff_base: float = Field(default=2.0, ge=1.0, le=10.0)
    retry_max_delay_seconds: int = Field(default=3600, ge=60, le=86400)
    timeout_seconds: int = Field(default=30, ge=5, le=120)
    event_types_filter: list[str] = Field(default_factory=list)
    custom_headers: dict[str, str] = Field(default_factory=dict)


class EndpointUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    url: HttpUrl | None = None
    max_retries: int | None = Field(default=None, ge=1, le=20)
    retry_backoff_base: float | None = Field(default=None, ge=1.0, le=10.0)
    retry_max_delay_seconds: int | None = Field(default=None, ge=60, le=86400)
    timeout_seconds: int | None = Field(default=None, ge=5, le=120)
    event_types_filter: list[str] | None = None
    custom_headers: dict[str, str] | None = None
    is_active: bool | None = None


class EndpointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    url: str
    max_retries: int
    retry_backoff_base: float
    retry_max_delay_seconds: int
    timeout_seconds: int
    event_types_filter: list[str]
    custom_headers: dict[str, str]
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None


class EndpointCreatedResponse(EndpointResponse):
    signing_secret: str


class EndpointStatsResponse(BaseModel):
    endpoint_id: uuid.UUID
    total_events: int
    delivered: int
    failed: int
    dead_lettered: int
    pending: int
    success_rate: float
    avg_latency_ms: float | None
    circuit_state: str
