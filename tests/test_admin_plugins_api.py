"""Plugin catalogue, admin dashboard, health and error shape."""

from __future__ import annotations

import httpx


async def test_live_and_ready(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/health/live")).json()["status"] == "alive"
    assert (await client.get("/api/v1/health/ready")).json()["status"] == "ready"


async def test_security_headers_and_request_id(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/health/live")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert "X-Request-ID" in resp.headers


async def test_unknown_route_is_problem_json(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/nope")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/problem+json")


async def test_list_plugins_requires_auth(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/plugins")).status_code == 401


async def test_list_plugins(client: httpx.AsyncClient, auth_headers: dict) -> None:
    resp = await client.get("/api/v1/plugins", headers=auth_headers)
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()}
    assert "file.write" in names


async def test_enable_disable_requires_admin(client: httpx.AsyncClient, auth_headers: dict) -> None:
    resp = await client.post("/api/v1/plugins/file.read/disable", headers=auth_headers)
    assert resp.status_code == 403


async def test_admin_can_disable_plugin(client: httpx.AsyncClient, admin_headers: dict) -> None:
    resp = await client.post("/api/v1/plugins/file.read/disable", headers=admin_headers)
    assert resp.status_code == 200
    plugins = await client.get("/api/v1/plugins", headers=admin_headers)
    disabled = next(p for p in plugins.json() if p["name"] == "file.read")
    assert disabled["enabled"] is False


async def test_admin_dashboard(client: httpx.AsyncClient, admin_headers: dict) -> None:
    resp = await client.get("/api/v1/admin/dashboard", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_users"] >= 1
    assert body["plugins"] >= 10
    assert "cpu_percent" in body["system"]


async def test_admin_dashboard_requires_admin(
    client: httpx.AsyncClient, auth_headers: dict
) -> None:
    resp = await client.get("/api/v1/admin/dashboard", headers=auth_headers)
    assert resp.status_code == 403
