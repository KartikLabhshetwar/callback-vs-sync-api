import time
from threading import Lock

from fastapi import FastAPI, Request

app = FastAPI()

# Thread-safe storage for received callbacks
_lock = Lock()
_received: dict[str, float] = {}  # request_id -> received_timestamp (monotonic)
_received_wall: dict[str, float] = {}  # request_id -> wall clock timestamp


@app.post("/callback")
async def receive_callback(request: Request) -> dict:
    body = await request.json()
    request_id = body.get("request_id", "unknown")
    now_mono = time.monotonic()
    now_wall = time.time()
    with _lock:
        _received[request_id] = now_mono
        _received_wall[request_id] = now_wall
    return {"status": "received", "request_id": request_id}


def get_received() -> dict[str, float]:
    with _lock:
        return dict(_received)


def get_received_wall() -> dict[str, float]:
    with _lock:
        return dict(_received_wall)


def clear_received() -> None:
    with _lock:
        _received.clear()
        _received_wall.clear()
