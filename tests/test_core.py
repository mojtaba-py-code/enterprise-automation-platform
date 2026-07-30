"""Core: settings guard, security, resilience, rate limiting, conditions."""

from __future__ import annotations

import time

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import INSECURE_DEFAULT_SECRET, Settings
from app.core.rate_limit import InMemoryRateLimiter, RedisRateLimiter
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_key,
    hash_password,
    verify_password,
)
from app.domain.workflow import evaluate_condition
from app.resilience.cache import InMemoryCache, RedisCache
from app.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerOpen, CircuitState
from app.resilience.retry import retry_async


# --- config -----------------------------------------------------------------
def test_default_secret_refused_in_production() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(environment="production")


def test_default_secret_allowed_in_dev() -> None:
    assert Settings(environment="development").secret_key == INSECURE_DEFAULT_SECRET


def test_cors_origins_from_csv() -> None:
    assert Settings(cors_origins="http://a, http://b").cors_origins == ["http://a", "http://b"]


# --- security ---------------------------------------------------------------
def _settings() -> Settings:
    return Settings(secret_key="unit-test-secret-key-long-enough-000000")


def test_password_round_trip() -> None:
    hashed = hash_password("correct horse")
    assert verify_password("correct horse", hashed)
    assert not verify_password("wrong", hashed)
    assert verify_password("x", "not-a-hash") is False


def test_token_type_is_enforced() -> None:
    s = _settings()
    refresh = create_refresh_token("u1", s)
    with pytest.raises(TokenError):
        decode_token(refresh, expected_type="access", settings=s)


def test_expired_token_rejected() -> None:
    s = Settings(secret_key="k" * 32, access_token_ttl=-1)
    token = create_access_token("u1", s)
    time.sleep(0.01)
    with pytest.raises(TokenError):
        decode_token(token, expected_type="access", settings=s)


def test_api_key_is_hashed() -> None:
    plaintext, hashed = generate_api_key()
    assert plaintext.startswith("eap_")
    assert verify_password(plaintext, hashed)


# --- retry ------------------------------------------------------------------
async def _nosleep(_: float) -> None:
    return None


async def test_retry_succeeds_after_failures() -> None:
    calls = {"n": 0}

    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return "ok"

    assert await retry_async(flaky, attempts=3, sleeper=_nosleep) == "ok"
    assert calls["n"] == 3


async def test_retry_gives_up() -> None:
    async def always_fail() -> None:
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        await retry_async(always_fail, attempts=2, sleeper=_nosleep)


# --- circuit breaker --------------------------------------------------------
class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def test_circuit_breaker_opens_and_recovers() -> None:
    clock = _Clock()
    breaker = CircuitBreaker("x", failure_threshold=1, recovery_seconds=5, clock=clock)

    async def boom() -> None:
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        await breaker.call(boom)
    assert breaker.state is CircuitState.OPEN
    with pytest.raises(CircuitBreakerOpen):
        await breaker.call(boom)

    clock.now = 6.0

    async def ok() -> str:
        return "up"

    assert await breaker.call(ok) == "up"
    assert breaker.state is CircuitState.CLOSED


# --- cache & rate limiting --------------------------------------------------
async def test_in_memory_cache_expiry() -> None:
    cache = InMemoryCache()
    await cache.set("k", "v", ttl=100)
    assert await cache.get("k") == "v"
    await cache.set("gone", "v", ttl=0)
    assert await cache.get("gone") is None
    await cache.delete("k")
    assert await cache.get("k") is None


class _FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}
        self.counts: dict[str, int] = {}

    async def get(self, key: str) -> bytes | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value.encode()

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> None:
        return None


async def test_redis_cache_round_trip() -> None:
    cache = RedisCache(_FakeRedis())  # type: ignore[arg-type]
    assert await cache.get("missing") is None
    await cache.set("k", "v", ttl=60)
    assert await cache.get("k") == "v"


async def test_rate_limiters_block() -> None:
    mem = InMemoryRateLimiter(limit=2)
    assert (await mem.check("a"))[0]
    assert (await mem.check("a"))[0]
    assert (await mem.check("a")) == (False, 0)

    redis = RedisRateLimiter(_FakeRedis(), limit=1)  # type: ignore[arg-type]
    assert (await redis.check("b")) == (True, 0)
    assert (await redis.check("b"))[0] is False


# --- condition evaluator ----------------------------------------------------
@pytest.mark.parametrize(
    ("expr", "variables", "expected"),
    [
        ("a.size > 0", {"a": {"size": 5}}, True),
        ("a.size > 0", {"a": {"size": 0}}, False),
        ("name == 'Mojtaba'", {"name": "Mojtaba"}, True),
        ("flag", {"flag": True}, True),
        ("flag", {"flag": False}, False),
        ("missing.value == 1", {}, False),
        ("count >= 3", {"count": 3}, True),
        ("ok != false", {"ok": True}, True),
    ],
)
def test_evaluate_condition(expr: str, variables: dict, expected: bool) -> None:
    assert evaluate_condition(expr, variables) is expected


async def test_metrics_endpoint(client: httpx.AsyncClient) -> None:
    await client.get("/api/v1/health/live")
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "http_requests_total" in resp.text
