import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.callback import SSRFError, validate_callback_url
from app.config import settings
from app.database import insert_request
from app.models import AsyncRequest, AsyncResponse
import app.task_queue as tq_mod

router = APIRouter()


@router.post("/async", response_model=AsyncResponse, status_code=202)
async def async_endpoint(req: AsyncRequest) -> JSONResponse:
    """Asynchronous processing — enqueues work and delivers result via callback.

    Returns 202 Accepted immediately. The result will be POSTed to the
    callback_url when processing completes.
    """
    # SSRF validation
    try:
        validate_callback_url(req.callback_url)
    except SSRFError as e:
        return JSONResponse(status_code=400, content={"detail": f"Invalid callback URL: {e}"})

    request_id = str(uuid.uuid4())
    iterations = req.iterations or settings.default_iterations

    await insert_request(request_id, "async", req.input_data, iterations, req.callback_url)

    # Enqueue to task queue — returns False if queue is full (back-pressure)
    if tq_mod.task_queue is None:
        return JSONResponse(
            status_code=503,
            content={"detail": "Task queue not initialized"},
        )

    enqueued = await tq_mod.task_queue.enqueue(request_id, req.input_data, iterations, req.callback_url)
    if not enqueued:
        return JSONResponse(
            status_code=503,
            content={"detail": "Server overloaded — queue is full"},
            headers={"Retry-After": "5"},
        )

    return JSONResponse(
        status_code=202,
        content=AsyncResponse(
            request_id=request_id,
            status="accepted",
            message="Request accepted. Result will be delivered to callback URL.",
        ).model_dump(),
    )
