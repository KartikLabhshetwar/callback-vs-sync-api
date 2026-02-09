import pytest


@pytest.mark.asyncio
async def test_sync_endpoint(client):
    resp = await client.post("/sync", json={"input_data": "hello", "iterations": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["request_id"]
    assert body["result"]
    assert body["iterations"] == 100
    assert body["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_sync_endpoint_default_iterations(client):
    resp = await client.post("/sync", json={"input_data": "hello"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["iterations"] == 100  # from CONSUMA_DEFAULT_ITERATIONS env


@pytest.mark.asyncio
async def test_sync_endpoint_deterministic(client):
    resp1 = await client.post("/sync", json={"input_data": "test", "iterations": 50})
    resp2 = await client.post("/sync", json={"input_data": "test", "iterations": 50})
    assert resp1.json()["result"] == resp2.json()["result"]


@pytest.mark.asyncio
async def test_sync_endpoint_validation(client):
    resp = await client.post("/sync", json={"input_data": ""})
    assert resp.status_code == 422

    resp = await client.post("/sync", json={"input_data": "x", "iterations": 0})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_sync_result_in_requests(client):
    resp = await client.post("/sync", json={"input_data": "trace-test", "iterations": 50})
    request_id = resp.json()["request_id"]

    detail = await client.get(f"/requests/{request_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == request_id
    assert body["mode"] == "sync"
    assert body["status"] == "completed"
