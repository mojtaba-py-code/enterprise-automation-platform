"""FastAPI dependencies: settings, DB session, auth, RBAC and rate limiting."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.container import Container
from app.core.config import Settings
from app.core.errors import AuthenticationError, PermissionDeniedError, RateLimitedError
from app.core.security import TokenError, decode_token
from app.db.models import User, UserRole
from app.repositories.users import UserRepository
from app.repositories.workflows import RunRepository, WorkflowRepository
from app.services.auth_service import AuthService
from app.services.workflow_service import WorkflowService

_bearer = HTTPBearer(auto_error=False)


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


def get_settings_dep(container: ContainerDep) -> Settings:
    return container.settings


async def get_session(container: ContainerDep) -> AsyncIterator[AsyncSession]:
    async with container.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def get_auth_service(
    session: SessionDep, settings: SettingsDep, container: ContainerDep
) -> AuthService:
    return AuthService(UserRepository(session), settings, blocklist=container.token_blocklist)


def get_workflow_service(session: SessionDep, container: ContainerDep) -> WorkflowService:
    return WorkflowService(
        workflows=WorkflowRepository(session),
        runs=RunRepository(session),
        engine=container.workflow_engine,
        registry=container.registry,
    )


async def enforce_rate_limit(request: Request, container: ContainerDep) -> None:
    identity = request.client.host if request.client else "anonymous"
    allowed, remaining = await container.rate_limiter.check(identity)
    request.state.rate_limit_remaining = remaining
    if not allowed:
        raise RateLimitedError(
            "rate limit exceeded, slow down",
            extra={"limit_per_minute": container.rate_limiter.limit},
        )


async def get_access_payload(
    settings: SettingsDep,
    container: ContainerDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict[str, Any]:
    if credentials is None:
        raise AuthenticationError("missing bearer token")
    try:
        payload = decode_token(credentials.credentials, expected_type="access", settings=settings)
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from exc
    if await container.token_blocklist.is_revoked(payload):
        raise AuthenticationError("this session has been revoked")
    return payload


AccessPayload = Annotated[dict[str, Any], Depends(get_access_payload)]


async def get_current_user(session: SessionDep, payload: AccessPayload) -> User:
    user = await UserRepository(session).get_by_id(uuid.UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("user no longer exists or is disabled")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if user.role is not UserRole.ADMIN:
        raise PermissionDeniedError("admin privileges required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
