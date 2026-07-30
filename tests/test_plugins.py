"""Plugin behaviour, the sandbox, and the registry."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.core.errors import NotFoundError, ValidationFailedError
from app.domain.plugins import PluginContext
from app.plugins import default_registry
from app.plugins.email_plugin import EmailSendPlugin, SinkEmailSender
from app.plugins.excel_plugin import ExcelReadPlugin, ExcelWritePlugin
from app.plugins.file_plugin import FileReadPlugin, FileWritePlugin
from app.plugins.http_plugin import HttpRequestPlugin
from app.plugins.pdf_plugin import PdfReportPlugin
from app.plugins.registry import PluginRegistry
from app.plugins.transform_plugin import SetVariablesPlugin, ValidatePlugin


@pytest.fixture
def ctx(tmp_path: Path) -> PluginContext:
    return PluginContext(workspace=tmp_path)


async def _run(plugin, raw: dict, ctx: PluginContext) -> dict:
    return await plugin.run(plugin.validate_params(raw), ctx)


# --- sandbox ----------------------------------------------------------------
def test_sandbox_blocks_path_traversal(ctx: PluginContext) -> None:
    with pytest.raises(ValidationFailedError):
        ctx.safe_path("../../etc/passwd")


def test_sandbox_allows_nested_path(ctx: PluginContext) -> None:
    resolved = ctx.safe_path("a/b/c.txt")
    assert str(resolved).startswith(str(ctx.workspace.resolve()))


# --- template resolution ----------------------------------------------------
def test_context_resolves_templates(ctx: PluginContext) -> None:
    ctx.variables = {"read": {"content": "hello"}, "n": 3}
    assert ctx.resolve("${read.content}") == "hello"
    assert ctx.resolve("value=${n}") == "value=3"
    assert ctx.resolve({"x": "${read.content}"}) == {"x": "hello"}


def test_context_unknown_reference(ctx: PluginContext) -> None:
    with pytest.raises(ValidationFailedError):
        ctx.resolve("${nope.missing}")


# --- file plugins -----------------------------------------------------------
async def test_file_write_read_roundtrip(ctx: PluginContext) -> None:
    write = FileWritePlugin()
    out = await _run(write, {"path": "docs/a.txt", "content": "hi there"}, ctx)
    assert out["created"] is True
    assert (ctx.workspace / "docs" / "a.txt").read_text() == "hi there"

    read = FileReadPlugin()
    got = await _run(read, {"path": "docs/a.txt"}, ctx)
    assert got["content"] == "hi there"


async def test_file_write_rollback_deletes_created_file(ctx: PluginContext) -> None:
    write = FileWritePlugin()
    params = write.validate_params({"path": "tmp/x.txt", "content": "z"})
    output = await write.run(params, ctx)
    assert (ctx.workspace / "tmp" / "x.txt").exists()
    await write.compensate(params, ctx, output)
    assert not (ctx.workspace / "tmp" / "x.txt").exists()


async def test_file_read_missing(ctx: PluginContext) -> None:
    with pytest.raises(NotFoundError):
        await _run(FileReadPlugin(), {"path": "nope.txt"}, ctx)


# --- excel plugins ----------------------------------------------------------
async def test_excel_write_then_read(ctx: PluginContext) -> None:
    await _run(
        ExcelWritePlugin(),
        {"path": "report.xlsx", "header": ["name", "score"], "rows": [["A", 1], ["B", 2]]},
        ctx,
    )
    result = await _run(ExcelReadPlugin(), {"path": "report.xlsx", "has_header": True}, ctx)
    assert result["header"] == ["name", "score"]
    assert result["row_count"] == 2
    assert result["rows"][0] == ["A", 1]


# --- pdf plugin -------------------------------------------------------------
async def test_pdf_report(ctx: PluginContext) -> None:
    out = await _run(
        PdfReportPlugin(), {"path": "out.pdf", "title": "Q1", "lines": ["a", "b"]}, ctx
    )
    assert out["line_count"] == 2
    data = (ctx.workspace / "out.pdf").read_bytes()
    assert data.startswith(b"%PDF")


# --- transform plugins ------------------------------------------------------
async def test_set_and_validate(ctx: PluginContext) -> None:
    out = await _run(SetVariablesPlugin(), {"values": {"a": 1}}, ctx)
    assert out == {"a": 1}
    ok = await _run(ValidatePlugin(), {"value": "abcd", "min_length": 3}, ctx)
    assert ok["valid"] is True
    with pytest.raises(ValidationFailedError):
        await _run(ValidatePlugin(), {"value": "x", "min_length": 5}, ctx)


# --- http plugin (mock transport) -------------------------------------------
async def test_http_plugin_with_mock_transport(ctx: PluginContext) -> None:
    plugin = HttpRequestPlugin()
    plugin.transport = httpx.MockTransport(lambda _req: httpx.Response(200, json={"pong": True}))
    out = await _run(plugin, {"method": "GET", "url": "http://svc/ping"}, ctx)
    assert out["status_code"] == 200
    assert out["body"] == {"pong": True}
    assert out["ok"] is True


# --- email plugin -----------------------------------------------------------
async def test_email_plugin_records_message(ctx: PluginContext) -> None:
    plugin = EmailSendPlugin()
    sink = SinkEmailSender()
    plugin.sender = sink
    out = await _run(plugin, {"to": "x@example.com", "subject": "Hi", "body": "there"}, ctx)
    assert out["sent"] is True
    assert sink.outbox[0].to == "x@example.com"


# --- registry ---------------------------------------------------------------
def test_registry_enable_disable() -> None:
    reg = PluginRegistry()
    reg.add(FileReadPlugin())
    assert reg.is_enabled("file.read")
    reg.disable("file.read")
    assert not reg.is_enabled("file.read")
    with pytest.raises(NotFoundError):
        reg.get("file.read")
    reg.enable("file.read")
    assert reg.get("file.read").name == "file.read"


def test_registry_rejects_duplicates() -> None:
    reg = PluginRegistry()
    reg.add(FileReadPlugin())
    with pytest.raises(ValueError, match="duplicate"):
        reg.add(FileReadPlugin())


def test_default_registry_has_expected_plugins() -> None:
    names = default_registry.names()
    for expected in ("file.write", "excel.read", "pdf.report", "http.request", "email.send"):
        assert expected in names
