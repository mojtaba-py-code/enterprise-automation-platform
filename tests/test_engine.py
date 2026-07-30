"""Workflow engine: data flow, conditions, retries, timeouts and rollback."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.domain.plugins import Plugin, PluginContext
from app.domain.workflow import RunStatus, StepStatus, WorkflowDefinition
from app.plugins import default_registry
from app.plugins.registry import PluginRegistry
from app.services.workflow_engine import WorkflowEngine


async def _nosleep(_: float) -> None:
    return None


class EmptyParams(BaseModel):
    pass


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(secret_key="k" * 32, workspace_dir=tmp_path / "ws", default_step_retries=1)


@pytest.fixture
def engine(settings: Settings) -> WorkflowEngine:
    settings.workspace_dir.mkdir(parents=True, exist_ok=True)
    return WorkflowEngine(default_registry, settings, sleeper=_nosleep)


async def test_happy_path_with_data_flow(engine: WorkflowEngine) -> None:
    wf = WorkflowDefinition.model_validate(
        {
            "name": "flow",
            "steps": [
                {"id": "vars", "plugin": "transform.set", "params": {"values": {"name": "Ada"}}},
                {
                    "id": "write",
                    "plugin": "file.write",
                    "params": {"path": "hi.txt", "content": "Hello ${vars.name}"},
                },
                {"id": "read", "plugin": "file.read", "params": {"path": "hi.txt"}},
                {
                    "id": "check",
                    "plugin": "transform.validate",
                    "params": {"value": "${read.content}", "min_length": 3},
                },
            ],
        }
    )
    result = await engine.run(wf)
    assert result.status is RunStatus.SUCCESS
    assert result.variables["read"]["content"] == "Hello Ada"
    assert all(s.status is StepStatus.SUCCESS for s in result.steps)


async def test_conditional_skip(engine: WorkflowEngine) -> None:
    wf = WorkflowDefinition.model_validate(
        {
            "name": "cond",
            "steps": [
                {"id": "vars", "plugin": "transform.set", "params": {"values": {"n": 1}}},
                {
                    "id": "maybe",
                    "plugin": "transform.set",
                    "params": {"values": {"x": 1}},
                    "when": "vars.n > 100",
                },
            ],
        }
    )
    result = await engine.run(wf)
    assert result.steps[1].status is StepStatus.SKIPPED


# A custom plugin whose behaviour we control, registered on a private registry.
class FlakyPlugin(Plugin):
    name = "test.flaky"
    params_model = EmptyParams

    def __init__(self, fail_times: int) -> None:
        self.fail_times = fail_times
        self.calls = 0

    async def run(self, params: BaseModel, context: PluginContext) -> dict[str, Any]:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("transient")
        return {"ok": True}


class RecordingPlugin(Plugin):
    name = "test.record"
    supports_rollback = True
    params_model = EmptyParams

    def __init__(self) -> None:
        self.compensated = 0

    async def run(self, params: BaseModel, context: PluginContext) -> dict[str, Any]:
        return {"done": True}

    async def compensate(
        self, params: BaseModel, context: PluginContext, output: dict[str, Any]
    ) -> None:
        self.compensated += 1


class AlwaysFailPlugin(Plugin):
    name = "test.fail"
    params_model = EmptyParams

    async def run(self, params: BaseModel, context: PluginContext) -> dict[str, Any]:
        raise RuntimeError("permanent")


def _engine_with(registry: PluginRegistry, settings: Settings) -> WorkflowEngine:
    return WorkflowEngine(registry, settings, sleeper=_nosleep)


async def test_step_retries_until_success(settings: Settings) -> None:
    reg = PluginRegistry()
    flaky = FlakyPlugin(fail_times=2)
    reg.add(flaky)
    engine = _engine_with(reg, settings)
    wf = WorkflowDefinition.model_validate(
        {"name": "r", "steps": [{"id": "s", "plugin": "test.flaky", "retries": 3}]}
    )
    result = await engine.run(wf)
    assert result.status is RunStatus.SUCCESS
    assert result.steps[0].attempts == 3
    assert flaky.calls == 3


async def test_rollback_compensates_completed_steps(settings: Settings) -> None:
    reg = PluginRegistry()
    recorder = RecordingPlugin()
    reg.add(recorder)
    reg.add(AlwaysFailPlugin())
    engine = _engine_with(reg, settings)
    wf = WorkflowDefinition.model_validate(
        {
            "name": "rb",
            "steps": [
                {"id": "first", "plugin": "test.record"},
                {"id": "boom", "plugin": "test.fail", "retries": 0, "on_error": "rollback"},
            ],
        }
    )
    result = await engine.run(wf)
    assert result.status is RunStatus.FAILED
    assert recorder.compensated == 1
    assert result.steps[0].status is StepStatus.ROLLED_BACK
    assert result.steps[1].status is StepStatus.FAILED


async def test_on_error_continue(settings: Settings) -> None:
    reg = PluginRegistry()
    reg.add(AlwaysFailPlugin())
    reg.add(RecordingPlugin())
    engine = _engine_with(reg, settings)
    wf = WorkflowDefinition.model_validate(
        {
            "name": "cont",
            "steps": [
                {"id": "boom", "plugin": "test.fail", "retries": 0, "on_error": "continue"},
                {"id": "after", "plugin": "test.record"},
            ],
        }
    )
    result = await engine.run(wf)
    assert result.status is RunStatus.FAILED  # a step failed...
    assert result.steps[1].status is StepStatus.SUCCESS  # ...but the next one still ran


async def test_unknown_plugin_is_a_step_failure(settings: Settings) -> None:
    engine = _engine_with(PluginRegistry(), settings)
    wf = WorkflowDefinition.model_validate(
        {"name": "u", "steps": [{"id": "s", "plugin": "does.not.exist", "retries": 0}]}
    )
    result = await engine.run(wf)
    assert result.status is RunStatus.FAILED
    assert result.steps[0].status is StepStatus.FAILED


async def test_step_timeout(settings: Settings) -> None:
    class SlowPlugin(Plugin):
        name = "test.slow"
        params_model = EmptyParams

        async def run(self, params: BaseModel, context: PluginContext) -> dict[str, Any]:
            await asyncio.sleep(1)
            return {}

    reg = PluginRegistry()
    reg.add(SlowPlugin())
    engine = _engine_with(reg, settings)
    wf = WorkflowDefinition.model_validate(
        {"name": "t", "steps": [{"id": "s", "plugin": "test.slow", "timeout": 0.01, "retries": 0}]}
    )
    result = await engine.run(wf)
    assert result.steps[0].status is StepStatus.FAILED
