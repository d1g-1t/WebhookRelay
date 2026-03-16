from fastapi import APIRouter

from webhook_relay.api.v1.delivery import router as delivery_router
from webhook_relay.api.v1.dlq import router as dlq_router
from webhook_relay.api.v1.endpoints import router as endpoints_router
from webhook_relay.api.v1.events import router as events_router

router = APIRouter(prefix="/api/v1")
router.include_router(endpoints_router)
router.include_router(events_router)
router.include_router(dlq_router)
router.include_router(delivery_router)
