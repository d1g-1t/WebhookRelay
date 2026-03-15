import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from webhook_relay.api.dependencies import get_db, get_dlq_repo, get_replay_service
from webhook_relay.exceptions import DeadLetterNotFoundError, RecentlyReplayedError
from webhook_relay.repositories.dead_letter_repo import DeadLetterRepository
from webhook_relay.schemas.delivery import (
    BulkReplayRequest,
    BulkReplayResponse,
    DeadLetterResponse,
    PaginatedResponse,
    ReplayResponse,
)
from webhook_relay.services.replay_service import ReplayService

router = APIRouter(prefix="/dlq", tags=["dead-letter-queue"])


@router.get("/", response_model=PaginatedResponse[DeadLetterResponse])
async def list_dlq(
    endpoint_id: uuid.UUID | None = None,
    event_type: str | None = None,
    page: int = 1,
    size: int = 20,
    session: AsyncSession = Depends(get_db),
    repo: DeadLetterRepository = Depends(get_dlq_repo),
):
    items, total = await repo.get_all(
        session, endpoint_id=endpoint_id, event_type=event_type, page=page, size=size
    )
    return PaginatedResponse(
        items=[DeadLetterResponse.model_validate(e) for e in items],
        total=total,
        page=page,
        size=size,
        pages=(total + size - 1) // size if total else 0,
    )


@router.get("/{dlq_id}", response_model=DeadLetterResponse)
async def get_dlq_entry(
    dlq_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    repo: DeadLetterRepository = Depends(get_dlq_repo),
):
    entry = await repo.get_by_id(session, dlq_id)
    if not entry:
        raise HTTPException(status_code=404, detail="DLQ entry not found")
    return entry


@router.post("/{dlq_id}/replay", response_model=ReplayResponse)
async def replay_dlq_event(
    dlq_id: uuid.UUID,
    force: bool = False,
    replay_service: ReplayService = Depends(get_replay_service),
):
    try:
        result = await replay_service.replay_single(dlq_id, force=force)
        return ReplayResponse(**result)
    except DeadLetterNotFoundError:
        raise HTTPException(status_code=404, detail="DLQ entry not found")
    except RecentlyReplayedError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/replay/bulk", response_model=BulkReplayResponse)
async def bulk_replay(
    data: BulkReplayRequest,
    replay_service: ReplayService = Depends(get_replay_service),
):
    result = await replay_service.replay_bulk(
        endpoint_id=data.endpoint_id,
        event_type=data.event_type,
        force=data.force,
    )
    return BulkReplayResponse(
        replayed=result["replayed"],
        errors=result["errors"],
        results=[ReplayResponse(**r) for r in result["results"]],
    )


@router.delete("/{dlq_id}", status_code=204)
async def discard_dlq_entry(
    dlq_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    repo: DeadLetterRepository = Depends(get_dlq_repo),
):
    if not await repo.delete_entry(session, dlq_id):
        raise HTTPException(status_code=404, detail="DLQ entry not found")
