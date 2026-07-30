"""Filesystem automation plugins. All paths are confined to the workspace sandbox."""

from __future__ import annotations

import shutil
from typing import Any

from pydantic import BaseModel, Field

from app.core.errors import NotFoundError
from app.domain.plugins import Plugin, PluginContext
from app.plugins.registry import register


@register
class FileWritePlugin(Plugin):
    name = "file.write"
    category = "file"
    summary = "Write text content to a file inside the workspace."
    supports_rollback = True

    class Params(BaseModel):
        path: str = Field(min_length=1)
        content: str = ""
        overwrite: bool = True

    params_model = Params

    async def run(self, params: BaseModel, context: PluginContext) -> dict[str, Any]:
        assert isinstance(params, FileWritePlugin.Params)
        target = context.safe_path(params.path)
        created = not target.exists()
        if target.exists() and not params.overwrite:
            raise NotFoundError(f"file already exists: {params.path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(params.content, encoding="utf-8")
        return {"path": str(target), "bytes": len(params.content.encode()), "created": created}

    async def compensate(
        self, params: BaseModel, context: PluginContext, output: dict[str, Any]
    ) -> None:
        assert isinstance(params, FileWritePlugin.Params)
        if output.get("created"):
            context.safe_path(params.path).unlink(missing_ok=True)


@register
class FileReadPlugin(Plugin):
    name = "file.read"
    category = "file"
    summary = "Read a text file from the workspace."

    class Params(BaseModel):
        path: str = Field(min_length=1)

    params_model = Params

    async def run(self, params: BaseModel, context: PluginContext) -> dict[str, Any]:
        assert isinstance(params, FileReadPlugin.Params)
        target = context.safe_path(params.path)
        if not target.is_file():
            raise NotFoundError(f"file not found: {params.path}")
        content = target.read_text(encoding="utf-8")
        return {"content": content, "size": len(content), "path": str(target)}


@register
class FileMovePlugin(Plugin):
    name = "file.move"
    category = "file"
    summary = "Move or rename a file within the workspace."
    supports_rollback = True

    class Params(BaseModel):
        source: str = Field(min_length=1)
        destination: str = Field(min_length=1)

    params_model = Params

    async def run(self, params: BaseModel, context: PluginContext) -> dict[str, Any]:
        assert isinstance(params, FileMovePlugin.Params)
        src = context.safe_path(params.source)
        dst = context.safe_path(params.destination)
        if not src.exists():
            raise NotFoundError(f"source not found: {params.source}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return {"source": str(src), "destination": str(dst)}

    async def compensate(
        self, params: BaseModel, context: PluginContext, output: dict[str, Any]
    ) -> None:
        src, dst = output.get("source"), output.get("destination")
        if src and dst:
            shutil.move(dst, src)


@register
class FileDeletePlugin(Plugin):
    name = "file.delete"
    category = "file"
    summary = "Delete a file from the workspace."

    class Params(BaseModel):
        path: str = Field(min_length=1)
        missing_ok: bool = True

    params_model = Params

    async def run(self, params: BaseModel, context: PluginContext) -> dict[str, Any]:
        assert isinstance(params, FileDeletePlugin.Params)
        target = context.safe_path(params.path)
        existed = target.exists()
        if not existed and not params.missing_ok:
            raise NotFoundError(f"file not found: {params.path}")
        target.unlink(missing_ok=True)
        return {"path": str(target), "deleted": existed}
