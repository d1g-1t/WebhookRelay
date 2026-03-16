import uuid

from arq import ArqRedis
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from webhook_relay.api.dependencies import (
    get_arq_pool,
    get_attempt_repo,
    get_db,
    get_endpoint_repo,
    get_event_repo,
)
from webhook_relay.models.event import WebhookEvent
from webhook_relay.repositories.delivery_attempt_repo import DeliveryAttemptRepository
from webhook_relay.repositories.endpoint_repo import EndpointRepository
from webhook_relay.repositories.event_repo import EventRepository
from webhook_relay.schemas.delivery import PaginatedResponse
from webhook_relay.schemas.event import (
    DeliveryAttemptResponse,
    EventCreate,
    EventDetailResponse,
    EventResponse,
)

router = APIRouter(prefix="/events", tags=["events"])


@router.post("/", response_model=EventResponse, status_code=201)
async def create_event(
    data: EventCreate,
    session: AsyncSession = Depends(get_db),
    event_repo: EventRepository = Depends(get_event_repo),
    endpoint_repo: EndpointRepository = Depends(get_endpoint_repo),
    arq_pool: ArqRedis = Depends(get_arq_pool),
):
    if data.idempotency_key:
        existing = await event_repo.get_by_idempotency_key(session, data.idempotency_key)
        if existing:
            return existing

    endpoint = await endpoint_repo.get_by_id(session, data.endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    if not endpoint.is_active:
        raise HTTPException(status_code=422, detail="Endpoint is inactive")

    if endpoint.event_types_filter and data.event_type not in endpoint.event_types_filter:
        raise HTTPException(
            status_code=422,
            detail=f"Event type '{data.event_type}' not accepted by this endpoint",
        )

    event = await event_repo.create(
        session,
        WebhookEvent(
            endpoint_id=data.endpoint_id,
            event_type=data.event_type,
            payload=data.payload,
            idempotency_key=data.idempotency_key,
            status="pending",
        ),
    )
    await session.flush()

    await arq_pool.enqueue_job(
        "deliver_webhook_task", str(event.id), _job_id=f"deliver:{event.id}"
    )

    return event


@router.get("/{event_id}", response_model=EventDetailResponse)
async def get_event(
    event_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    event_repo: EventRepository = Depends(get_event_repo),
):
    event = await event_repo.get_with_attempts(session, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.get("/{event_id}/attempts", response_model=PaginatedResponse[DeliveryAttemptResponse])
async def get_event_attempts(
    event_id: uuid.UUID,
    page: int = 1,
    size: int = 20,
    session: AsyncSession = Depends(get_db),
    attempt_repo: DeliveryAttemptRepository = Depends(get_attempt_repo),
):
    items, total = await attempt_repo.get_by_event_id(session, event_id, page=page, size=size)
    return PaginatedResponse(
        items=[DeliveryAttemptResponse.model_validate(a) for a in items],
        total=total,
        page=page,
        size=size,
        pages=(total + size - 1) // size if total else 0,
    )
