from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from arq import ArqRedis
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from webhook_relay.repositories.dead_letter_repo import DeadLetterRepository
from webhook_relay.repositories.delivery_attempt_repo import DeliveryAttemptRepository
from webhook_relay.repositories.endpoint_repo import EndpointRepository
from webhook_relay.repositories.event_repo import EventRepository
from webhook_relay.services.circuit_breaker import CircuitBreaker
from webhook_relay.services.hmac_service import HMACService
from webhook_relay.services.replay_service import ReplayService


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with request.app.state.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


def get_arq_pool(request: Request) -> ArqRedis:
    return request.app.state.arq_pool


def get_endpoint_repo() -> EndpointRepository:
    return EndpointRepository()


def get_event_repo() -> EventRepository:
    return EventRepository()


def get_attempt_repo() -> DeliveryAttemptRepository:
    return DeliveryAttemptRepository()


def get_dlq_repo() -> DeadLetterRepository:
    return DeadLetterRepository()


def get_hmac_service(request: Request) -> HMACService:
    return request.app.state.hmac_service


def get_circuit_breaker(request: Request) -> CircuitBreaker:
    return request.app.state.circuit_breaker


async def get_replay_service(
    request: Request,
    dlq_repo: DeadLetterRepository = Depends(get_dlq_repo),
    event_repo: EventRepository = Depends(get_event_repo),
) -> ReplayService:
    return ReplayService(
        session_factory=request.app.state.session_factory,
        event_repo=event_repo,
        dlq_repo=dlq_repo,
        circuit_breaker=request.app.state.circuit_breaker,
        arq_pool=request.app.state.arq_pool,
    )
