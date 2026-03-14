import uuid
from datetime import datetime, timedelta, timezone

from arq import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from webhook_relay.exceptions import DeadLetterNotFoundError, RecentlyReplayedError
from webhook_relay.models.event import WebhookEvent
from webhook_relay.repositories.dead_letter_repo import DeadLetterRepository
from webhook_relay.repositories.event_repo import EventRepository
from webhook_relay.services.circuit_breaker import CircuitBreaker


class ReplayService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        event_repo: EventRepository,
        dlq_repo: DeadLetterRepository,
        circuit_breaker: CircuitBreaker,
        arq_pool: ArqRedis,
    ):
        self._session_factory = session_factory
        self._event_repo = event_repo
        self._dlq_repo = dlq_repo
        self._circuit_breaker = circuit_breaker
        self._arq_pool = arq_pool

    async def replay_single(
        self,
        dlq_id: uuid.UUID,
        force: bool = False,
        session: AsyncSession | None = None,
    ) -> dict:
        own_session = session is None
        if own_session:
            session = self._session_factory()

        try:
            dlq_entry = await self._dlq_repo.get_by_id(session, dlq_id)
            if not dlq_entry:
                raise DeadLetterNotFoundError(dlq_id)

            if dlq_entry.replay_count > 0 and not force:
                if dlq_entry.replayed_at and dlq_entry.replayed_at > datetime.now(
                    timezone.utc
                ) - timedelta(hours=1):
                    raise RecentlyReplayedError(
                        "Event was replayed less than 1 hour ago. Use force=True to override."
                    )

            new_event = await self._event_repo.create(
                session,
                WebhookEvent(
                    endpoint_id=dlq_entry.endpoint_id,
                    event_type=dlq_entry.event_type,
                    payload=dlq_entry.original_payload,
                    status="pending",
                ),
            )

            await self._dlq_repo.mark_replayed(session, dlq_entry)
            await self._circuit_breaker.reset(str(dlq_entry.endpoint_id))

            if own_session:
                await session.commit()

            await self._arq_pool.enqueue_job(
                "deliver_webhook_task",
                str(new_event.id),
                _job_id=f"deliver:{new_event.id}",
            )

            return {
                "original_dlq_id": dlq_id,
                "new_event_id": new_event.id,
                "enqueued": True,
            }
        finally:
            if own_session:
                await session.close()

    async def replay_bulk(
        self,
        endpoint_id: uuid.UUID | None = None,
        event_type: str | None = None,
        force: bool = False,
    ) -> dict:
        async with self._session_factory() as session:
            entries = await self._dlq_repo.get_unreplayed_by_filter(
                session, endpoint_id=endpoint_id, event_type=event_type
            )

            results = []
            errors = 0

            for entry in entries:
                try:
                    result = await self.replay_single(entry.id, force=force, session=session)
                    results.append(result)
                except (RecentlyReplayedError, DeadLetterNotFoundError):
                    errors += 1

            await session.commit()

            return {
                "replayed": len(results),
                "errors": errors,
                "results": results,
            }
