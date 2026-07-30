"""A small async cache abstraction (in-memory for dev/tests, Redis for prod)."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from redis.asyncio import Redis


@runtime_checkable
class Cache(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl: int) -> None: ...

    async def delete(self, key: str) -> None: ...


class InMemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> str | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at <= time.monotonic():
                self._store.pop(key, None)
                return None
            return value

    async def set(self, key: str, value: str, ttl: int) -> None:
        async with self._lock:
            self._store[key] = (value, time.monotonic() + ttl)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)


class RedisCache:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def get(self, key: str) -> str | None:
        value = await self._client.get(key)
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else str(value)

    async def set(self, key: str, value: str, ttl: int) -> None:
        await self._client.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)
