"""Excel automation plugins (openpyxl). Files stay inside the workspace sandbox."""

from __future__ import annotations

from typing import Any

from openpyxl import Workbook, load_workbook
from pydantic import BaseModel, Field

from app.core.errors import NotFoundError
from app.domain.plugins import Plugin, PluginContext
from app.plugins.registry import register


@register
class ExcelWritePlugin(Plugin):
    name = "excel.write"
    category = "excel"
    summary = "Write rows (optionally with a header) to an .xlsx workbook."

    class Params(BaseModel):
        path: str = Field(min_length=1)
        rows: list[list[Any]] = Field(default_factory=list)
        header: list[str] | None = None
        sheet_name: str = "Sheet1"

    params_model = Params

    async def run(self, params: BaseModel, context: PluginContext) -> dict[str, Any]:
        assert isinstance(params, ExcelWritePlugin.Params)
        target = context.safe_path(params.path)
        target.parent.mkdir(parents=True, exist_ok=True)

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = params.sheet_name
        written = 0
        if params.header:
            sheet.append(params.header)
        for row in params.rows:
            sheet.append(row)
            written += 1
        workbook.save(target)
        return {"path": str(target), "rows_written": written}


@register
class ExcelReadPlugin(Plugin):
    name = "excel.read"
    category = "excel"
    summary = "Read the first worksheet of an .xlsx workbook into a list of rows."

    class Params(BaseModel):
        path: str = Field(min_length=1)
        has_header: bool = True

    params_model = Params

    async def run(self, params: BaseModel, context: PluginContext) -> dict[str, Any]:
        assert isinstance(params, ExcelReadPlugin.Params)
        target = context.safe_path(params.path)
        if not target.is_file():
            raise NotFoundError(f"workbook not found: {params.path}")

        workbook = load_workbook(target, read_only=True, data_only=True)
        sheet = workbook.active
        rows = [list(row) for row in sheet.iter_rows(values_only=True)]
        workbook.close()

        header = rows[0] if (params.has_header and rows) else None
        body = rows[1:] if params.has_header else rows
        return {"header": header, "rows": body, "row_count": len(body)}
