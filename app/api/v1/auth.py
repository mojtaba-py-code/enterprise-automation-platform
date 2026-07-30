"""Authentication endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import (
    AccessPayload,
    CurrentUser,
    SessionDep,
    enforce_rate_limit,
    get_auth_service,
)
from app.db.models import AuditLog
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.schemas.common import MessageResponse
from app.services.auth_service import AuthService, TokenPair

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(enforce_rate_limit)])

AuthDep = Annotated[AuthService, Depends(get_auth_service)]


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _tokens(pair: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        token_type=pair.token_type,
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, request: Request, session: SessionDep, auth: AuthDep
) -> UserOut:
    user = await auth.register(
        email=payload.email, password=payload.password, full_name=payload.full_name
    )
    session.add(AuditLog(actor_id=user.id, action="user.register", ip_address=_ip(request)))
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, request: Request, session: SessionDep, auth: AuthDep
) -> TokenResponse:
    user = await auth.authenticate(email=payload.email, password=payload.password)
    session.add(AuditLog(actor_id=user.id, action="user.login", ip_address=_ip(request)))
    tokens = auth.issue_tokens(user)
    return _tokens(tokens)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, auth: AuthDep) -> TokenResponse:
    tokens = await auth.refresh(payload.refresh_token)
    return _tokens(tokens)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    payload: LogoutRequest,
    access_payload: AccessPayload,
    request: Request,
    session: SessionDep,
    auth: AuthDep,
) -> MessageResponse:
    await auth.logout(access_payload, payload.refresh_token)
    session.add(
        AuditLog(
            actor_id=uuid.UUID(access_payload["sub"]),
            action="user.logout",
            ip_address=_ip(request),
        )
    )
    return MessageResponse(message="logged out")


@router.get("/me", response_model=UserOut)
async def me(current_user: CurrentUser) -> UserOut:
    return UserOut.model_validate(current_user)
