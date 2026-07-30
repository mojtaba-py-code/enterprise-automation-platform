"""Supplementary coverage: file move/delete, http errors, token blocklist."""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest

from app.core.errors import AppError, NotFoundError
from app.domain.plugins import PluginContext
from app.plugins.file_plugin import FileDeletePlugin, FileMovePlugin, FileWritePlugin
from app.plugins.http_plugin import HttpRequestPlugin
from app.resilience.cache import InMemoryCache
from app.services.token_blocklist import TokenBlocklist


@pytest.fixture
def ctx(tmp_path: Path) -> PluginContext:
    return PluginContext(workspace=tmp_path)


async def _run(plugin, raw: dict, ctx: PluginContext) -> dict:
    return await plugin.run(plugin.validate_params(raw), ctx)


async def test_file_move_and_rollback(ctx: PluginContext) -> None:
    await _run(FileWritePlugin(), {"path": "a.txt", "content": "x"}, ctx)
    move = FileMovePlugin()
    params = move.validate_params({"source": "a.txt", "destination": "b.txt"})
    output = await move.run(params, ctx)
    assert (ctx.workspace / "b.txt").exists()
    assert not (ctx.workspace / "a.txt").exists()

    await move.compensate(params, ctx, output)
    assert (ctx.workspace / "a.txt").exists()


async def test_file_move_missing_source(ctx: PluginContext) -> None:
    with pytest.raises(NotFoundError):
        await _run(FileMovePlugin(), {"source": "ghost.txt", "destination": "x.txt"}, ctx)


async def test_file_delete(ctx: PluginContext) -> None:
    await _run(FileWritePlugin(), {"path": "d.txt", "content": "x"}, ctx)
    out = await _run(FileDeletePlugin(), {"path": "d.txt"}, ctx)
    assert out["deleted"] is True
    assert not (ctx.workspace / "d.txt").exists()

    missing = await _run(FileDeletePlugin(), {"path": "gone.txt"}, ctx)
    assert missing["deleted"] is False

    with pytest.raises(NotFoundError):
        await _run(FileDeletePlugin(), {"path": "gone.txt", "missing_ok": False}, ctx)


async def test_http_plugin_transport_error(ctx: PluginContext) -> None:
    def boom(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    plugin = HttpRequestPlugin()
    plugin.transport = httpx.MockTransport(boom)
    with pytest.raises(AppError):
        await _run(plugin, {"method": "GET", "url": "http://svc"}, ctx)


async def test_http_plugin_non_json_body(ctx: PluginContext) -> None:
    plugin = HttpRequestPlugin()
    plugin.transport = httpx.MockTransport(lambda _r: httpx.Response(200, text="plain text"))
    out = await _run(plugin, {"method": "GET", "url": "http://svc"}, ctx)
    assert out["body"] == "plain text"


async def test_token_blocklist() -> None:
    blocklist = TokenBlocklist(InMemoryCache())
    payload = {"jti": "abc", "exp": int(time.time()) + 100}
    assert await blocklist.is_revoked(payload) is False
    await blocklist.revoke(payload)
    assert await blocklist.is_revoked(payload) is True

    expired = {"jti": "old", "exp": int(time.time()) - 5}
    await blocklist.revoke(expired)
    assert await blocklist.is_revoked(expired) is False

    await blocklist.revoke({"exp": int(time.time()) + 100})  # no jti -> ignored
    assert await blocklist.is_revoked({"exp": 0}) is False
