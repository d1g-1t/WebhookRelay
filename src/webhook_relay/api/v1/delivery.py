import time

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from webhook_relay.api.dependencies import (
    get_circuit_breaker,
    get_db,
    get_dlq_repo,
    get_event_repo,
    get_hmac_service,
    get_redis,
)
from webhook_relay.repositories.dead_letter_repo import DeadLetterRepository
from webhook_relay.repositories.event_repo import EventRepository
from webhook_relay.schemas.delivery import (
    HMACVerifyResponse,
    HealthResponse,
    StatsResponse,
)
from webhook_relay.services.circuit_breaker import CircuitBreaker
from webhook_relay.services.hmac_service import HMACService

router = APIRouter(tags=["operations"])


@router.get("/health", response_model=HealthResponse)
async def health_check(
    session: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    db_status = "ok"
    redis_status = "ok"

    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    try:
        await redis.ping()
    except Exception:
        redis_status = "error"

    status = "healthy" if db_status == "ok" and redis_status == "ok" else "degraded"
    return HealthResponse(status=status, database=db_status, redis=redis_status)


@router.get("/stats", response_model=StatsResponse)
async def global_stats(
    session: AsyncSession = Depends(get_db),
    event_repo: EventRepository = Depends(get_event_repo),
    dlq_repo: DeadLetterRepository = Depends(get_dlq_repo),
    cb: CircuitBreaker = Depends(get_circuit_breaker),
):
    status_counts = await event_repo.count_by_status(session)
    dlq_count = await dlq_repo.count(session)
    open_circuits = await cb.get_open_circuits()

    total = sum(status_counts.values())
    delivered = status_counts.get("delivered", 0)

    return StatsResponse(
        total_events=total,
        pending=status_counts.get("pending", 0),
        delivered=delivered,
        failed=status_counts.get("failed", 0),
        dead_lettered=status_counts.get("dead_lettered", 0),
        dlq_count=dlq_count,
        success_rate=round(delivered / total * 100, 2) if total else 0.0,
        open_circuits=open_circuits,
    )


@router.post("/inbound/verify", response_model=HMACVerifyResponse)
async def verify_inbound_hmac(
    request: Request,
    hmac_service: HMACService = Depends(get_hmac_service),
):
    body = await request.body()
    signature = request.headers.get("X-Webhook-Signature")
    secret = request.headers.get("X-Webhook-Secret")

    if not signature or not secret:
        return HMACVerifyResponse(
            valid=False,
            error="Missing X-Webhook-Signature or X-Webhook-Secret header",
        )

    valid = hmac_service.verify_signature(body, signature, secret)
    ts = hmac_service.parse_timestamp(signature)
    age = abs(int(time.time()) - ts) if ts else None

    return HMACVerifyResponse(
        valid=valid,
        timestamp_age_seconds=age,
        error=None if valid else "Signature verification failed",
    )
