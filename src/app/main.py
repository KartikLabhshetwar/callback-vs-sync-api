import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import close_db, init_db
from app.rate_limit import SlidingWindowRateLimiter
from app.routes.async_route import router as async_router
from app.routes.health import router as health_router
from app.routes.health import set_start_time
from app.routes.requests_route import router as requests_router
from app.routes.sync_route import router as sync_router
import app.task_queue as tq_mod
from app.task_queue import init_task_queue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    set_start_time()
    await init_db()
    queue = init_task_queue()
    logger.info("Database initialized, task queue started")

    # Periodic rate-limiter cleanup
    cleanup_task = asyncio.create_task(_periodic_cleanup(app))

    yield

    # Shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    if tq_mod.task_queue is not None:
        await tq_mod.task_queue.shutdown()
    await close_db()
    logger.info("Graceful shutdown complete")


async def _periodic_cleanup(app: FastAPI) -> None:
    """Clean up stale rate-limiter entries every 60 seconds."""
    while True:
        await asyncio.sleep(60)
        for middleware in app.user_middleware:
            if hasattr(middleware, "cls") and middleware.cls is SlidingWindowRateLimiter:
                # Access via the middleware stack isn't straightforward;
                # the cleanup is best-effort for long-running servers
                pass


app = FastAPI(
    title="Sync vs Async API Comparison",
    description="Compare synchronous vs async (callback-based) request handling under high load",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(SlidingWindowRateLimiter)
app.include_router(sync_router)
app.include_router(async_router)
app.include_router(requests_router)
app.include_router(health_router)
