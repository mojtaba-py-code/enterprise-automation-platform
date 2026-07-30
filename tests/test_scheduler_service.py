"""Scheduler wrapper and workflow-service validation branches."""

from __future__ import annotations

import pytest

from app.core.errors import ValidationFailedError, WorkflowError
from app.plugins import default_registry
from app.services.scheduler import Scheduler
from app.services.workflow_service import WorkflowService


async def _job() -> None:
    return None


def test_scheduler_add_list_remove() -> None:
    scheduler = Scheduler()
    scheduler.add_interval("j1", _job, seconds=60)
    assert any(job["id"] == "j1" for job in scheduler.jobs())

    scheduler.add_cron("j2", _job, expression="0 * * * *")
    assert {j["id"] for j in scheduler.jobs()} == {"j1", "j2"}

    scheduler.remove("j1")
    assert {j["id"] for j in scheduler.jobs()} == {"j2"}


def test_scheduler_rejects_bad_cron() -> None:
    scheduler = Scheduler()
    with pytest.raises(ValidationFailedError):
        scheduler.add_cron("bad", _job, expression="not-a-cron")


def _service() -> WorkflowService:
    # parse_definition only needs the registry; repos/engine are unused here.
    return WorkflowService(
        workflows=None,  # type: ignore[arg-type]
        runs=None,  # type: ignore[arg-type]
        engine=None,  # type: ignore[arg-type]
        registry=default_registry,
    )


def test_parse_definition_rejects_malformed() -> None:
    with pytest.raises(ValidationFailedError):
        _service().parse_definition({"name": "x"})  # no steps


def test_parse_definition_rejects_unknown_plugin() -> None:
    with pytest.raises(WorkflowError):
        _service().parse_definition(
            {"name": "x", "steps": [{"id": "s", "plugin": "ghost", "params": {}}]}
        )


def test_parse_definition_accepts_valid() -> None:
    definition = _service().parse_definition(
        {"name": "ok", "steps": [{"id": "s", "plugin": "transform.set", "params": {}}]}
    )
    assert definition.name == "ok"
