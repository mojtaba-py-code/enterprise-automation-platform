"""Workflow and run persistence."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RunStatus, StepRun, Workflow, WorkflowRun
from app.domain.workflow import WorkflowRunResult


class WorkflowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, owner_id: uuid.UUID, name: str, description: str, definition: dict[str, Any]
    ) -> Workflow:
        workflow = Workflow(
            owner_id=owner_id, name=name, description=description, definition=definition
        )
        self._session.add(workflow)
        await self._session.flush()
        return workflow

    async def get_owned(self, workflow_id: uuid.UUID, owner_id: uuid.UUID) -> Workflow | None:
        result = await self._session.execute(
            select(Workflow).where(Workflow.id == workflow_id, Workflow.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def list_for_owner(
        self, owner_id: uuid.UUID, *, limit: int, offset: int
    ) -> list[Workflow]:
        result = await self._session.execute(
            select(Workflow)
            .where(Workflow.owner_id == owner_id)
            .order_by(Workflow.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def delete(self, workflow: Workflow) -> None:
        await self._session.delete(workflow)
        await self._session.flush()


class RunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        workflow_id: uuid.UUID,
        owner_id: uuid.UUID,
        trigger: str,
        result: WorkflowRunResult,
    ) -> WorkflowRun:
        run = WorkflowRun(
            workflow_id=workflow_id,
            owner_id=owner_id,
            trigger=trigger,
            status=RunStatus(result.status.value),
            variables=result.variables,
            finished_at=datetime.now(UTC),
        )
        self._session.add(run)
        await self._session.flush()
        for position, outcome in enumerate(result.steps):
            self._session.add(
                StepRun(
                    run_id=run.id,
                    position=position,
                    step_id=outcome.step_id,
                    plugin=outcome.plugin,
                    status=outcome.status.value,
                    error=outcome.error,
                    duration_ms=outcome.duration_ms,
                    attempts=outcome.attempts,
                    output=outcome.output,
                )
            )
        await self._session.flush()
        return run

    async def get_owned(self, run_id: uuid.UUID, owner_id: uuid.UUID) -> WorkflowRun | None:
        result = await self._session.execute(
            select(WorkflowRun).where(WorkflowRun.id == run_id, WorkflowRun.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def list_for_owner(
        self, owner_id: uuid.UUID, *, limit: int, offset: int
    ) -> list[WorkflowRun]:
        result = await self._session.execute(
            select(WorkflowRun)
            .where(WorkflowRun.owner_id == owner_id)
            .order_by(WorkflowRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_by_status(self, owner_id: uuid.UUID) -> dict[str, int]:
        result = await self._session.execute(
            select(WorkflowRun.status, func.count())
            .where(WorkflowRun.owner_id == owner_id)
            .group_by(WorkflowRun.status)
        )
        return {status.value: count for status, count in result.all()}
