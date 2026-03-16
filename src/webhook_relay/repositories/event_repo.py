import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from webhook_relay.models.event import WebhookEvent


class EventRepository:
    async def create(self, session: AsyncSession, event: WebhookEvent) -> WebhookEvent:
        session.add(event)
        await session.flush()
        return event

    async def get_by_id(self, session: AsyncSession, event_id: uuid.UUID) -> WebhookEvent | None:
        return await session.get(WebhookEvent, event_id)

    async def get_with_endpoint(
        self, session: AsyncSession, event_id: uuid.UUID
    ) -> WebhookEvent | None:
        result = await session.execute(
            select(WebhookEvent)
            .options(selectinload(WebhookEvent.endpoint))
            .where(WebhookEvent.id == event_id)
        )
        return result.scalar_one_or_none()

    async def get_with_attempts(
        self, session: AsyncSession, event_id: uuid.UUID
    ) -> WebhookEvent | None:
        result = await session.execute(
            select(WebhookEvent)
            .options(selectinload(WebhookEvent.attempts))
            .where(WebhookEvent.id == event_id)
        )
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(
        self, session: AsyncSession, key: str
    ) -> WebhookEvent | None:
        result = await session.execute(
            select(WebhookEvent).where(WebhookEvent.idempotency_key == key)
        )
        return result.scalar_one_or_none()

    async def mark_delivering(self, session: AsyncSession, event: WebhookEvent) -> None:
        event.status = "delivering"
        event.attempt_count += 1
        await session.flush()

    async def mark_delivered(self, session: AsyncSession, event: WebhookEvent) -> None:
        event.status = "delivered"
        event.delivered_at = datetime.now(timezone.utc)
        await session.flush()

    async def mark_dead_lettered(self, session: AsyncSession, event: WebhookEvent) -> None:
        event.status = "dead_lettered"
        await session.flush()

    async def schedule_retry(
        self, session: AsyncSession, event: WebhookEvent, next_retry_at: datetime
    ) -> None:
        event.status = "failed"
        event.next_retry_at = next_retry_at
        await session.flush()

    async def get_due_for_retry(
        self, session: AsyncSession, limit: int = 500
    ) -> list[WebhookEvent]:
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(WebhookEvent)
            .where(
                WebhookEvent.status == "failed",
                WebhookEvent.next_retry_at <= now,
            )
            .order_by(WebhookEvent.next_retry_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_stale_pending(
        self, session: AsyncSession, older_than_seconds: int = 120, limit: int = 100
    ) -> list[WebhookEvent]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)
        result = await session.execute(
            select(WebhookEvent)
            .where(
                WebhookEvent.status == "pending",
                WebhookEvent.next_retry_at.is_(None),
                WebhookEvent.created_at < cutoff,
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_status(
        self, session: AsyncSession, endpoint_id: uuid.UUID | None = None
    ) -> dict[str, int]:
        query = select(WebhookEvent.status, func.count()).group_by(WebhookEvent.status)
        if endpoint_id:
            query = query.where(WebhookEvent.endpoint_id == endpoint_id)
        result = await session.execute(query)
        return dict(result.all())
