"""Data-transformation plugins: set variables, validate, and render templates."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.errors import ValidationFailedError
from app.domain.plugins import Plugin, PluginContext
from app.plugins.registry import register


@register
class SetVariablesPlugin(Plugin):
    name = "transform.set"
    category = "transform"
    summary = "Set one or more variables for later steps to consume."

    class Params(BaseModel):
        values: dict[str, Any] = Field(default_factory=dict)

    params_model = Params

    async def run(self, params: BaseModel, context: PluginContext) -> dict[str, Any]:
        assert isinstance(params, SetVariablesPlugin.Params)
        return dict(params.values)


@register
class ValidatePlugin(Plugin):
    name = "transform.validate"
    category = "transform"
    summary = "Assert a value is non-empty (or meets a minimum length)."

    class Params(BaseModel):
        value: Any = None
        min_length: int = Field(default=1, ge=0)

    params_model = Params

    async def run(self, params: BaseModel, context: PluginContext) -> dict[str, Any]:
        assert isinstance(params, ValidatePlugin.Params)
        value = params.value
        length = len(value) if hasattr(value, "__len__") else (0 if value is None else 1)
        if length < params.min_length:
            raise ValidationFailedError(
                f"validation failed: length {length} < required {params.min_length}"
            )
        return {"valid": True, "length": length}


@register
class TemplatePlugin(Plugin):
    name = "transform.template"
    category = "transform"
    summary = "Render a text template using ${...} references to workflow variables."

    class Params(BaseModel):
        template: str = ""

    params_model = Params

    async def run(self, params: BaseModel, context: PluginContext) -> dict[str, Any]:
        assert isinstance(params, TemplatePlugin.Params)
        # ${...} references were already substituted by the engine before validation.
        return {"text": params.template}
