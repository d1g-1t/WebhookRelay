import logging

import httpx
from arq import cron
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from webhook_relay.config import settings
from webhook_relay.redis_client import create_redis_client, get_arq_redis_settings
from webhook_relay.repositories.dead_letter_repo import DeadLetterRepository
from webhook_relay.repositories.delivery_attempt_repo import DeliveryAttemptRepository
from webhook_relay.repositories.endpoint_repo import EndpointRepository
from webhook_relay.repositories.event_repo import EventRepository
from webhook_relay.services.circuit_breaker import CircuitBreaker
from webhook_relay.services.delivery_service import DeliveryService
from webhook_relay.services.hmac_service import HMACService
from webhook_relay.services.retry_service import ExponentialBackoffStrategy
from webhook_relay.worker.tasks import deliver_webhook_task, poll_pending_retries

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def startup(ctx: dict) -> None:
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    redis_client = await create_redis_client()
    http_client = httpx.AsyncClient()

    event_repo = EventRepository()
    attempt_repo = DeliveryAttemptRepository()
    dlq_repo = DeadLetterRepository()
    endpoint_repo = EndpointRepository()

    circuit_breaker = CircuitBreaker(
        redis=redis_client,
        failure_threshold=settings.CB_FAILURE_THRESHOLD,
        failure_window=settings.CB_FAILURE_WINDOW_SECONDS,
        recovery_timeout=settings.CB_RECOVERY_TIMEOUT_SECONDS,
    )

    delivery_service = DeliveryService(
        session_factory=session_factory,
        http_client=http_client,
        hmac_service=HMACService(settings.HMAC_TIMESTAMP_TOLERANCE_SECONDS),
        circuit_breaker=circuit_breaker,
        retry_strategy=ExponentialBackoffStrategy(),
        event_repo=event_repo,
        attempt_repo=attempt_repo,
        dlq_repo=dlq_repo,
        endpoint_repo=endpoint_repo,
        settings=settings,
    )

    ctx["delivery_service"] = delivery_service
    ctx["event_repo"] = event_repo
    ctx["session_factory"] = session_factory
    ctx["redis_client"] = redis_client
    ctx["http_client"] = http_client
    ctx["engine"] = engine


async def shutdown(ctx: dict) -> None:
    await ctx["http_client"].aclose()
    await ctx["redis_client"].aclose()
    await ctx["engine"].dispose()


class WorkerSettings:
    functions = [deliver_webhook_task]
    cron_jobs = [cron(poll_pending_retries, second={0, 30})]
    redis_settings = get_arq_redis_settings()
    max_jobs = settings.ARQ_MAX_JOBS
    job_timeout = settings.ARQ_JOB_TIMEOUT_SECONDS
    on_startup = startup
    on_shutdown = shutdown
