import time

import pytest

from webhook_relay.services.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreaker:
    @pytest.fixture(autouse=True)
    def setup(self, mock_redis):
        self.redis = mock_redis
        self.cb = CircuitBreaker(
            redis=self.redis,
            failure_threshold=3,
            failure_window=60,
            recovery_timeout=10,
        )

    @pytest.mark.asyncio
    async def test_default_state_is_closed(self):
        state = await self.cb.get_state("ep-1")
        assert state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_is_allowed_when_closed(self):
        assert await self.cb.is_allowed("ep-1")

    @pytest.mark.asyncio
    async def test_single_failure_stays_closed(self):
        state = await self.cb.record_failure("ep-1")
        assert state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self):
        for _ in range(2):
            await self.cb.record_failure("ep-1")
        state = await self.cb.record_failure("ep-1")
        assert state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_not_allowed_when_open(self):
        for _ in range(3):
            await self.cb.record_failure("ep-1")
        assert not await self.cb.is_allowed("ep-1")

    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_recovery(self):
        for _ in range(3):
            await self.cb.record_failure("ep-1")
        self.redis._data["cb:ep-1:opened_at"] = str(time.time() - 15)
        state = await self.cb.get_state("ep-1")
        assert state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_success_closes(self):
        for _ in range(3):
            await self.cb.record_failure("ep-1")
        self.redis._data["cb:ep-1:opened_at"] = str(time.time() - 15)
        await self.cb.get_state("ep-1")
        await self.cb.record_success("ep-1")
        state = await self.cb.get_state("ep-1")
        assert state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens(self):
        for _ in range(3):
            await self.cb.record_failure("ep-1")
        self.redis._data["cb:ep-1:opened_at"] = str(time.time() - 15)
        await self.cb.get_state("ep-1")
        state = await self.cb.record_failure("ep-1")
        assert state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_reset_clears_state(self):
        for _ in range(3):
            await self.cb.record_failure("ep-1")
        await self.cb.reset("ep-1")
        state = await self.cb.get_state("ep-1")
        assert state == CircuitState.CLOSED
        assert await self.cb.is_allowed("ep-1")
