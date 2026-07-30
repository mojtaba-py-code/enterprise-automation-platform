"""Composition root — every long-lived collaborator is built once, here."""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import Settings
from app.core.rate_limit import InMemoryRateLimiter, RateLimiter, RedisRateLimiter
from app.db.session import create_engine, create_session_factory
from app.plugins import default_registry
from app.plugins.registry import PluginRegistry
from app.resilience.cache import Cache, InMemoryCache, RedisCache
from app.services.scheduler import Scheduler
from app.services.token_blocklist import TokenBlocklist
from app.services.workflow_engine import WorkflowEngine


class Container:
    def __init__(self, settings: Settings, *, cache: Cache | None = None) -> None:
        self.settings = settings
        self.engine = create_engine(settings)
        self.session_factory = create_session_factory(self.engine)
        self.registry: PluginRegistry = default_registry
        self.workflow_engine = WorkflowEngine(self.registry, settings)
        self.scheduler = Scheduler()

        self._redis: Redis | None = None
        if cache is not None:
            self.cache: Cache = cache
            self.rate_limiter: RateLimiter = InMemoryRateLimiter(
                limit=settings.rate_limit_per_minute
            )
        elif settings.redis_url is not None:
            self._redis = Redis.from_url(str(settings.redis_url))
            self.cache = RedisCache(self._redis)
            self.rate_limiter = RedisRateLimiter(self._redis, limit=settings.rate_limit_per_minute)
        else:
            self.cache = InMemoryCache()
            self.rate_limiter = InMemoryRateLimiter(limit=settings.rate_limit_per_minute)

        self.token_blocklist = TokenBlocklist(self.cache)

        # Ensure the filesystem sandbox exists.
        settings.workspace_dir.mkdir(parents=True, exist_ok=True)

    async def aclose(self) -> None:
        self.scheduler.shutdown()
        await self.engine.dispose()
        if self._redis is not None:
            await self._redis.aclose()
