"""Auth endpoints, validation and token revocation."""

from __future__ import annotations

import httpx

from tests.conftest import VALID_PASSWORD, login, register_user


async def test_register_login_me(client: httpx.AsyncClient) -> None:
    user = await register_user(client)
    assert user["email"] == "user@example.com"
    tokens = await login(client)
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == "user@example.com"


async def test_duplicate_email_conflict(client: httpx.AsyncClient) -> None:
    await register_user(client)
    resp = await client.post(
        "/api/v1/auth/register", json={"email": "user@example.com", "password": VALID_PASSWORD}
    )
    assert resp.status_code == 409
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_weak_password_rejected(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/register", json={"email": "w@example.com", "password": "alllowercase"}
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


async def test_login_wrong_password(client: httpx.AsyncClient) -> None:
    await register_user(client)
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "user@example.com", "password": "WrongPass1"}
    )
    assert resp.status_code == 401


async def test_refresh_rejects_access_token(client: httpx.AsyncClient) -> None:
    await register_user(client)
    tokens = await login(client)
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert resp.status_code == 401


async def test_refresh_issues_new_tokens(client: httpx.AsyncClient) -> None:
    await register_user(client)
    tokens = await login(client)
    resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_logout_revokes_tokens(client: httpx.AsyncClient) -> None:
    await register_user(client)
    tokens = await login(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200

    out = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}, headers=headers
    )
    assert out.status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401
    refresh = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh.status_code == 401


async def test_me_requires_auth(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert resp.status_code == 401
