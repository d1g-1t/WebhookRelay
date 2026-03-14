import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from webhook_relay.models.base import Base


class DeadLetterEvent(Base):
    __tablename__ = "dead_letter_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("webhook_events.id"), nullable=False
    )
    endpoint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    original_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    event_type: Mapped[str] = mapped_column(String(255))
    total_attempts: Mapped[int] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_http_status: Mapped[int | None] = mapped_column(Integer)
    replayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replay_count: Mapped[int] = mapped_column(Integer, default=0)
    dead_lettered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
