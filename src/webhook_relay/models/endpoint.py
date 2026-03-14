import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from webhook_relay.models.base import Base

if TYPE_CHECKING:
    from webhook_relay.models.event import WebhookEvent


class WebhookEndpoint(Base):
    __tablename__ = "webhook_endpoints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    signing_secret: Mapped[str] = mapped_column(String(255), nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=5)
    retry_backoff_base: Mapped[float] = mapped_column(Float, default=2.0)
    retry_max_delay_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    event_types_filter: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    custom_headers: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    events: Mapped[list["WebhookEvent"]] = relationship(back_populates="endpoint")
