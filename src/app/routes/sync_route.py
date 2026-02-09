import logging
import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import insert_request, update_request_result
from app.models import SyncRequest, SyncResponse
from app.work import compute_work

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/sync", response_model=SyncResponse)
async def sync_endpoint(req: SyncRequest) -> SyncResponse | JSONResponse:
    """Synchronous processing — runs compute_work directly on the event loop.

    This INTENTIONALLY blocks the event loop to demonstrate the
    difference between sync and async handling under load.
    """
    request_id = str(uuid.uuid4())
    iterations = req.iterations or settings.default_iterations

    await insert_request(request_id, "sync", req.input_data, iterations)

    try:
        # Intentionally blocking the event loop — this IS the comparison point
        work_result = compute_work(req.input_data, iterations)
    except Exception:
        logger.exception("compute_work failed for request %s", request_id)
        await update_request_result(request_id, "failed", "", 0)
        return JSONResponse(
            status_code=500,
            content={"detail": "Work computation failed", "request_id": request_id},
        )

    await update_request_result(
        request_id, "completed", work_result["result"], work_result["duration_ms"]
    )

    return SyncResponse(
        request_id=request_id,
        status="completed",
        result=work_result["result"],
        iterations=work_result["iterations"],
        duration_ms=work_result["duration_ms"],
    )
