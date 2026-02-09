import uuid

from fastapi import APIRouter

from app.config import settings
from app.database import insert_request, update_request_result
from app.models import SyncRequest, SyncResponse
from app.work import compute_work

router = APIRouter()


@router.post("/sync", response_model=SyncResponse)
async def sync_endpoint(req: SyncRequest) -> SyncResponse:
    """Synchronous processing — runs compute_work directly on the event loop.

    This INTENTIONALLY blocks the event loop to demonstrate the
    difference between sync and async handling under load.
    """
    request_id = str(uuid.uuid4())
    iterations = req.iterations or settings.default_iterations

    await insert_request(request_id, "sync", req.input_data, iterations)

    # Intentionally blocking the event loop — this IS the comparison point
    work_result = compute_work(req.input_data, iterations)

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
