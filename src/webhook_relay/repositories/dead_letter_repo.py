import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from webhook_relay.models.dead_letter import DeadLetterEvent


class DeadLetterRepository:
    async def create(
        self, session: AsyncSession, entry: DeadLetterEvent
    ) -> DeadLetterEvent:
        session.add(entry)
        await session.flush()
        return entry

    async def get_by_id(
        self, session: AsyncSession, dlq_id: uuid.UUID
    ) -> DeadLetterEvent | None:
        return await session.get(DeadLetterEvent, dlq_id)

    async def get_all(
        self,
        session: AsyncSession,
        endpoint_id: uuid.UUID | None = None,
        event_type: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[DeadLetterEvent], int]:
        query = select(DeadLetterEvent)
        count_query = select(func.count()).select_from(DeadLetterEvent)

        if endpoint_id:
            query = query.where(DeadLetterEvent.endpoint_id == endpoint_id)
            count_query = count_query.where(DeadLetterEvent.endpoint_id == endpoint_id)
        if event_type:
            query = query.where(DeadLetterEvent.event_type == event_type)
            count_query = count_query.where(DeadLetterEvent.event_type == event_type)

        query = query.order_by(DeadLetterEvent.dead_lettered_at.desc())
        query = query.offset((page - 1) * size).limit(size)

        result = await session.execute(query)
        total = await session.scalar(count_query)
        return list(result.scalars().all()), total or 0

    async def mark_replayed(self, session: AsyncSession, entry: DeadLetterEvent) -> None:
        entry.replayed_at = datetime.now(timezone.utc)
        entry.replay_count += 1
        await session.flush()

    async def delete_entry(self, session: AsyncSession, dlq_id: uuid.UUID) -> bool:
        result = await session.execute(
            delete(DeadLetterEvent).where(DeadLetterEvent.id == dlq_id)
        )
        await session.flush()
        return result.rowcount > 0

    async def count(self, session: AsyncSession) -> int:
        result = await session.scalar(select(func.count()).select_from(DeadLetterEvent))
        return result or 0

    async def get_unreplayed_by_filter(
        self,
        session: AsyncSession,
        endpoint_id: uuid.UUID | None = None,
        event_type: str | None = None,
        limit: int = 1000,
    ) -> list[DeadLetterEvent]:
        query = select(DeadLetterEvent)
        if endpoint_id:
            query = query.where(DeadLetterEvent.endpoint_id == endpoint_id)
        if event_type:
            query = query.where(DeadLetterEvent.event_type == event_type)
        query = query.order_by(DeadLetterEvent.dead_lettered_at.asc()).limit(limit)

        result = await session.execute(query)
        return list(result.scalars().all())
