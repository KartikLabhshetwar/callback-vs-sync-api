import time

from fastapi import APIRouter

from app.models import HealthResponse

router = APIRouter()

_start_time: float = 0.0


def set_start_time() -> None:
    global _start_time
    _start_time = time.monotonic()


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    from app.database import get_db
    import app.task_queue as tq_mod

    db_connected = False
    try:
        db = await get_db()
        await db.execute("SELECT 1")
        db_connected = True
    except Exception:
        pass

    return HealthResponse(
        status="ok" if db_connected else "degraded",
        queue_depth=tq_mod.task_queue.queue_depth if tq_mod.task_queue else 0,
        active_workers=tq_mod.task_queue.active_workers if tq_mod.task_queue else 0,
        db_connected=db_connected,
        uptime_seconds=round(time.monotonic() - _start_time, 2),
    )
