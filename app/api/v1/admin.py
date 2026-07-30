"""Admin dashboard metrics (admin role required)."""

from __future__ import annotations

import psutil
from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import AdminUser, ContainerDep, SessionDep
from app.db.models import User, Workflow, WorkflowRun

router = APIRouter(prefix="/admin", tags=["admin"])


class SystemHealth(BaseModel):
    cpu_percent: float
    memory_percent: float
    disk_percent: float


class DashboardMetrics(BaseModel):
    total_users: int
    total_workflows: int
    total_runs: int
    runs_by_status: dict[str, int]
    plugins: int
    system: SystemHealth


@router.get("/dashboard", response_model=DashboardMetrics)
async def dashboard(_: AdminUser, session: SessionDep, container: ContainerDep) -> DashboardMetrics:
    total_users = await session.scalar(select(func.count()).select_from(User)) or 0
    total_workflows = await session.scalar(select(func.count()).select_from(Workflow)) or 0
    total_runs = await session.scalar(select(func.count()).select_from(WorkflowRun)) or 0

    status_rows = await session.execute(
        select(WorkflowRun.status, func.count()).group_by(WorkflowRun.status)
    )
    runs_by_status = {status.value: count for status, count in status_rows.all()}

    return DashboardMetrics(
        total_users=total_users,
        total_workflows=total_workflows,
        total_runs=total_runs,
        runs_by_status=runs_by_status,
        plugins=len(container.registry.names()),
        system=SystemHealth(
            cpu_percent=psutil.cpu_percent(interval=None),
            memory_percent=psutil.virtual_memory().percent,
            disk_percent=psutil.disk_usage(str(container.settings.workspace_dir)).percent,
        ),
    )
