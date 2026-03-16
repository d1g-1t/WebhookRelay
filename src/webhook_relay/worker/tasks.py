import logging
import uuid

logger = logging.getLogger(__name__)


async def deliver_webhook_task(ctx: dict, event_id: str) -> str:
    delivery_service = ctx["delivery_service"]
    outcome = await delivery_service.deliver(uuid.UUID(event_id))
    return outcome.status


async def poll_pending_retries(ctx: dict) -> None:
    session_factory = ctx["session_factory"]
    event_repo = ctx["event_repo"]

    async with session_factory() as session:
        due_events = await event_repo.get_due_for_retry(session, limit=500)
        stale_events = await event_repo.get_stale_pending(session, older_than_seconds=120)

        all_events = due_events + stale_events
        enqueued = 0

        for event in all_events:
            try:
                await ctx["redis"].enqueue_job(
                    "deliver_webhook_task",
                    str(event.id),
                    _job_id=f"deliver:{event.id}",
                )
                enqueued += 1
            except Exception:
                logger.exception("Failed to enqueue event %s", event.id)

        if enqueued:
            logger.info("Enqueued %d events for delivery", enqueued)
