import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from webhook_relay.models.delivery_attempt import DeliveryAttempt
from webhook_relay.models.endpoint import WebhookEndpoint
from webhook_relay.models.event import WebhookEvent
from webhook_relay.services.delivery_service import DeliveryService, DeliveryStatus
from webhook_relay.services.hmac_service import HMACService
from webhook_relay.services.retry_service import ExponentialBackoffStrategy


def _make_endpoint(**overrides):
    defaults = {
        "id": uuid.uuid4(),
        "name": "Test",
        "url": "https://example.com/webhook",
        "signing_secret": HMACService.generate_secret(),
        "max_retries": 5,
        "retry_backoff_base": 2.0,
        "retry_max_delay_seconds": 3600,
        "timeout_seconds": 30,
        "event_types_filter": [],
        "custom_headers": {},
        "is_active": True,
    }
    defaults.update(overrides)
    ep = MagicMock(spec=WebhookEndpoint)
    for k, v in defaults.items():
        setattr(ep, k, v)
    return ep


def _make_event(endpoint, **overrides):
    defaults = {
        "id": uuid.uuid4(),
        "endpoint_id": endpoint.id,
        "event_type": "test.event",
        "payload": {"key": "value"},
        "status": "pending",
        "attempt_count": 0,
        "endpoint": endpoint,
    }
    defaults.update(overrides)
    ev = MagicMock(spec=WebhookEvent)
    for k, v in defaults.items():
        setattr(ev, k, v)
    return ev


def _make_delivery_service(event=None, http_response=None, http_error=None):
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.commit = AsyncMock()
    session.flush = AsyncMock()

    session_factory = MagicMock(return_value=session)

    event_repo = AsyncMock()
    event_repo.get_with_endpoint.return_value = event
    event_repo.mark_delivering = AsyncMock()
    event_repo.mark_delivered = AsyncMock()
    event_repo.mark_dead_lettered = AsyncMock()
    event_repo.schedule_retry = AsyncMock()

    attempt_repo = AsyncMock()
    attempt_repo.create = AsyncMock(side_effect=lambda s, a: a)

    dlq_repo = AsyncMock()
    dlq_repo.create = AsyncMock()

    endpoint_repo = AsyncMock()
    endpoint_repo.deactivate = AsyncMock()

    circuit_breaker = AsyncMock()
    circuit_breaker.is_allowed.return_value = True
    circuit_breaker.record_success = AsyncMock()
    circuit_breaker.record_failure = AsyncMock()

    http_client = AsyncMock()
    if http_error:
        http_client.post.side_effect = http_error
    elif http_response:
        http_client.post.return_value = http_response

    settings = MagicMock()
    settings.CB_RECOVERY_TIMEOUT_SECONDS = 300

    service = DeliveryService(
        session_factory=session_factory,
        http_client=http_client,
        hmac_service=HMACService(),
        circuit_breaker=circuit_breaker,
        retry_strategy=ExponentialBackoffStrategy(),
        event_repo=event_repo,
        attempt_repo=attempt_repo,
        dlq_repo=dlq_repo,
        endpoint_repo=endpoint_repo,
        settings=settings,
    )
    return service, event_repo, dlq_repo, circuit_breaker, endpoint_repo


def _mock_response(status_code, text="", headers=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.headers = headers or {}
    return resp


class TestDeliveryService:
    @pytest.mark.asyncio
    async def test_successful_delivery(self):
        endpoint = _make_endpoint()
        event = _make_event(endpoint)
        svc, event_repo, dlq_repo, cb, _ = _make_delivery_service(
            event=event, http_response=_mock_response(200, "ok")
        )
        outcome = await svc.deliver(event.id)
        assert outcome.status == DeliveryStatus.SUCCESS
        event_repo.mark_delivered.assert_called_once()
        cb.record_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_500_triggers_retry(self):
        endpoint = _make_endpoint()
        event = _make_event(endpoint)
        svc, event_repo, dlq_repo, cb, _ = _make_delivery_service(
            event=event, http_response=_mock_response(500, "error")
        )
        outcome = await svc.deliver(event.id)
        assert outcome.status == DeliveryStatus.RETRY_SCHEDULED
        event_repo.schedule_retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_400_goes_to_dlq(self):
        endpoint = _make_endpoint()
        event = _make_event(endpoint)
        svc, event_repo, dlq_repo, cb, _ = _make_delivery_service(
            event=event, http_response=_mock_response(400, "bad request")
        )
        outcome = await svc.deliver(event.id)
        assert outcome.status == DeliveryStatus.DEAD_LETTERED
        dlq_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_429_with_retry_after(self):
        endpoint = _make_endpoint()
        event = _make_event(endpoint)
        svc, event_repo, *_ = _make_delivery_service(
            event=event,
            http_response=_mock_response(429, "rate limited", {"Retry-After": "120"}),
        )
        outcome = await svc.deliver(event.id)
        assert outcome.status == DeliveryStatus.RETRY_SCHEDULED

    @pytest.mark.asyncio
    async def test_max_retries_exhausted_goes_to_dlq(self):
        endpoint = _make_endpoint(max_retries=1)
        event = _make_event(endpoint, attempt_count=0)
        svc, event_repo, dlq_repo, *_ = _make_delivery_service(
            event=event, http_response=_mock_response(500, "error")
        )
        event.attempt_count = 1
        outcome = await svc.deliver(event.id)
        assert outcome.status == DeliveryStatus.DEAD_LETTERED

    @pytest.mark.asyncio
    async def test_connection_timeout_retries(self):
        import httpx

        endpoint = _make_endpoint()
        event = _make_event(endpoint)
        svc, event_repo, *_ = _make_delivery_service(
            event=event, http_error=httpx.ConnectError("connection refused")
        )
        outcome = await svc.deliver(event.id)
        assert outcome.status == DeliveryStatus.RETRY_SCHEDULED

    @pytest.mark.asyncio
    async def test_circuit_open_schedules_retry(self):
        endpoint = _make_endpoint()
        event = _make_event(endpoint)
        svc, event_repo, *_ = _make_delivery_service(
            event=event, http_response=_mock_response(200)
        )
        svc._circuit_breaker.is_allowed.return_value = False
        outcome = await svc.deliver(event.id)
        assert outcome.status == DeliveryStatus.CIRCUIT_OPEN

    @pytest.mark.asyncio
    async def test_410_deactivates_endpoint(self):
        endpoint = _make_endpoint()
        event = _make_event(endpoint)
        svc, event_repo, dlq_repo, cb, endpoint_repo = _make_delivery_service(
            event=event, http_response=_mock_response(410, "gone")
        )
        outcome = await svc.deliver(event.id)
        assert outcome.status == DeliveryStatus.DEAD_LETTERED
        endpoint_repo.deactivate.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_found_event(self):
        svc, *_ = _make_delivery_service(event=None)
        outcome = await svc.deliver(uuid.uuid4())
        assert outcome.status == DeliveryStatus.NOT_FOUND

    @pytest.mark.asyncio
    async def test_already_delivered_event_skipped(self):
        endpoint = _make_endpoint()
        event = _make_event(endpoint, status="delivered")
        svc, *_ = _make_delivery_service(event=event)
        outcome = await svc.deliver(event.id)
        assert outcome.status == DeliveryStatus.NOT_FOUND
