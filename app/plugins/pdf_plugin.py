"""PDF automation plugin (ReportLab). Generates a simple titled report."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.domain.plugins import Plugin, PluginContext
from app.plugins.registry import register


@register
class PdfReportPlugin(Plugin):
    name = "pdf.report"
    category = "pdf"
    summary = "Render a titled PDF report from a list of text lines."

    class Params(BaseModel):
        path: str = Field(min_length=1)
        title: str = "Report"
        lines: list[str] = Field(default_factory=list)

    params_model = Params

    async def run(self, params: BaseModel, context: PluginContext) -> dict[str, Any]:
        assert isinstance(params, PdfReportPlugin.Params)
        target = context.safe_path(params.path)
        target.parent.mkdir(parents=True, exist_ok=True)

        styles = getSampleStyleSheet()
        story: list[Any] = [Paragraph(params.title, styles["Title"]), Spacer(1, 12)]
        for line in params.lines:
            story.append(Paragraph(line, styles["BodyText"]))

        SimpleDocTemplate(str(target), pagesize=A4).build(story)
        return {"path": str(target), "line_count": len(params.lines)}
