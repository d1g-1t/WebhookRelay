import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from webhook_relay.models.delivery_attempt import DeliveryAttempt


class DeliveryAttemptRepository:
    async def create(
        self, session: AsyncSession, attempt: DeliveryAttempt
    ) -> DeliveryAttempt:
        session.add(attempt)
        await session.flush()
        return attempt

    async def get_by_event_id(
        self,
        session: AsyncSession,
        event_id: uuid.UUID,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[DeliveryAttempt], int]:
        query = (
            select(DeliveryAttempt)
            .where(DeliveryAttempt.event_id == event_id)
            .order_by(DeliveryAttempt.attempt_number.asc())
            .offset((page - 1) * size)
            .limit(size)
        )
        count_query = (
            select(func.count())
            .select_from(DeliveryAttempt)
            .where(DeliveryAttempt.event_id == event_id)
        )
        result = await session.execute(query)
        total = await session.scalar(count_query)
        return list(result.scalars().all()), total or 0

    async def avg_duration_by_endpoint(
        self, session: AsyncSession, endpoint_id: uuid.UUID
    ) -> float | None:
        from webhook_relay.models.event import WebhookEvent

        result = await session.scalar(
            select(func.avg(DeliveryAttempt.duration_ms))
            .join(WebhookEvent, DeliveryAttempt.event_id == WebhookEvent.id)
            .where(WebhookEvent.endpoint_id == endpoint_id, DeliveryAttempt.success.is_(True))
        )
        return float(result) if result else None
