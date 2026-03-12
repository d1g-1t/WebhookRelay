import logging
from contextlib import asynccontextmanager

import httpx
from arq import create_pool
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from webhook_relay.api.v1.router import router
from webhook_relay.config import settings
from webhook_relay.database import async_session, engine
from webhook_relay.middleware import RequestIDMiddleware
from webhook_relay.redis_client import create_redis_client, get_arq_redis_settings
from webhook_relay.services.circuit_breaker import CircuitBreaker
from webhook_relay.services.hmac_service import HMACService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s", settings.APP_NAME)
    app.state.redis = await create_redis_client()
    app.state.arq_pool = await create_pool(get_arq_redis_settings())
    app.state.http_client = httpx.AsyncClient()
    app.state.session_factory = async_session
    app.state.hmac_service = HMACService(settings.HMAC_TIMESTAMP_TOLERANCE_SECONDS)
    app.state.circuit_breaker = CircuitBreaker(
        redis=app.state.redis,
        failure_threshold=settings.CB_FAILURE_THRESHOLD,
        failure_window=settings.CB_FAILURE_WINDOW_SECONDS,
        recovery_timeout=settings.CB_RECOVERY_TIMEOUT_SECONDS,
    )
    logger.info("%s ready", settings.APP_NAME)
    yield
    await app.state.http_client.aclose()
    await app.state.arq_pool.close()
    await app.state.redis.aclose()
    await engine.dispose()
    logger.info("%s shutdown complete", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Reliable webhook delivery with retry, DLQ, HMAC signing, and circuit breaker.",
    lifespan=lifespan,
)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
