"""Workflow CRUD, execution and run history."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import CurrentUser, SessionDep, enforce_rate_limit, get_workflow_service
from app.core.errors import NotFoundError
from app.repositories.workflows import RunRepository, WorkflowRepository
from app.schemas.workflow import (
    RunDetailOut,
    RunOut,
    RunRequest,
    StepOut,
    WorkflowCreate,
    WorkflowOut,
)
from app.services.workflow_service import WorkflowService

router = APIRouter(
    prefix="/workflows", tags=["workflows"], dependencies=[Depends(enforce_rate_limit)]
)

ServiceDep = Annotated[WorkflowService, Depends(get_workflow_service)]


def _parse_id(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise NotFoundError("workflow not found") from exc


@router.post("", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    payload: WorkflowCreate, user: CurrentUser, service: ServiceDep
) -> WorkflowOut:
    workflow = await service.create(
        owner_id=user.id,
        name=payload.name,
        description=payload.description,
        definition=payload.definition.model_dump(),
    )
    return WorkflowOut.model_validate(workflow)


@router.get("", response_model=list[WorkflowOut])
async def list_workflows(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[WorkflowOut]:
    workflows = await WorkflowRepository(session).list_for_owner(
        user.id, limit=limit, offset=offset
    )
    return [WorkflowOut.model_validate(w) for w in workflows]


@router.get("/{workflow_id}", response_model=WorkflowOut)
async def get_workflow(workflow_id: str, user: CurrentUser, session: SessionDep) -> WorkflowOut:
    workflow = await WorkflowRepository(session).get_owned(_parse_id(workflow_id), user.id)
    if workflow is None:
        raise NotFoundError("workflow not found")
    return WorkflowOut.model_validate(workflow)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(workflow_id: str, user: CurrentUser, session: SessionDep) -> Response:
    repo = WorkflowRepository(session)
    workflow = await repo.get_owned(_parse_id(workflow_id), user.id)
    if workflow is None:
        raise NotFoundError("workflow not found")
    await repo.delete(workflow)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{workflow_id}/run", response_model=RunDetailOut)
async def run_workflow(
    workflow_id: str,
    payload: RunRequest,
    user: CurrentUser,
    session: SessionDep,
    service: ServiceDep,
) -> RunDetailOut:
    workflow = await WorkflowRepository(session).get_owned(_parse_id(workflow_id), user.id)
    if workflow is None:
        raise NotFoundError("workflow not found")
    run, result = await service.execute(workflow, trigger="manual", initial=payload.variables)
    return RunDetailOut(
        id=run.id,
        workflow_id=run.workflow_id,
        status=run.status.value,
        trigger=run.trigger,
        variables=run.variables,
        created_at=run.created_at,
        finished_at=run.finished_at,
        steps=[
            StepOut(
                step_id=s.step_id,
                plugin=s.plugin,
                status=s.status.value,
                error=s.error,
                duration_ms=s.duration_ms,
                attempts=s.attempts,
                output=s.output,
            )
            for s in result.steps
        ],
    )


@router.get("/{workflow_id}/runs", response_model=list[RunOut])
async def list_runs(
    workflow_id: str,
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RunOut]:
    workflow = await WorkflowRepository(session).get_owned(_parse_id(workflow_id), user.id)
    if workflow is None:
        raise NotFoundError("workflow not found")
    runs = await RunRepository(session).list_for_owner(user.id, limit=limit, offset=offset)
    return [RunOut.model_validate(r) for r in runs if r.workflow_id == workflow.id]
