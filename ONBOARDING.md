# Onboarding & Learning Guide

This document walks you through the entire project — what it does, how to run it, how to test every feature, and what to understand for interviews/reviews.

---

## 1. What This Project Proves

This project answers one question: **What happens to a web server when you process requests synchronously vs asynchronously under high concurrent load?**

| Sync Path | Async Path |
|-----------|------------|
| Blocks the event loop | Returns 202 instantly |
| Request N waits for N-1 to finish | All requests accepted in parallel |
| Latency grows linearly with load | Accept latency stays flat |
| Simple to implement | Requires queue, workers, callbacks |

The "work" is configurable SHA-256 hashing — CPU-bound, deterministic, and GIL-releasing (so `asyncio.to_thread()` gives real parallelism).

---

## 2. Prerequisites

```bash
# You need Python 3.12+ and uv (the fast Python package manager)
# Install uv if you don't have it:
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify
uv --version
python3 --version   # should be 3.12+
```

---

## 3. Setup (30 seconds)

```bash
cd callback-vs-sync-api

# Install all dependencies (including dev)
uv sync --extra dev

# Copy env file
cp .env.example .env

# IMPORTANT: For local testing, .env already has:
# CONSUMA_ALLOW_PRIVATE_CALLBACKS=true
# This lets callbacks reach localhost. In production this would be false.
```

That's it. No Docker, no Redis, no Postgres — everything is self-contained.

---

## 4. Run the Server

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

You should see:
```
INFO:     Database initialized, task queue started
INFO:     Started 4 queue workers
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Leave this terminal open. Open a **new terminal** for the commands below.

---

## 5. Test Every Feature Manually

### 5.1 Health Check

```bash
curl -s http://localhost:8000/healthz | python3 -m json.tool
```

Expected:
```json
{
    "status": "ok",
    "queue_depth": 0,
    "active_workers": 0,
    "db_connected": true,
    "uptime_seconds": 5.23
}
```

### 5.2 Sync Endpoint

```bash
curl -s -X POST http://localhost:8000/sync \
  -H 'Content-Type: application/json' \
  -d '{"input_data": "hello", "iterations": 50000}' | python3 -m json.tool
```

Expected: Full result returned inline. Note the `duration_ms` — this is how long the event loop was blocked.

### 5.3 Async Endpoint

First, start a callback receiver in a **second new terminal**:

```bash
# Terminal 2: Start the callback receiver
uv run uvicorn loadgen.callback_server:app --port 9000
```

Now send the async request:

```bash
# Terminal 3: Send async request
curl -s -X POST http://localhost:8000/async \
  -H 'Content-Type: application/json' \
  -d '{"input_data": "hello", "callback_url": "http://localhost:9000/callback", "iterations": 50000}' | python3 -m json.tool
```

Expected: **202 Accepted** returned instantly (< 5ms). Then check the callback receiver terminal — you should see the POST arrive with the result.

### 5.4 Request Tracing

```bash
# List all requests
curl -s "http://localhost:8000/requests?limit=5" | python3 -m json.tool

# Get detail for a specific request (use an ID from above)
curl -s "http://localhost:8000/requests/<request-id>" | python3 -m json.tool
```

The detail view for async requests includes a `delivery_trace` array showing every callback attempt.

### 5.5 SSRF Protection

```bash
# This should be REJECTED (private IP, if allow_private_callbacks=false)
# First, edit .env and set CONSUMA_ALLOW_PRIVATE_CALLBACKS=false, restart server

curl -s -X POST http://localhost:8000/async \
  -H 'Content-Type: application/json' \
  -d '{"input_data": "test", "callback_url": "http://127.0.0.1:22/evil"}' | python3 -m json.tool
```

Expected: `400 Bad Request` with SSRF error message.

```bash
# These always fail regardless of config:
curl -s -X POST http://localhost:8000/async \
  -H 'Content-Type: application/json' \
  -d '{"input_data": "test", "callback_url": "ftp://example.com/callback"}' | python3 -m json.tool
```

Expected: `400` — only http/https schemes allowed.

### 5.6 Rate Limiting

```bash
# Send 101+ requests rapidly (default limit is 100/60s)
for i in $(seq 1 105); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/healthz)
  echo "Request $i: $STATUS"
done
```

You should see `200` for the first 100, then `429 Too Many Requests` with a `Retry-After` header.

### 5.7 Queue Back-Pressure

```bash
# Edit .env: CONSUMA_MAX_QUEUE_SIZE=3, restart server
# Then fire 10 async requests simultaneously:
for i in $(seq 1 10); do
  curl -s -X POST http://localhost:8000/async \
    -H 'Content-Type: application/json' \
    -d "{\"input_data\": \"pressure-$i\", \"callback_url\": \"http://localhost:9000/callback\"}" &
done
wait
```

Some should return `503 Service Unavailable` with `Retry-After: 5` header.

---

## 6. Run the Automated Tests

```bash
uv run pytest tests/ -v
```

Expected: **16 tests, all passing.**

| Test File | What It Covers |
|-----------|----------------|
| `test_work.py` | SHA-256 determinism, hex output, timing |
| `test_sync.py` | Sync endpoint correctness, defaults, validation, DB persistence |
| `test_async.py` | Async 202 acceptance, validation, DB persistence |
| `test_callback.py` | SSRF blocking (private IPs, bad schemes, no hostname), allow-private config |

---

## 7. Run the Load Test (The Fun Part)

Make sure the server is running on port 8000, then:

```bash
# Both sync and async, 200 requests, 30 concurrent
uv run python -m loadgen.cli --num-requests 200 --concurrency 30 --iterations 10000

# Sync only
uv run python -m loadgen.cli --mode sync --num-requests 200 --concurrency 30

# Async only
uv run python -m loadgen.cli --mode async --num-requests 200 --concurrency 30
```

The load generator:
1. Starts a callback receiver on port 9000
2. Fires N requests with bounded concurrency
3. For async: waits for all callbacks to arrive
4. Prints a rich table comparing p50/p95/p99/max latencies

**What you should see**: Sync p95/p99 latencies will be dramatically higher than async accept latencies. The async "time-to-callback" will be similar to sync (work still takes time), but the server remains responsive throughout.

---

## 8. Understanding the Code — File by File

Read these in order for the clearest learning path:

### Layer 1: Foundation
| File | What to Learn |
|------|---------------|
| `src/app/config.py` | Pydantic Settings pattern — type-safe env config with prefix |
| `src/app/work.py` | The "work" function. Note: `hashlib.sha256()` releases the GIL |
| `src/app/database.py` | aiosqlite pattern: global connection, WAL mode, CRUD helpers |
| `src/app/models.py` | Pydantic models for request validation + response serialization |

### Layer 2: Request Handling
| File | What to Learn |
|------|---------------|
| `src/app/routes/sync_route.py` | The sync path — **intentionally** calls `compute_work()` directly, blocking the event loop |
| `src/app/routes/async_route.py` | The async path — validates, enqueues, returns 202. Note the `tq_mod.task_queue` pattern (module-level globals gotcha) |
| `src/app/routes/requests_route.py` | Query endpoints with pagination + delivery trace |
| `src/app/routes/health.py` | Health endpoint exposing internal state |

### Layer 3: Async Internals
| File | What to Learn |
|------|---------------|
| `src/app/task_queue.py` | `asyncio.Queue` + worker pool pattern. **Key insight**: `asyncio.to_thread()` is what makes this work — hashlib releases the GIL so threads get real parallelism |
| `src/app/callback.py` | SSRF validation (DNS resolve + IP blocklist), exponential backoff with jitter, delivery logging |
| `src/app/rate_limit.py` | Sliding window rate limiter as Starlette middleware |

### Layer 4: Orchestration
| File | What to Learn |
|------|---------------|
| `src/app/main.py` | FastAPI lifespan pattern — startup (DB + queue) and graceful shutdown (drain queue, close DB) |

---

## 9. Key Concepts to Understand (Interview-Ready)

### Why does sync degrade under load?
FastAPI runs on an async event loop (uvicorn/asyncio). When `compute_work()` runs directly on the event loop, it blocks everything — no other request can be processed until it finishes. With 50 concurrent requests, request #50 waits for all 49 before it.

### Why does async stay responsive?
The async endpoint returns 202 immediately (just a DB insert + queue push). The actual work happens in a thread pool via `asyncio.to_thread()`. The event loop is never blocked, so it can accept new requests while work runs in background threads.

### Why `asyncio.to_thread()` and not just `await compute_work()`?
`compute_work()` is CPU-bound. Making it `async` and `await`-ing it would still block the event loop — `async` doesn't mean parallel, it means cooperative multitasking. `to_thread()` runs it in a real OS thread, and because hashlib releases the GIL, you get actual parallelism.

### What is SSRF and why do we protect against it?
SSRF (Server-Side Request Forgery) — an attacker sends `callback_url=http://169.254.169.254/metadata` (cloud metadata service) or `http://internal-service:8080/admin`. Our protection:
1. Resolve DNS to get the actual IP
2. Check IP against private network ranges
3. Block non-http/https schemes
4. Disable redirect following (prevents SSRF via redirect)
5. Re-validate at delivery time (prevents DNS rebinding)

### What is back-pressure?
When the queue is full, we return 503 + `Retry-After` instead of accepting more work. This prevents OOM and lets the client know to slow down. Without it, an unbounded queue would eat all memory under sustained load.

### Why exponential backoff with jitter?
If 1000 callbacks fail simultaneously and all retry at exactly 2s, you get a "thundering herd" — 1000 retries hitting at the same instant. Jitter (random ±25%) spreads retries across time.

### Why sliding window rate limiting?
Fixed window rate limiting has a burst problem: you can send 100 requests at second 59, then 100 more at second 61 (200 in 2 seconds). Sliding window tracks actual timestamps, so the limit is enforced smoothly.

---

## 10. What's Production vs Demo

| Feature | This Project | Production |
|---------|-------------|------------|
| Database | SQLite + aiosqlite | PostgreSQL + asyncpg |
| Task queue | In-process asyncio.Queue | Redis + ARQ / RabbitMQ + Celery |
| Rate limiter | In-memory dict | Redis sliding window |
| Deployment | Single process | Multi-worker (gunicorn + uvicorn workers) |
| SSRF protection | Full | Same + WAF rules |
| Monitoring | /healthz endpoint | Prometheus + Grafana |
| Secrets | .env file | Vault / cloud secrets manager |

---

## 11. Quick Reference Commands

```bash
# Install deps
uv sync --extra dev

# Run server
uv run uvicorn app.main:app --port 8000 --reload

# Run tests
uv run pytest tests/ -v

# Run load test
uv run python -m loadgen.cli --num-requests 200 --concurrency 30

# Lint
uv run ruff check src/ tests/ loadgen/

# Format
uv run ruff format src/ tests/ loadgen/
```

---

## 12. Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: app` | Run with `uv run` (it sets up the venv), not bare `python` |
| Async callbacks failing | Make sure `CONSUMA_ALLOW_PRIVATE_CALLBACKS=true` in `.env` for local dev |
| `Database not initialized` | The server's lifespan didn't run. Are you using `uvicorn app.main:app`? |
| Rate limited during testing | Set `CONSUMA_RATE_LIMIT_REQUESTS=10000` in `.env` |
| Load test shows 0 callbacks | Make sure the callback server is reachable on the configured port |
