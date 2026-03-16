import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from webhook_relay.exceptions import DeadLetterNotFoundError, RecentlyReplayedError
from webhook_relay.models.dead_letter import DeadLetterEvent
from webhook_relay.services.replay_service import ReplayService


def _make_dlq_entry(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "event_id": uuid.uuid4(),
        "endpoint_id": uuid.uuid4(),
        "original_payload": {"key": "value"},
        "event_type": "test.event",
        "total_attempts": 5,
        "last_error": "HTTP 500",
        "last_http_status": 500,
        "replayed_at": None,
        "replay_count": 0,
        "dead_lettered_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    entry = MagicMock(spec=DeadLetterEvent)
    for k, v in defaults.items():
        setattr(entry, k, v)
    return entry


def _make_replay_service(dlq_entry=None):
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.commit = AsyncMock()
    session.flush = AsyncMock()

    session_factory = MagicMock(return_value=session)

    event_repo = AsyncMock()
    new_event = MagicMock()
    new_event.id = uuid.uuid4()
    event_repo.create.return_value = new_event

    dlq_repo = AsyncMock()
    dlq_repo.get_by_id.return_value = dlq_entry
    dlq_repo.mark_replayed = AsyncMock()
    dlq_repo.get_unreplayed_by_filter = AsyncMock(
        return_value=[dlq_entry] if dlq_entry else []
    )

    circuit_breaker = AsyncMock()
    circuit_breaker.reset = AsyncMock()

    arq_pool = AsyncMock()
    arq_pool.enqueue_job = AsyncMock()

    service = ReplayService(
        session_factory=session_factory,
        event_repo=event_repo,
        dlq_repo=dlq_repo,
        circuit_breaker=circuit_breaker,
        arq_pool=arq_pool,
    )
    return service, event_repo, dlq_repo, circuit_breaker, arq_pool


class TestReplayService:
    @pytest.mark.asyncio
    async def test_replay_creates_new_event(self):
        entry = _make_dlq_entry()
        svc, event_repo, dlq_repo, cb, arq = _make_replay_service(entry)
        result = await svc.replay_single(entry.id)
        assert result["enqueued"] is True
        assert result["original_dlq_id"] == entry.id
        event_repo.create.assert_called_once()
        dlq_repo.mark_replayed.assert_called_once()
        cb.reset.assert_called_once_with(str(entry.endpoint_id))
        arq.enqueue_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_replay_not_found(self):
        svc, *_ = _make_replay_service(dlq_entry=None)
        with pytest.raises(DeadLetterNotFoundError):
            await svc.replay_single(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_replay_recently_replayed_raises(self):
        entry = _make_dlq_entry(
            replay_count=1,
            replayed_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        )
        svc, *_ = _make_replay_service(entry)
        with pytest.raises(RecentlyReplayedError):
            await svc.replay_single(entry.id)

    @pytest.mark.asyncio
    async def test_replay_recently_replayed_with_force(self):
        entry = _make_dlq_entry(
            replay_count=1,
            replayed_at=datetime.now(timezone.utc) - timedelta(minutes=30),
        )
        svc, *_ = _make_replay_service(entry)
        result = await svc.replay_single(entry.id, force=True)
        assert result["enqueued"] is True

    @pytest.mark.asyncio
    async def test_replay_old_replay_allowed(self):
        entry = _make_dlq_entry(
            replay_count=1,
            replayed_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        svc, *_ = _make_replay_service(entry)
        result = await svc.replay_single(entry.id)
        assert result["enqueued"] is True

    @pytest.mark.asyncio
    async def test_bulk_replay(self):
        entry = _make_dlq_entry()
        svc, event_repo, dlq_repo, cb, arq = _make_replay_service(entry)
        result = await svc.replay_bulk(endpoint_id=entry.endpoint_id)
        assert result["replayed"] == 1
        assert result["errors"] == 0
