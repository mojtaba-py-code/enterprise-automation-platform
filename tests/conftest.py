"""Shared test fixtures.

Each test gets an isolated SQLite database and a temporary workspace sandbox,
and talks to the app through a real ASGI client wired to a purpose-built
container — so tests exercise routing, middleware, DI and the DB together.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import update

from app.container import Container
from app.core.config import Settings
from app.db.base import Base
from app.db.models import User, UserRole
from app.main import create_app
from app.plugins import default_registry
from app.plugins.email_plugin import EmailSendPlugin, SinkEmailSender
from app.plugins.http_plugin import HttpRequestPlugin

VALID_PASSWORD = "Sup3rSecret!"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        secret_key="test-secret-key-long-enough-0123456789",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        workspace_dir=tmp_path / "workspace",
        rate_limit_per_minute=10_000,
    )


@pytest.fixture(autouse=True)
def _reset_registry() -> Iterator[None]:
    """Keep the shared plugin registry isolated between tests."""
    yield
    default_registry._disabled.clear()
    http = default_registry.get("http.request")
    assert isinstance(http, HttpRequestPlugin)
    http.transport = None
    email = default_registry.get("email.send")
    assert isinstance(email, EmailSendPlugin)
    email.sender = SinkEmailSender()


@pytest_asyncio.fixture
async def container(settings: Settings) -> AsyncIterator[Container]:
    instance = Container(settings)
    async with instance.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield instance
    await instance.aclose()


@pytest.fixture
def app(container: Container) -> FastAPI:
    return create_app(container.settings, container=container)


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client


async def register_user(client: httpx.AsyncClient, email: str = "user@example.com") -> dict:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": VALID_PASSWORD, "full_name": "Test User"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def login(client: httpx.AsyncClient, email: str = "user@example.com") -> dict:
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": VALID_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def auth_headers(client: httpx.AsyncClient) -> dict[str, str]:
    await register_user(client)
    tokens = await login(client)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest_asyncio.fixture
async def admin_headers(client: httpx.AsyncClient, container: Container) -> dict[str, str]:
    await register_user(client, email="admin@example.com")
    async with container.session_factory() as session:
        await session.execute(
            update(User).where(User.email == "admin@example.com").values(role=UserRole.ADMIN)
        )
        await session.commit()
    tokens = await login(client, email="admin@example.com")
    return {"Authorization": f"Bearer {tokens['access_token']}"}
