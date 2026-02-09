# Sync vs Async (Callback) API Under Request Storms

Compare what happens when a server handles requests synchronously (blocking) vs asynchronously (callback-based) under high load.

**Tech stack**: Python, FastAPI, SQLite, asyncio

## How It Works

```
  POST /sync ──> Server does work ──> Returns result (client waits entire time)

  POST /async ──> Server says "got it" (202) ──> Client is free
                       |
                       └──> Background worker does work ──> Calls your callback URL with result
```

**Sync** blocks the event loop. Under load, request #200 waits for all 199 before it.
**Async** returns instantly. Work happens in background threads, results delivered via callback.

## Quick Start

```bash
# 1. Install
uv sync --extra dev
cp .env.example .env

# 2. Start server
uv run uvicorn app.main:app --port 8000

# 3. Run tests (30 tests)
uv run pytest tests/ -v

# 4. Run load test (in a new terminal)
uv run python -m loadgen.cli --num-requests 200 --concurrency 30
```

No Docker, no Redis, no Postgres. Everything runs locally with zero external deps.

## API Endpoints

### POST /sync
Send data, wait for result.
```bash
curl -X POST localhost:8000/sync \
  -H 'Content-Type: application/json' \
  -d '{"input_data": "hello", "iterations": 50000}'
```

### POST /async
Send data + callback URL, get instant 202 back, receive result later at your URL.
```bash
curl -X POST localhost:8000/async \
  -H 'Content-Type: application/json' \
  -d '{"input_data": "hello", "callback_url": "http://localhost:9000/callback", "iterations": 50000}'
```

### GET /requests?mode=sync|async
List recent requests. Filter by mode, paginate with `limit` and `offset`.

### GET /requests/{id}
Full request detail. For async requests, includes `delivery_trace` showing every callback attempt.

### GET /healthz
Server health: queue depth, active workers, DB status, uptime.

## Load Generator

The built-in load tester fires requests at both endpoints and compares:

```bash
uv run python -m loadgen.cli --num-requests 200 --concurrency 30
```

**What it shows:**

| Column | Meaning |
|--------|---------|
| Sync (response) | How long the client waited for each sync request |
| Async (accept) | How fast the server returned 202 (client freed instantly) |
| Async (callback) | Total time until callback arrived (includes queue + work + delivery) |

Options: `--mode sync|async|both`, `--iterations`, `--callback-port`, `--timeout`

## Design Decisions

| What | Choice | Why |
|------|--------|-----|
| "Work" function | SHA-256 hashing (N rounds) | Deterministic, CPU-bound, releases the GIL so threads get real parallelism |
| Database | SQLite + aiosqlite (WAL mode) | Zero deps. Swap for PostgreSQL in production |
| Task queue | asyncio.Queue (bounded) | No Redis needed. Swap for ARQ/Celery in production |
| Async CPU work | `asyncio.to_thread()` | Runs in real OS thread. hashlib releases GIL = actual parallelism |
| Callback retry | Exponential backoff + jitter | Retries at 2s, 4s, 8s, 16s, 32s. Jitter prevents thundering herd |
| SSRF protection | DNS resolve + IP blocklist + no redirects | Blocks private IPs, re-validates at delivery time (DNS rebinding defense) |
| Rate limiting | Sliding window per-IP | Returns 429 + Retry-After. Avoids burst-at-boundary problem |
| Back-pressure | Bounded queue + 503 | Queue full = 503 with Retry-After. Prevents OOM |

## Protection Features

- **SSRF**: Callback URLs validated against private IP ranges, bad schemes blocked, redirects disabled, re-validated at delivery time
- **Rate limiting**: 500 req/60s per IP (configurable). Skips /healthz
- **Back-pressure**: Bounded queue returns 503 when full
- **Input validation**: Max payload 10KB, max callback URL 2048 chars, max iterations 1M
- **Error handling**: Both sync and async paths catch failures, update DB status, deliver error callbacks

## Configuration

All env vars use `CONSUMA_` prefix. Copy `.env.example` to `.env` to configure:

| Variable | Default | What it does |
|----------|---------|-------------|
| `CONSUMA_DEFAULT_ITERATIONS` | 50000 | SHA-256 rounds per request |
| `CONSUMA_MAX_WORKERS` | 4 | Background worker threads |
| `CONSUMA_MAX_QUEUE_SIZE` | 1000 | Queue capacity (503 when full) |
| `CONSUMA_CALLBACK_MAX_RETRIES` | 5 | Retry attempts for failed callbacks |
| `CONSUMA_RATE_LIMIT_REQUESTS` | 500 | Requests per window per IP |
| `CONSUMA_ALLOW_PRIVATE_CALLBACKS` | true | Allow localhost callbacks (disable in production) |

## Testing

```bash
uv run pytest tests/ -v    # 30 tests
```

| Test file | What it covers |
|-----------|---------------|
| `test_work.py` | SHA-256 determinism, output format, timing |
| `test_sync.py` | Sync endpoint correctness, defaults, validation, DB persistence |
| `test_async.py` | 202 acceptance, validation, DB persistence |
| `test_callback.py` | SSRF blocking (private IPs, bad schemes, no hostname) |
| `test_edge_cases.py` | 404s, queue full 503, input boundaries, rate limiting, mode filtering |

## Project Structure

```
src/app/
  main.py            # App setup, lifespan (startup/shutdown), middleware
  config.py          # Env-driven settings (CONSUMA_ prefix)
  work.py            # SHA-256 work function (shared by both paths)
  database.py        # SQLite with WAL mode
  models.py          # Pydantic request/response schemas
  callback.py        # SSRF validation + retry delivery
  task_queue.py      # Bounded queue + worker pool
  rate_limit.py      # Sliding window rate limiter
  routes/
    sync_route.py    # POST /sync
    async_route.py   # POST /async
    requests_route.py # GET /requests, GET /requests/{id}
    health.py        # GET /healthz

loadgen/               # Load test CLI
tests/                 # 30 automated tests
```

## Known Limitations

- **SQLite**: WAL helps but doesn't eliminate write contention under extreme load. Use PostgreSQL in production.
- **In-memory rate limiter**: Per-process only. Use Redis for multi-worker deployments.
- **No callback ordering**: Retries can deliver out-of-order. Timestamps included in payload for client-side ordering.
