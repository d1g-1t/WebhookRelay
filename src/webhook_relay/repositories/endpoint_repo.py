import secrets
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from webhook_relay.models.endpoint import WebhookEndpoint


class EndpointRepository:
    async def create(self, session: AsyncSession, endpoint: WebhookEndpoint) -> WebhookEndpoint:
        session.add(endpoint)
        await session.flush()
        return endpoint

    async def get_by_id(
        self, session: AsyncSession, endpoint_id: uuid.UUID
    ) -> WebhookEndpoint | None:
        return await session.get(WebhookEndpoint, endpoint_id)

    async def get_all(
        self,
        session: AsyncSession,
        page: int = 1,
        size: int = 20,
        is_active: bool | None = None,
    ) -> tuple[list[WebhookEndpoint], int]:
        query = select(WebhookEndpoint)
        count_query = select(func.count()).select_from(WebhookEndpoint)

        if is_active is not None:
            query = query.where(WebhookEndpoint.is_active == is_active)
            count_query = count_query.where(WebhookEndpoint.is_active == is_active)

        query = query.order_by(WebhookEndpoint.created_at.desc())
        query = query.offset((page - 1) * size).limit(size)

        result = await session.execute(query)
        total = await session.scalar(count_query)
        return list(result.scalars().all()), total or 0

    async def update(
        self, session: AsyncSession, endpoint_id: uuid.UUID, data: dict
    ) -> WebhookEndpoint | None:
        endpoint = await self.get_by_id(session, endpoint_id)
        if not endpoint:
            return None
        for key, value in data.items():
            if value is not None:
                setattr(endpoint, key, value)
        await session.flush()
        return endpoint

    async def deactivate(self, session: AsyncSession, endpoint_id: uuid.UUID) -> bool:
        result = await session.execute(
            update(WebhookEndpoint)
            .where(WebhookEndpoint.id == endpoint_id)
            .values(is_active=False)
        )
        await session.flush()
        return result.rowcount > 0

    async def rotate_secret(
        self, session: AsyncSession, endpoint_id: uuid.UUID
    ) -> WebhookEndpoint | None:
        endpoint = await self.get_by_id(session, endpoint_id)
        if not endpoint:
            return None
        endpoint.signing_secret = secrets.token_hex(32)
        await session.flush()
        return endpoint
