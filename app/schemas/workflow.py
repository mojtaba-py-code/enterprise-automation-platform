"""Workflow, run and plugin schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.workflow import WorkflowDefinition


class PluginOut(BaseModel):
    name: str
    category: str
    summary: str
    enabled: bool
    supports_rollback: bool


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    definition: WorkflowDefinition


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    is_active: bool
    definition: dict[str, Any]
    created_at: datetime


class RunRequest(BaseModel):
    variables: dict[str, Any] = Field(default_factory=dict)


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    step_id: str
    plugin: str
    status: str
    error: str | None
    duration_ms: int
    attempts: int
    output: dict[str, Any]


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workflow_id: uuid.UUID
    status: str
    trigger: str
    variables: dict[str, Any]
    created_at: datetime
    finished_at: datetime | None


class RunDetailOut(RunOut):
    steps: list[StepOut]


class ScheduleRequest(BaseModel):
    kind: Literal["interval", "cron"]
    seconds: int | None = Field(default=None, ge=1)
    cron: str | None = None
