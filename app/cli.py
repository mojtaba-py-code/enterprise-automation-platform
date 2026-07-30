"""Command-line interface for the automation platform.

Runs workflows directly through the engine (no server required), which is handy
for local development, cron jobs and CI pipelines.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer

from app.core.config import get_settings
from app.domain.workflow import WorkflowDefinition
from app.plugins import default_registry
from app.services.workflow_engine import WorkflowEngine

app = typer.Typer(add_completion=False, help="Enterprise Automation Platform CLI")


@app.command("plugins")
def list_plugins() -> None:
    """List every registered plugin."""
    for plugin in default_registry.all():
        typer.echo(f"{plugin.name:20} [{plugin.category}]  {plugin.summary}")


@app.command("run")
def run(path: Path) -> None:
    """Run a workflow defined in a JSON file."""
    definition = WorkflowDefinition.model_validate(json.loads(path.read_text(encoding="utf-8")))
    engine = WorkflowEngine(default_registry, get_settings())
    result = asyncio.run(engine.run(definition))

    typer.echo(f"workflow '{result.workflow}' -> {result.status.value}")
    for step in result.steps:
        detail = step.error or json.dumps(step.output)
        typer.echo(f"  {step.step_id:16} {step.plugin:18} {step.status.value:10} {detail}")
    raise typer.Exit(code=0 if result.status.value == "success" else 1)


if __name__ == "__main__":
    app()
