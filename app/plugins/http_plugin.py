"""HTTP / API automation plugin.

The transport is an instance attribute so tests can inject an
``httpx.MockTransport`` without any network access.
"""

from __future__ import annotations

from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from app.core.errors import AppError
from app.domain.plugins import Plugin, PluginContext
from app.plugins.registry import register


@register
class HttpRequestPlugin(Plugin):
    name = "http.request"
    category = "api"
    summary = "Perform an HTTP request and capture the JSON/text response."

    class Params(BaseModel):
        method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
        url: str = Field(min_length=1)
        headers: dict[str, str] = Field(default_factory=dict)
        params: dict[str, Any] = Field(default_factory=dict)
        json_body: Any = None
        timeout: float = Field(default=15.0, gt=0)

    params_model = Params

    def __init__(self) -> None:
        self.transport: httpx.AsyncBaseTransport | None = None

    async def run(self, params: BaseModel, context: PluginContext) -> dict[str, Any]:
        assert isinstance(params, HttpRequestPlugin.Params)
        async with httpx.AsyncClient(transport=self.transport, timeout=params.timeout) as client:
            try:
                response = await client.request(
                    params.method,
                    params.url,
                    headers=params.headers,
                    params=params.params,
                    json=params.json_body,
                )
            except httpx.HTTPError as exc:
                raise AppError(f"http request failed: {exc}") from exc

        body: Any
        try:
            body = response.json()
        except ValueError:
            body = response.text
        return {"status_code": response.status_code, "body": body, "ok": response.is_success}
