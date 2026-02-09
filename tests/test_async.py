import pytest


@pytest.mark.asyncio
async def test_async_endpoint_accepts(client):
    resp = await client.post("/async", json={
        "input_data": "hello",
        "iterations": 100,
        "callback_url": "http://localhost:9999/callback",
    })
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["request_id"]


@pytest.mark.asyncio
async def test_async_endpoint_validation(client):
    resp = await client.post("/async", json={
        "input_data": "",
        "callback_url": "http://localhost:9999/callback",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_async_request_in_list(client):
    resp = await client.post("/async", json={
        "input_data": "list-test",
        "iterations": 50,
        "callback_url": "http://localhost:9999/callback",
    })
    request_id = resp.json()["request_id"]

    detail = await client.get(f"/requests/{request_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["id"] == request_id
    assert body["mode"] == "async"
