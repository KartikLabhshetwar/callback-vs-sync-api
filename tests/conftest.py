import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Use a temp file database for tests (in-memory doesn't survive across connections)
os.environ["CONSUMA_DATABASE_PATH"] = "/tmp/test_requests.db"
os.environ["CONSUMA_ALLOW_PRIVATE_CALLBACKS"] = "true"
os.environ["CONSUMA_DEFAULT_ITERATIONS"] = "100"
os.environ["CONSUMA_MAX_WORKERS"] = "2"
os.environ["CONSUMA_MAX_QUEUE_SIZE"] = "10"
os.environ["CONSUMA_CALLBACK_MAX_RETRIES"] = "2"
os.environ["CONSUMA_RATE_LIMIT_REQUESTS"] = "1000"

from app.database import close_db, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.routes.health import set_start_time  # noqa: E402
from app.task_queue import init_task_queue, task_queue  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def setup_and_teardown():
    """Initialize DB and task queue before each test, clean up after."""
    import app.task_queue as tq_mod

    # Remove old test db
    try:
        os.unlink("/tmp/test_requests.db")
    except FileNotFoundError:
        pass

    set_start_time()
    await init_db()
    queue = init_task_queue()

    yield

    if tq_mod.task_queue is not None:
        await tq_mod.task_queue.shutdown(timeout=5)
        tq_mod.task_queue = None
    await close_db()

    try:
        os.unlink("/tmp/test_requests.db")
    except FileNotFoundError:
        pass


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
