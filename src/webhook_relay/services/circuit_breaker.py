import time
from enum import StrEnum

import redis.asyncio as aioredis


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        redis: aioredis.Redis,
        failure_threshold: int = 5,
        failure_window: int = 60,
        recovery_timeout: int = 300,
    ):
        self._redis = redis
        self._failure_threshold = failure_threshold
        self._failure_window = failure_window
        self._recovery_timeout = recovery_timeout

    async def get_state(self, endpoint_id: str) -> CircuitState:
        state = await self._redis.get(f"cb:{endpoint_id}:state")
        if state is None:
            return CircuitState.CLOSED

        state = CircuitState(state)

        if state == CircuitState.OPEN:
            opened_at = await self._redis.get(f"cb:{endpoint_id}:opened_at")
            if opened_at:
                elapsed = time.time() - float(opened_at)
                if elapsed > self._recovery_timeout:
                    await self._transition_to(endpoint_id, CircuitState.HALF_OPEN)
                    return CircuitState.HALF_OPEN

        return state

    async def is_allowed(self, endpoint_id: str) -> bool:
        state = await self.get_state(endpoint_id)
        return state != CircuitState.OPEN

    async def record_success(self, endpoint_id: str) -> None:
        state = await self.get_state(endpoint_id)
        if state == CircuitState.HALF_OPEN:
            await self._transition_to(endpoint_id, CircuitState.CLOSED)
            await self._redis.delete(f"cb:{endpoint_id}:failures")

    async def record_failure(self, endpoint_id: str) -> CircuitState:
        pipe = self._redis.pipeline()
        failures_key = f"cb:{endpoint_id}:failures"
        pipe.incr(failures_key)
        pipe.expire(failures_key, self._failure_window)
        results = await pipe.execute()
        failure_count = results[0]

        current_state = await self.get_state(endpoint_id)

        if failure_count >= self._failure_threshold and current_state == CircuitState.CLOSED:
            await self._transition_to(endpoint_id, CircuitState.OPEN)
            return CircuitState.OPEN

        if current_state == CircuitState.HALF_OPEN:
            await self._transition_to(endpoint_id, CircuitState.OPEN)
            return CircuitState.OPEN

        return current_state

    async def reset(self, endpoint_id: str) -> None:
        pipe = self._redis.pipeline()
        pipe.delete(f"cb:{endpoint_id}:state")
        pipe.delete(f"cb:{endpoint_id}:failures")
        pipe.delete(f"cb:{endpoint_id}:opened_at")
        await pipe.execute()

    async def _transition_to(self, endpoint_id: str, state: CircuitState) -> None:
        pipe = self._redis.pipeline()
        pipe.set(f"cb:{endpoint_id}:state", state.value)
        if state == CircuitState.OPEN:
            pipe.set(f"cb:{endpoint_id}:opened_at", str(time.time()))
        elif state == CircuitState.CLOSED:
            pipe.delete(f"cb:{endpoint_id}:opened_at")
        await pipe.execute()

    async def get_open_circuits(self) -> list[str]:
        keys = []
        async for key in self._redis.scan_iter("cb:*:state"):
            val = await self._redis.get(key)
            if val == CircuitState.OPEN:
                endpoint_id = key.split(":")[1]
                keys.append(endpoint_id)
        return keys
