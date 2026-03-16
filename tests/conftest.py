import pytest


class MockRedis:
    def __init__(self):
        self._data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def set(self, key: str, value, ex=None):
        self._data[key] = str(value)

    async def delete(self, *keys: str):
        for key in keys:
            self._data.pop(key, None)

    async def incr(self, key: str) -> int:
        val = int(self._data.get(key, 0)) + 1
        self._data[key] = str(val)
        return val

    async def expire(self, key: str, seconds: int):
        pass

    async def ping(self):
        return True

    async def aclose(self):
        pass

    async def scan_iter(self, pattern: str):
        for key in list(self._data.keys()):
            if key.endswith(pattern.replace("*", "").replace("cb:", "", 1)):
                yield key

    def pipeline(self):
        return MockPipeline(self)


class MockPipeline:
    def __init__(self, redis: MockRedis):
        self._redis = redis
        self._ops: list[tuple] = []

    def incr(self, key: str):
        self._ops.append(("incr", key))
        return self

    def expire(self, key: str, seconds: int):
        self._ops.append(("expire", key, seconds))
        return self

    def set(self, key: str, value):
        self._ops.append(("set", key, value))
        return self

    def delete(self, *keys: str):
        for key in keys:
            self._ops.append(("delete", key))
        return self

    async def execute(self):
        results = []
        for op in self._ops:
            if op[0] == "incr":
                val = int(self._redis._data.get(op[1], 0)) + 1
                self._redis._data[op[1]] = str(val)
                results.append(val)
            elif op[0] == "set":
                self._redis._data[op[1]] = str(op[2])
                results.append(True)
            elif op[0] == "expire":
                results.append(True)
            elif op[0] == "delete":
                self._redis._data.pop(op[1], None)
                results.append(1)
        self._ops = []
        return results


@pytest.fixture
def mock_redis():
    return MockRedis()
