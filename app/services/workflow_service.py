"""Workflow application service.

Sits between the API/CLI and the engine: validates definitions (structure and
that every referenced plugin exists and is enabled), persists workflows, runs
them through the engine, and records each run.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import ValidationError

from app.core.errors import ValidationFailedError, WorkflowError
from app.db.models import Workflow, WorkflowRun
from app.domain.workflow import WorkflowDefinition, WorkflowRunResult
from app.plugins.registry import PluginRegistry
from app.repositories.workflows import RunRepository, WorkflowRepository
from app.services.workflow_engine import WorkflowEngine


class WorkflowService:
    def __init__(
        self,
        *,
        workflows: WorkflowRepository,
        runs: RunRepository,
        engine: WorkflowEngine,
        registry: PluginRegistry,
    ) -> None:
        self._workflows = workflows
        self._runs = runs
        self._engine = engine
        self._registry = registry

    def parse_definition(self, raw: dict[str, Any]) -> WorkflowDefinition:
        try:
            definition = WorkflowDefinition.model_validate(raw)
        except ValidationError as exc:
            raise ValidationFailedError(f"invalid workflow definition: {exc}") from exc
        self._check_plugins(definition)
        self._check_unique_step_ids(definition)
        return definition

    async def create(
        self, *, owner_id: uuid.UUID, name: str, description: str, definition: dict[str, Any]
    ) -> Workflow:
        self.parse_definition(definition)
        return await self._workflows.create(
            owner_id=owner_id, name=name, description=description, definition=definition
        )

    async def execute(
        self, workflow: Workflow, *, trigger: str = "manual", initial: dict[str, Any] | None = None
    ) -> tuple[WorkflowRun, WorkflowRunResult]:
        definition = self.parse_definition(workflow.definition)
        result = await self._engine.run(definition, initial)
        run = await self._runs.record(
            workflow_id=workflow.id,
            owner_id=workflow.owner_id,
            trigger=trigger,
            result=result,
        )
        return run, result

    def _check_plugins(self, definition: WorkflowDefinition) -> None:
        for step in definition.steps:
            if not self._registry.is_enabled(step.plugin):
                raise WorkflowError(
                    f"step '{step.id}' references an unknown or disabled plugin: {step.plugin!r}"
                )

    @staticmethod
    def _check_unique_step_ids(definition: WorkflowDefinition) -> None:
        ids = definition.step_ids()
        if len(ids) != len(set(ids)):
            raise WorkflowError("workflow step ids must be unique")
