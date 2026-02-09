# Sync API vs Async (Callback) API Under Request Storms

A Python backend (FastAPI + uv) that compares synchronous vs asynchronous (callback-based) request handling under high load. Demonstrates production patterns: error handling, callback retry logic, SSRF prevention, back-pressure, and graceful shutdown.

## Architecture

```
                         ┌──────────────────────────────────┐
                         │           FastAPI App             │
                         │                                  │
  POST /sync ──────────► │  compute_work() ─── blocks ───► │ ──► Response
                         │  (on event loop)                 │
                         │                                  │
  POST /async ─────────► │  enqueue ──► Task Queue ─────── │ ──► 202 Accepted
                         │              │                   │
                         │              ▼                   │
                         │         Worker Pool              │
                         │    asyncio.to_thread()           │
                         │         compute_work()           │
                         │              │                   │
                         │              ▼                   │
                         │      deliver_callback()          │
                         │    (retry + SSRF guard)          │
                         └──────────────────────────────────┘
                                        │
                                        ▼
                              Callback Receiver
```

**Sync path**: `compute_work()` runs directly on the event loop, intentionally blocking it. Under concurrent load, requests queue up behind each other.

**Async path**: Work is enqueued to a bounded `asyncio.Queue`, processed by workers via `asyncio.to_thread()` (hashlib releases the GIL), and results are delivered via callback with exponential backoff retry.

## Quick Start

```bash
# Install dependencies
uv sync

# Copy and configure environment
cp .env.example .env

# Run the server
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# Run load test (both modes)
uv run python -m loadgen.cli --num-requests 200 --concurrency 30
```

## API Reference

### POST /sync
Synchronous processing. Blocks until complete.

```bash
curl -X POST localhost:8000/sync \
  -H 'Content-Type: application/json' \
  -d '{"input_data": "hello", "iterations": 50000}'
```

### POST /async
Asynchronous processing. Returns 202 immediately, delivers result via callback.

```bash
curl -X POST localhost:8000/async \
  -H 'Content-Type: application/json' \
  -d '{"input_data": "hello", "callback_url": "http://localhost:9000/callback", "iterations": 50000}'
```

### GET /requests
List requests with optional filtering.

```bash
curl "localhost:8000/requests?mode=sync&limit=10"
```

### GET /requests/{id}
Get request detail including callback delivery trace.

### GET /healthz
Health check with queue depth, active workers, and uptime.

## Configuration

All settings use the `CONSUMA_` env prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `CONSUMA_DEFAULT_ITERATIONS` | 50000 | SHA-256 iterations per request |
| `CONSUMA_MAX_WORKERS` | 4 | Async task queue worker count |
| `CONSUMA_MAX_QUEUE_SIZE` | 1000 | Bounded queue size (back-pressure) |
| `CONSUMA_CALLBACK_TIMEOUT` | 10 | Callback delivery timeout (seconds) |
| `CONSUMA_CALLBACK_MAX_RETRIES` | 5 | Max callback delivery attempts |
| `CONSUMA_RATE_LIMIT_REQUESTS` | 100 | Requests per window per IP |
| `CONSUMA_RATE_LIMIT_WINDOW` | 60 | Rate limit window (seconds) |
| `CONSUMA_ALLOW_PRIVATE_CALLBACKS` | false | Allow callbacks to private IPs |
| `CONSUMA_DATABASE_PATH` | requests.db | SQLite database path |

## Load Generator

```bash
uv run python -m loadgen.cli --help
```

Options:
- `--server-url`: API server URL (default: http://localhost:8000)
- `--num-requests`: Total requests (default: 100)
- `--concurrency`: Concurrent requests (default: 20)
- `--mode`: sync, async, or both (default: both)
- `--iterations`: SHA-256 iterations (default: 10000)
- `--callback-port`: Callback receiver port (default: 9000)
- `--timeout`: Request timeout seconds (default: 120)

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Work function | SHA-256 iterations | Deterministic, CPU-bound, GIL-releasing (hashlib/OpenSSL) |
| Database | SQLite + aiosqlite + WAL | Zero external deps. Use PostgreSQL in production |
| Task queue | In-process asyncio.Queue | No Redis needed. Use ARQ/Celery in production |
| CPU work (async) | `asyncio.to_thread()` | hashlib releases GIL = real parallelism |
| Callback retry | Exponential backoff + jitter | Prevents thundering herd |
| SSRF protection | DNS resolve + IP blocklist + no redirects | Multi-layer, re-validates at delivery |
| Rate limiting | Sliding window per-IP | Avoids burst-at-boundary problem |
| Back-pressure | Bounded queue + 503 | Prevents OOM under load |

## Known Limitations

- **SQLite write contention**: WAL mode mitigates but doesn't eliminate under heavy concurrent writes
- **In-memory rate limiter**: Not suitable for multi-process deployment; use Redis in production
- **No callback ordering guarantee**: Retries can cause out-of-order delivery (timestamps included in payload)
- **Mid-delivery data loss**: Tasks in-flight during shutdown may not complete. Document for production

## Testing

```bash
uv run pytest tests/ -v
```

## Project Structure

```
src/app/
  main.py              # FastAPI app, lifespan, middleware
  config.py            # Pydantic Settings (env-driven)
  models.py            # Request/response schemas
  database.py          # aiosqlite CRUD helpers
  work.py              # SHA-256 compute work
  callback.py          # Callback delivery with SSRF guard
  task_queue.py        # Bounded async task queue + workers
  rate_limit.py        # Sliding window rate limiter
  routes/
    sync_route.py      # POST /sync
    async_route.py     # POST /async
    requests_route.py  # GET /requests, GET /requests/{id}
    health.py          # GET /healthz

loadgen/
  cli.py               # Click CLI entrypoint
  runner.py            # Load test orchestrator
  callback_server.py   # Callback receiver
  stats.py             # Percentile computation + report

tests/
  test_sync.py         # Sync endpoint tests
  test_async.py        # Async endpoint tests
  test_callback.py     # SSRF validation tests
  test_work.py         # Work function tests
```
