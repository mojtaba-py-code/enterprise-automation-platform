"""ORM models.

A user owns workflows; each workflow can be run many times, and every run
records its per-step outcomes. The audit log is an append-only trail of
security-relevant events.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(enum.StrEnum):
    USER = "user"
    ADMIN = "admin"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(200), default=None)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=16), default=UserRole.USER
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    workflows: Mapped[list[Workflow]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )


class Workflow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workflows"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(String(500), default="")
    definition: Mapped[dict[str, Any]] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    owner: Mapped[User] = relationship(back_populates="workflows")
    runs: Mapped[list[WorkflowRun]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )


class RunStatus(enum.StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class WorkflowRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workflow_runs"

    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), index=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True)
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, native_enum=False, length=16), default=RunStatus.RUNNING, index=True
    )
    trigger: Mapped[str] = mapped_column(String(32), default="manual")
    variables: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    workflow: Mapped[Workflow] = relationship(back_populates="runs")
    steps: Mapped[list[StepRun]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="StepRun.position"
    )


class StepRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workflow_step_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    step_id: Mapped[str] = mapped_column(String(64))
    plugin: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    error: Mapped[str | None] = mapped_column(String(1000), default=None)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    output: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    run: Mapped[WorkflowRun] = relationship(back_populates="steps")


class AuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "audit_log"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    detail: Mapped[str] = mapped_column(String(500), default="")
    ip_address: Mapped[str | None] = mapped_column(String(45), default=None)
