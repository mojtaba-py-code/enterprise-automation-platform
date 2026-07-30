"""Aggregate all v1 routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import admin, auth, health, plugins, workflows

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(plugins.router)
api_router.include_router(workflows.router)
api_router.include_router(admin.router)
