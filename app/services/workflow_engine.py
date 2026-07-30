"""The workflow engine.

Executes a :class:`WorkflowDefinition` step by step over the plugin registry.
Supports conditional execution (``when``), per-step retries with backoff,
per-step timeouts, and compensating rollback on failure. A failing provider
never crashes the engine — the failure is captured on the step outcome and the
configured ``on_error`` policy decides what happens next.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from pydantic import BaseModel

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.metrics import STEP_RUNS, WORKFLOW_RUNS
from app.domain.plugins import Plugin, PluginContext
from app.domain.workflow import (
    OnError,
    RunStatus,
    StepDefinition,
    StepOutcome,
    StepStatus,
    WorkflowDefinition,
    WorkflowRunResult,
    evaluate_condition,
)
from app.plugins.registry import PluginRegistry
from app.resilience.retry import Sleeper, retry_async

logger = get_logger("workflow")


@dataclass(slots=True)
class _Completed:
    plugin: Plugin
    params: BaseModel
    outcome: StepOutcome


class WorkflowEngine:
    def __init__(
        self, registry: PluginRegistry, settings: Settings, *, sleeper: Sleeper | None = None
    ) -> None:
        self._registry = registry
        self._settings = settings
        self._sleeper = sleeper

    async def run(
        self, definition: WorkflowDefinition, initial: dict[str, object] | None = None
    ) -> WorkflowRunResult:
        context = PluginContext(
            workspace=self._settings.workspace_dir, variables=dict(initial or {})
        )
        result = WorkflowRunResult(workflow=definition.name, status=RunStatus.SUCCESS)
        completed: list[_Completed] = []

        for step in definition.steps:
            if step.when is not None and not evaluate_condition(step.when, context.variables):
                result.steps.append(
                    StepOutcome(step_id=step.id, plugin=step.plugin, status=StepStatus.SKIPPED)
                )
                continue

            outcome, plugin, params = await self._run_step(step, context)
            result.steps.append(outcome)

            if outcome.status is StepStatus.SUCCESS:
                assert plugin is not None and params is not None
                context.variables[step.id] = outcome.output
                completed.append(_Completed(plugin, params, outcome))
                continue

            # The step failed — apply the error policy.
            result.status = RunStatus.FAILED
            if step.on_error is OnError.CONTINUE:
                continue
            if step.on_error is OnError.ROLLBACK:
                await self._rollback(completed, context)
            break

        context_status = result.status.value
        WORKFLOW_RUNS.labels(context_status).inc()
        result.variables = context.variables
        return result

    async def _run_step(
        self, step: StepDefinition, context: PluginContext
    ) -> tuple[StepOutcome, Plugin | None, BaseModel | None]:
        started = time.perf_counter()
        try:
            plugin = self._registry.get(step.plugin)
            resolved = context.resolve(step.params)
            params = plugin.validate_params(resolved)
        except Exception as exc:
            STEP_RUNS.labels(step.plugin, "failed").inc()
            return self._failed(step, started, str(exc), attempts=0), None, None

        retries = step.retries if step.retries is not None else self._settings.default_step_retries
        timeout = step.timeout or self._settings.default_step_timeout
        attempts = 0

        async def call() -> dict[str, object]:
            nonlocal attempts
            attempts += 1
            return await asyncio.wait_for(plugin.run(params, context), timeout=timeout)

        try:
            output = await retry_async(call, attempts=retries + 1, sleeper=self._sleeper)
        except Exception as exc:
            STEP_RUNS.labels(step.plugin, "failed").inc()
            return self._failed(step, started, str(exc), attempts=attempts), None, None

        STEP_RUNS.labels(step.plugin, "success").inc()
        outcome = StepOutcome(
            step_id=step.id,
            plugin=step.plugin,
            status=StepStatus.SUCCESS,
            output=output,
            duration_ms=int((time.perf_counter() - started) * 1000),
            attempts=attempts,
        )
        return outcome, plugin, params

    @staticmethod
    def _failed(step: StepDefinition, started: float, error: str, *, attempts: int) -> StepOutcome:
        logger.warning("step_failed", step=step.id, plugin=step.plugin, error=error)
        return StepOutcome(
            step_id=step.id,
            plugin=step.plugin,
            status=StepStatus.FAILED,
            error=error,
            duration_ms=int((time.perf_counter() - started) * 1000),
            attempts=attempts,
        )

    async def _rollback(self, completed: list[_Completed], context: PluginContext) -> None:
        for entry in reversed(completed):
            try:
                await entry.plugin.compensate(entry.params, context, entry.outcome.output)
                entry.outcome.status = StepStatus.ROLLED_BACK
            except Exception as exc:  # rollback is best-effort; never mask the original error
                logger.error("rollback_failed", step=entry.outcome.step_id, error=str(exc))
