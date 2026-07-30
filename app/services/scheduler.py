"""Scheduling service (APScheduler).

A thin, typed wrapper around ``AsyncIOScheduler`` so the rest of the app can
schedule workflow runs on an interval or a cron expression without depending on
APScheduler directly.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.errors import ValidationFailedError

AsyncJob = Callable[..., Awaitable[Any]]


class Scheduler:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def add_interval(
        self, job_id: str, func: AsyncJob, *, seconds: int, args: tuple[Any, ...] = ()
    ) -> None:
        self._scheduler.add_job(
            func, "interval", seconds=seconds, id=job_id, args=args, replace_existing=True
        )

    def add_cron(
        self, job_id: str, func: AsyncJob, *, expression: str, args: tuple[Any, ...] = ()
    ) -> None:
        try:
            trigger = CronTrigger.from_crontab(expression, timezone="UTC")
        except ValueError as exc:
            raise ValidationFailedError(f"invalid cron expression: {expression!r}") from exc
        self._scheduler.add_job(func, trigger, id=job_id, args=args, replace_existing=True)

    def remove(self, job_id: str) -> None:
        self._scheduler.remove_job(job_id)

    def jobs(self) -> list[dict[str, Any]]:
        # ``next_run_time`` is only populated once the scheduler is running, so
        # read it defensively to keep ``jobs()`` safe to call at any time.
        result: list[dict[str, Any]] = []
        for job in self._scheduler.get_jobs():
            next_run = getattr(job, "next_run_time", None)
            result.append(
                {
                    "id": job.id,
                    "trigger": str(job.trigger),
                    "next_run": next_run.isoformat() if next_run else None,
                }
            )
        return result
