import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from webhook_relay.api.dependencies import (
    get_attempt_repo,
    get_circuit_breaker,
    get_db,
    get_endpoint_repo,
    get_event_repo,
)
from webhook_relay.models.endpoint import WebhookEndpoint
from webhook_relay.repositories.delivery_attempt_repo import DeliveryAttemptRepository
from webhook_relay.repositories.endpoint_repo import EndpointRepository
from webhook_relay.repositories.event_repo import EventRepository
from webhook_relay.schemas.delivery import PaginatedResponse
from webhook_relay.schemas.endpoint import (
    EndpointCreate,
    EndpointCreatedResponse,
    EndpointResponse,
    EndpointStatsResponse,
    EndpointUpdate,
)
from webhook_relay.services.circuit_breaker import CircuitBreaker

router = APIRouter(prefix="/endpoints", tags=["endpoints"])


@router.post("/", response_model=EndpointCreatedResponse, status_code=201)
async def create_endpoint(
    data: EndpointCreate,
    session: AsyncSession = Depends(get_db),
    repo: EndpointRepository = Depends(get_endpoint_repo),
):
    endpoint = WebhookEndpoint(
        name=data.name,
        url=str(data.url),
        signing_secret=secrets.token_hex(32),
        max_retries=data.max_retries,
        retry_backoff_base=data.retry_backoff_base,
        retry_max_delay_seconds=data.retry_max_delay_seconds,
        timeout_seconds=data.timeout_seconds,
        event_types_filter=data.event_types_filter,
        custom_headers=data.custom_headers,
    )
    await repo.create(session, endpoint)
    return endpoint


@router.get("/", response_model=PaginatedResponse[EndpointResponse])
async def list_endpoints(
    page: int = 1,
    size: int = 20,
    is_active: bool | None = None,
    session: AsyncSession = Depends(get_db),
    repo: EndpointRepository = Depends(get_endpoint_repo),
):
    items, total = await repo.get_all(session, page=page, size=size, is_active=is_active)
    return PaginatedResponse(
        items=[EndpointResponse.model_validate(e) for e in items],
        total=total,
        page=page,
        size=size,
        pages=(total + size - 1) // size if total else 0,
    )


@router.get("/{endpoint_id}", response_model=EndpointResponse)
async def get_endpoint(
    endpoint_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    repo: EndpointRepository = Depends(get_endpoint_repo),
):
    endpoint = await repo.get_by_id(session, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return endpoint


@router.patch("/{endpoint_id}", response_model=EndpointResponse)
async def update_endpoint(
    endpoint_id: uuid.UUID,
    data: EndpointUpdate,
    session: AsyncSession = Depends(get_db),
    repo: EndpointRepository = Depends(get_endpoint_repo),
):
    update_data = data.model_dump(exclude_unset=True)
    if "url" in update_data and update_data["url"] is not None:
        update_data["url"] = str(update_data["url"])
    endpoint = await repo.update(session, endpoint_id, update_data)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return endpoint


@router.delete("/{endpoint_id}", status_code=204)
async def delete_endpoint(
    endpoint_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    repo: EndpointRepository = Depends(get_endpoint_repo),
):
    if not await repo.deactivate(session, endpoint_id):
        raise HTTPException(status_code=404, detail="Endpoint not found")


@router.get("/{endpoint_id}/stats", response_model=EndpointStatsResponse)
async def get_endpoint_stats(
    endpoint_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    repo: EndpointRepository = Depends(get_endpoint_repo),
    event_repo: EventRepository = Depends(get_event_repo),
    attempt_repo: DeliveryAttemptRepository = Depends(get_attempt_repo),
    cb: CircuitBreaker = Depends(get_circuit_breaker),
):
    endpoint = await repo.get_by_id(session, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Endpoint not found")

    status_counts = await event_repo.count_by_status(session, endpoint_id)
    avg_latency = await attempt_repo.avg_duration_by_endpoint(session, endpoint_id)
    circuit_state = await cb.get_state(str(endpoint_id))

    total = sum(status_counts.values())
    delivered = status_counts.get("delivered", 0)

    return EndpointStatsResponse(
        endpoint_id=endpoint_id,
        total_events=total,
        delivered=delivered,
        failed=status_counts.get("failed", 0),
        dead_lettered=status_counts.get("dead_lettered", 0),
        pending=status_counts.get("pending", 0),
        success_rate=round(delivered / total * 100, 2) if total else 0.0,
        avg_latency_ms=round(avg_latency, 2) if avg_latency else None,
        circuit_state=circuit_state.value,
    )


@router.post("/{endpoint_id}/rotate-secret", response_model=EndpointCreatedResponse)
async def rotate_secret(
    endpoint_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    repo: EndpointRepository = Depends(get_endpoint_repo),
):
    endpoint = await repo.rotate_secret(session, endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return endpoint
