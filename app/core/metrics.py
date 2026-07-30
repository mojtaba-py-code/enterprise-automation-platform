"""Prometheus metrics: RED signals per route plus workflow counters."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests.", ("method", "path", "status"))
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds", "HTTP request latency in seconds.", ("method", "path")
)
WORKFLOW_RUNS = Counter("workflow_runs_total", "Workflow runs by final status.", ("status",))
STEP_RUNS = Counter(
    "workflow_step_runs_total",
    "Workflow step executions by plugin and status.",
    ("plugin", "status"),
)

_METRICS_PATH = "/metrics"


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path == _METRICS_PATH:
            return await call_next(request)
        started = time.perf_counter()
        response = await call_next(request)
        template = _route_template(request)
        REQUEST_LATENCY.labels(request.method, template).observe(time.perf_counter() - started)
        REQUEST_COUNT.labels(request.method, template, response.status_code).inc()
        return response


def metrics_endpoint() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
