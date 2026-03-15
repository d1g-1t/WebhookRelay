import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from webhook_relay.config import Settings
from webhook_relay.models.dead_letter import DeadLetterEvent
from webhook_relay.models.delivery_attempt import DeliveryAttempt
from webhook_relay.repositories.dead_letter_repo import DeadLetterRepository
from webhook_relay.repositories.delivery_attempt_repo import DeliveryAttemptRepository
from webhook_relay.repositories.endpoint_repo import EndpointRepository
from webhook_relay.repositories.event_repo import EventRepository
from webhook_relay.services.circuit_breaker import CircuitBreaker
from webhook_relay.services.hmac_service import HMACService
from webhook_relay.services.retry_service import ExponentialBackoffStrategy

logger = logging.getLogger(__name__)


class DeliveryStatus(StrEnum):
    SUCCESS = "success"
    RETRY_SCHEDULED = "retry_scheduled"
    DEAD_LETTERED = "dead_lettered"
    CIRCUIT_OPEN = "circuit_open"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class DeliveryOutcome:
    status: DeliveryStatus
    event_id: uuid.UUID
    attempt_id: uuid.UUID | None = None
    duration_ms: float | None = None
    next_retry_at: datetime | None = None
    endpoint_id: uuid.UUID | None = None
    attempt_count: int | None = None


class DeliveryService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        http_client: httpx.AsyncClient,
        hmac_service: HMACService,
        circuit_breaker: CircuitBreaker,
        retry_strategy: ExponentialBackoffStrategy,
        event_repo: EventRepository,
        attempt_repo: DeliveryAttemptRepository,
        dlq_repo: DeadLetterRepository,
        endpoint_repo: EndpointRepository,
        settings: Settings,
    ):
        self._session_factory = session_factory
        self._http_client = http_client
        self._hmac_service = hmac_service
        self._circuit_breaker = circuit_breaker
        self._retry_strategy = retry_strategy
        self._event_repo = event_repo
        self._attempt_repo = attempt_repo
        self._dlq_repo = dlq_repo
        self._endpoint_repo = endpoint_repo
        self._settings = settings

    async def deliver(self, event_id: uuid.UUID) -> DeliveryOutcome:
        async with self._session_factory() as session:
            event = await self._event_repo.get_with_endpoint(session, event_id)
            if not event:
                return DeliveryOutcome(status=DeliveryStatus.NOT_FOUND, event_id=event_id)

            if event.status in ("delivered", "dead_lettered"):
                return DeliveryOutcome(status=DeliveryStatus.NOT_FOUND, event_id=event_id)

            endpoint = event.endpoint
            if not endpoint.is_active:
                await self._event_repo.mark_dead_lettered(session, event)
                await self._dlq_repo.create(
                    session,
                    DeadLetterEvent(
                        event_id=event.id,
                        endpoint_id=endpoint.id,
                        original_payload=event.payload,
                        event_type=event.event_type,
                        total_attempts=event.attempt_count,
                        last_error="Endpoint is inactive",
                    ),
                )
                await session.commit()
                return DeliveryOutcome(
                    status=DeliveryStatus.DEAD_LETTERED,
                    event_id=event_id,
                    attempt_count=event.attempt_count,
                )

            if not await self._circuit_breaker.is_allowed(str(endpoint.id)):
                next_retry = datetime.now(timezone.utc) + timedelta(
                    seconds=self._settings.CB_RECOVERY_TIMEOUT_SECONDS
                )
                await self._event_repo.schedule_retry(session, event, next_retry)
                await session.commit()
                return DeliveryOutcome(
                    status=DeliveryStatus.CIRCUIT_OPEN,
                    event_id=event_id,
                    endpoint_id=endpoint.id,
                    next_retry_at=next_retry,
                )

            await self._event_repo.mark_delivering(session, event)

            body = json.dumps(event.payload, separators=(",", ":"), sort_keys=True).encode()
            headers = self._hmac_service.get_signature_headers(
                body=body,
                secret=endpoint.signing_secret,
                event_id=str(event.id),
                event_type=event.event_type,
            )
            headers.update(endpoint.custom_headers)

            start = time.perf_counter()
            http_status = None
            response_body = None
            response_headers = None
            error_message = None
            success = False
            retry_after_header = None

            try:
                response = await self._http_client.post(
                    url=str(endpoint.url),
                    content=body,
                    headers=headers,
                    timeout=endpoint.timeout_seconds,
                )
                http_status = response.status_code
                response_body = response.text[:10_000]
                response_headers = dict(response.headers)
                retry_after_header = response.headers.get("Retry-After")
                success = 200 <= http_status < 300
            except httpx.TimeoutException as e:
                error_message = f"Timeout after {endpoint.timeout_seconds}s: {e}"
            except httpx.ConnectError as e:
                error_message = f"Connection error: {e}"
            except httpx.RequestError as e:
                error_message = f"Request error: {e}"

            duration_ms = (time.perf_counter() - start) * 1000

            attempt = await self._attempt_repo.create(
                session,
                DeliveryAttempt(
                    event_id=event.id,
                    attempt_number=event.attempt_count,
                    request_headers={k: v for k, v in headers.items() if k != "X-Webhook-Signature"},
                    request_body_hash=hashlib.sha256(body).hexdigest(),
                    http_status_code=http_status,
                    response_body=response_body,
                    response_headers=response_headers,
                    success=success,
                    error_message=error_message,
                    duration_ms=round(duration_ms, 2),
                ),
            )

            if success:
                await self._circuit_breaker.record_success(str(endpoint.id))
                await self._event_repo.mark_delivered(session, event)
                await session.commit()
                logger.info("Delivered event %s in %.1fms", event_id, duration_ms)
                return DeliveryOutcome(
                    status=DeliveryStatus.SUCCESS,
                    event_id=event_id,
                    attempt_id=attempt.id,
                    duration_ms=round(duration_ms, 2),
                )

            await self._circuit_breaker.record_failure(str(endpoint.id))

            if http_status == 410:
                await self._endpoint_repo.deactivate(session, endpoint.id)

            should_retry, delay_override = self._retry_strategy.should_retry(
                http_status_code=http_status,
                attempt_count=event.attempt_count,
                max_retries=endpoint.max_retries,
                retry_after_header=retry_after_header,
            )

            if should_retry:
                next_retry = self._retry_strategy.next_retry_at(
                    attempt_number=event.attempt_count,
                    backoff_base=endpoint.retry_backoff_base,
                    max_delay_seconds=endpoint.retry_max_delay_seconds,
                    delay_override=delay_override,
                )
                await self._event_repo.schedule_retry(session, event, next_retry)
                await session.commit()
                logger.info("Retry scheduled for event %s at %s", event_id, next_retry)
                return DeliveryOutcome(
                    status=DeliveryStatus.RETRY_SCHEDULED,
                    event_id=event_id,
                    next_retry_at=next_retry,
                )

            await self._dlq_repo.create(
                session,
                DeadLetterEvent(
                    event_id=event.id,
                    endpoint_id=endpoint.id,
                    original_payload=event.payload,
                    event_type=event.event_type,
                    total_attempts=event.attempt_count,
                    last_error=error_message or f"HTTP {http_status}",
                    last_http_status=http_status,
                ),
            )
            await self._event_repo.mark_dead_lettered(session, event)
            await session.commit()
            logger.warning("Event %s moved to DLQ after %d attempts", event_id, event.attempt_count)
            return DeliveryOutcome(
                status=DeliveryStatus.DEAD_LETTERED,
                event_id=event_id,
                attempt_count=event.attempt_count,
            )
