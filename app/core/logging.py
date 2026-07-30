"""Structured logging.

JSON in production (easy to ship to a log store), coloured console in dev. A
contextvar carries a correlation id so every line emitted while handling a
request or running a job can be traced back to it.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import cast

import structlog
from structlog.typing import EventDict, WrappedLogger

correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def _add_correlation_id(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    cid = correlation_id.get()
    if cid is not None:
        event_dict["correlation_id"] = cid
    return event_dict


def configure_logging(*, json_logs: bool, level: str = "INFO") -> None:
    shared: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_correlation_id,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: structlog.typing.Processor = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=True)
    )
    structlog.configure(
        processors=[*shared, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    handler = logging.StreamHandler(sys.stdout)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return cast("structlog.stdlib.BoundLogger", structlog.get_logger(name))
