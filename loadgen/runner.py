import asyncio
import time

import httpx

from loadgen.callback_server import clear_received, get_received_wall


async def run_sync_test(
    server_url: str,
    num_requests: int,
    concurrency: int,
    iterations: int,
    timeout: float,
) -> tuple[list[float], int]:
    """Fire N sync requests with bounded concurrency. Returns (latencies_ms, error_count)."""
    semaphore = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    errors = 0
    lock = asyncio.Lock()

    async def send_one(i: int, client: httpx.AsyncClient) -> None:
        nonlocal errors
        async with semaphore:
            start = time.monotonic()
            try:
                resp = await client.post(
                    f"{server_url}/sync",
                    json={"input_data": f"test-sync-{i}", "iterations": iterations},
                    timeout=timeout,
                )
                elapsed = round((time.monotonic() - start) * 1000, 2)
                if resp.status_code == 200:
                    async with lock:
                        latencies.append(elapsed)
                else:
                    async with lock:
                        errors += 1
            except Exception:
                async with lock:
                    errors += 1

    async with httpx.AsyncClient() as client:
        tasks = [send_one(i, client) for i in range(num_requests)]
        await asyncio.gather(*tasks)

    return latencies, errors


async def run_async_test(
    server_url: str,
    num_requests: int,
    concurrency: int,
    iterations: int,
    callback_url: str,
    timeout: float,
    callback_wait: float = 60.0,
) -> tuple[list[float], list[float], int, int]:
    """Fire N async requests and wait for callbacks.

    Returns (accept_latencies_ms, callback_latencies_ms, error_count, missing_callbacks).
    """
    clear_received()
    semaphore = asyncio.Semaphore(concurrency)
    accept_latencies: list[float] = []
    send_times: dict[str, float] = {}  # request_id -> wall clock send time
    errors = 0
    lock = asyncio.Lock()

    async def send_one(i: int, client: httpx.AsyncClient) -> None:
        nonlocal errors
        async with semaphore:
            send_wall = time.time()
            start = time.monotonic()
            try:
                resp = await client.post(
                    f"{server_url}/async",
                    json={
                        "input_data": f"test-async-{i}",
                        "iterations": iterations,
                        "callback_url": callback_url,
                    },
                    timeout=timeout,
                )
                elapsed = round((time.monotonic() - start) * 1000, 2)
                if resp.status_code == 202:
                    body = resp.json()
                    request_id = body["request_id"]
                    async with lock:
                        accept_latencies.append(elapsed)
                        send_times[request_id] = send_wall
                else:
                    async with lock:
                        errors += 1
            except Exception:
                async with lock:
                    errors += 1

    async with httpx.AsyncClient() as client:
        tasks = [send_one(i, client) for i in range(num_requests)]
        await asyncio.gather(*tasks)

    # Wait for callbacks to arrive
    expected = len(send_times)
    if expected > 0:
        deadline = time.monotonic() + callback_wait
        while time.monotonic() < deadline:
            received = get_received_wall()
            if len(received) >= expected:
                break
            await asyncio.sleep(0.1)

    # Compute callback latencies (wall clock: send_time -> callback_received_time)
    received = get_received_wall()
    callback_latencies: list[float] = []
    missing = 0
    for request_id, send_time in send_times.items():
        if request_id in received:
            cb_latency = round((received[request_id] - send_time) * 1000, 2)
            callback_latencies.append(cb_latency)
        else:
            missing += 1

    return accept_latencies, callback_latencies, errors, missing
