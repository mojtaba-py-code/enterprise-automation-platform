"""Workflow CRUD, execution and run history over the real API."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import login, register_user

WORKFLOW = {
    "name": "greet",
    "description": "write then read a greeting",
    "definition": {
        "name": "greet",
        "steps": [
            {"id": "vars", "plugin": "transform.set", "params": {"values": {"who": "World"}}},
            {
                "id": "write",
                "plugin": "file.write",
                "params": {"path": "greet.txt", "content": "Hello ${vars.who}"},
            },
            {"id": "read", "plugin": "file.read", "params": {"path": "greet.txt"}},
        ],
    },
}


async def _create(client: httpx.AsyncClient, headers: dict) -> str:
    resp = await client.post("/api/v1/workflows", json=WORKFLOW, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_create_list_get_workflow(client: httpx.AsyncClient, auth_headers: dict) -> None:
    workflow_id = await _create(client, auth_headers)

    listing = await client.get("/api/v1/workflows", headers=auth_headers)
    assert any(w["id"] == workflow_id for w in listing.json())

    got = await client.get(f"/api/v1/workflows/{workflow_id}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["name"] == "greet"


async def test_run_workflow(client: httpx.AsyncClient, auth_headers: dict) -> None:
    workflow_id = await _create(client, auth_headers)
    resp = await client.post(
        f"/api/v1/workflows/{workflow_id}/run", json={"variables": {}}, headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    read_step = next(s for s in body["steps"] if s["step_id"] == "read")
    assert read_step["output"]["content"] == "Hello World"

    runs = await client.get(f"/api/v1/workflows/{workflow_id}/runs", headers=auth_headers)
    assert len(runs.json()) == 1


async def test_create_rejects_unknown_plugin(client: httpx.AsyncClient, auth_headers: dict) -> None:
    bad = {
        "name": "bad",
        "definition": {
            "name": "bad",
            "steps": [{"id": "s", "plugin": "does.not.exist", "params": {}}],
        },
    }
    resp = await client.post("/api/v1/workflows", json=bad, headers=auth_headers)
    assert resp.status_code == 400
    assert resp.json()["code"] == "workflow_error"


async def test_create_rejects_duplicate_step_ids(
    client: httpx.AsyncClient, auth_headers: dict
) -> None:
    bad = {
        "name": "dup",
        "definition": {
            "name": "dup",
            "steps": [
                {"id": "s", "plugin": "transform.set", "params": {}},
                {"id": "s", "plugin": "transform.set", "params": {}},
            ],
        },
    }
    resp = await client.post("/api/v1/workflows", json=bad, headers=auth_headers)
    assert resp.status_code == 400


async def test_delete_workflow(client: httpx.AsyncClient, auth_headers: dict) -> None:
    workflow_id = await _create(client, auth_headers)
    deleted = await client.delete(f"/api/v1/workflows/{workflow_id}", headers=auth_headers)
    assert deleted.status_code == 204
    got = await client.get(f"/api/v1/workflows/{workflow_id}", headers=auth_headers)
    assert got.status_code == 404


async def test_workflow_requires_auth(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/workflows")).status_code == 401


async def test_cannot_access_another_users_workflow(client: httpx.AsyncClient) -> None:
    await register_user(client, email="owner@example.com")
    owner = await login(client, email="owner@example.com")
    owner_h = {"Authorization": f"Bearer {owner['access_token']}"}
    workflow_id = await _create(client, owner_h)

    await register_user(client, email="intruder@example.com")
    intruder = await login(client, email="intruder@example.com")
    intruder_h = {"Authorization": f"Bearer {intruder['access_token']}"}

    resp = await client.get(f"/api/v1/workflows/{workflow_id}", headers=intruder_h)
    assert resp.status_code == 404  # not leaked as 403


@pytest.mark.parametrize("workflow_id", ["not-a-uuid", "00000000-0000-0000-0000-000000000000"])
async def test_get_missing_workflow(
    client: httpx.AsyncClient, auth_headers: dict, workflow_id: str
) -> None:
    resp = await client.get(f"/api/v1/workflows/{workflow_id}", headers=auth_headers)
    assert resp.status_code == 404
