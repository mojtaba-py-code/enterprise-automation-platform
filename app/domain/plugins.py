"""Plugin contract.

Every automation capability (file, http, excel, ...) is a plugin implementing
this interface. The engine only ever talks to :class:`Plugin`, so new
capabilities are added without touching the core (Open/Closed principle).

A plugin declares a Pydantic ``params_model`` for its inputs, so parameters are
validated before the plugin ever runs. Filesystem plugins receive a sandboxed
:class:`PluginContext` and must resolve user paths through it.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel

from app.core.errors import ValidationFailedError
from app.core.logging import get_logger

_PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")


class PluginContext:
    """Shared, mutable state for one workflow run.

    ``variables`` accumulates each step's output keyed by step id, which lets a
    later step reference an earlier one via ``${step_id.field}`` templates.
    """

    def __init__(self, *, workspace: Path, variables: dict[str, Any] | None = None) -> None:
        self.workspace = workspace
        self.variables: dict[str, Any] = variables or {}
        self.log = get_logger("plugin")

    # -- path sandboxing ---------------------------------------------------
    def safe_path(self, user_path: str) -> Path:
        """Resolve ``user_path`` and guarantee it stays inside the workspace.

        Prevents path-traversal (``../../etc/passwd``) and absolute escapes.
        """
        root = self.workspace.resolve()
        candidate = (root / user_path).resolve()
        if root != candidate and root not in candidate.parents:
            raise ValidationFailedError(f"path escapes the workspace sandbox: {user_path!r}")
        return candidate

    # -- template resolution ----------------------------------------------
    def resolve(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._resolve_str(value)
        if isinstance(value, dict):
            return {k: self.resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve(v) for v in value]
        return value

    def _resolve_str(self, text: str) -> Any:
        match = _PLACEHOLDER.fullmatch(text.strip())
        if match:
            # The whole string is a single placeholder -> return the raw object.
            return self._lookup(match.group(1).strip())
        return _PLACEHOLDER.sub(lambda m: str(self._lookup(m.group(1).strip())), text)

    def _lookup(self, path: str) -> Any:
        current: Any = self.variables
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                raise ValidationFailedError(f"unknown template reference: ${{{path}}}")
        return current


class Plugin(ABC):
    name: ClassVar[str]
    category: ClassVar[str] = "general"
    summary: ClassVar[str] = ""
    params_model: ClassVar[type[BaseModel]]
    supports_rollback: ClassVar[bool] = False

    @abstractmethod
    async def run(self, params: BaseModel, context: PluginContext) -> dict[str, Any]:
        """Execute the plugin and return its output (merged into the context)."""

    async def compensate(
        self, params: BaseModel, context: PluginContext, output: dict[str, Any]
    ) -> None:
        """Undo a previously successful run (Command pattern). Default: no-op."""
        return None

    def validate_params(self, raw: dict[str, Any]) -> BaseModel:
        try:
            return self.params_model.model_validate(raw)
        except Exception as exc:  # pydantic ValidationError -> uniform 422
            raise ValidationFailedError(
                f"invalid parameters for plugin '{self.name}': {exc}"
            ) from exc
