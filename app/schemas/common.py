"""Shared response schemas."""

from __future__ import annotations

from pydantic import BaseModel


class HealthOut(BaseModel):
    status: str
    version: str


class MessageResponse(BaseModel):
    message: str


class PageInfo(BaseModel):
    limit: int
    offset: int
    count: int
