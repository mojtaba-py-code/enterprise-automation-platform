"""Async retry with exponential backoff.

Used by the workflow engine (per-step retries) and by any plugin that talks to
a flaky external system. The sleeper is injectable so tests run instantly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

Sleeper = Callable[[float], Awaitable[None]]


async def retry_async[T](
    func: Callable[[], Awaitable[T]],
    *,
    attempts: int,
    base_delay: float = 0.2,
    max_delay: float = 5.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    sleeper: Sleeper | None = None,
) -> T:
    """Call ``func`` up to ``attempts`` times, backing off between failures."""
    sleep = sleeper or asyncio.sleep
    last_exc: BaseException | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return await func()
        except retry_on as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            await sleep(min(max_delay, base_delay * (2 ** (attempt - 1))))
    assert last_exc is not None
    raise last_exc
