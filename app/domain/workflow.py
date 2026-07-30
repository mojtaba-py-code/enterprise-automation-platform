"""Workflow definitions, run results, and a safe condition evaluator."""

from __future__ import annotations

import operator
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class OnError(StrEnum):
    STOP = "stop"
    CONTINUE = "continue"
    ROLLBACK = "rollback"


class StepDefinition(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    plugin: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    when: str | None = None  # optional condition, e.g. "read.size > 0"
    on_error: OnError = OnError.STOP
    retries: int | None = Field(default=None, ge=0, le=10)
    timeout: float | None = Field(default=None, gt=0)


class WorkflowDefinition(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    version: int = 1
    steps: list[StepDefinition] = Field(min_length=1)

    def step_ids(self) -> list[str]:
        return [s.id for s in self.steps]


class StepStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


class RunStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


@dataclass(slots=True)
class StepOutcome:
    step_id: str
    plugin: str
    status: StepStatus
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0
    attempts: int = 0


@dataclass(slots=True)
class WorkflowRunResult:
    workflow: str
    status: RunStatus
    steps: list[StepOutcome] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)

    @property
    def failed_step(self) -> StepOutcome | None:
        return next((s for s in self.steps if s.status is StepStatus.FAILED), None)


_COMPARATORS: dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq,
    "!=": operator.ne,
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
}
# Longer operators first so ">=" is matched before ">".
_OPERATORS = ("==", "!=", ">=", "<=", ">", "<")


def evaluate_condition(expression: str, variables: dict[str, Any]) -> bool:
    """Evaluate a restricted ``left OP right`` (or bare truthy) condition.

    Deliberately does NOT use ``eval``: only variable lookups, literals and a
    fixed set of comparison operators are supported, so a workflow definition
    can never execute arbitrary code.
    """
    expr = expression.strip()
    for op in _OPERATORS:
        if op in expr:
            left, right = (part.strip() for part in expr.split(op, 1))
            return _compare(_resolve(left, variables), op, _coerce(right))
    return bool(_resolve(expr, variables))


def _compare(left: Any, op: str, right: Any) -> bool:
    try:
        return bool(_COMPARATORS[op](left, right))
    except TypeError:
        return False


def _resolve(token: str, variables: dict[str, Any]) -> Any:
    literal = _maybe_literal(token)
    if literal is not None or token in ("true", "false", "null"):
        return literal
    current: Any = variables
    for part in token.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _coerce(token: str) -> Any:
    literal = _maybe_literal(token)
    return literal if literal is not None or token in ("true", "false", "null") else token


def _is_quoted(token: str) -> bool:
    return len(token) > 1 and token[0] == token[-1] and token[0] in "\"'"


def _maybe_literal(token: str) -> Any:
    if token in ("true", "false"):
        return token == "true"
    if token == "null" or _is_quoted(token):
        return token[1:-1] if _is_quoted(token) else None
    for converter in (int, float):
        try:
            return converter(token)
        except ValueError:
            continue
    return None
