"""Plugin catalogue endpoints (admin can enable/disable)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AdminUser, ContainerDep, CurrentUser
from app.schemas.common import MessageResponse
from app.schemas.workflow import PluginOut

router = APIRouter(prefix="/plugins", tags=["plugins"])


@router.get("", response_model=list[PluginOut])
async def list_plugins(_: CurrentUser, container: ContainerDep) -> list[PluginOut]:
    registry = container.registry
    return [
        PluginOut(
            name=p.name,
            category=p.category,
            summary=p.summary,
            enabled=registry.is_enabled(p.name),
            supports_rollback=p.supports_rollback,
        )
        for p in registry.all()
    ]


@router.post("/{name}/enable", response_model=MessageResponse)
async def enable_plugin(name: str, _: AdminUser, container: ContainerDep) -> MessageResponse:
    container.registry.enable(name)
    return MessageResponse(message=f"plugin '{name}' enabled")


@router.post("/{name}/disable", response_model=MessageResponse)
async def disable_plugin(name: str, _: AdminUser, container: ContainerDep) -> MessageResponse:
    container.registry.disable(name)
    return MessageResponse(message=f"plugin '{name}' disabled")
