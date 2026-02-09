from fastapi import APIRouter, HTTPException, Query

from app.database import get_callback_attempts, get_request, list_requests
from app.models import CallbackAttemptDetail, RequestDetail, RequestSummary

router = APIRouter()


@router.get("/requests", response_model=list[RequestSummary])
async def list_all_requests(
    mode: str | None = Query(None, pattern="^(sync|async)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[RequestSummary]:
    rows = await list_requests(mode=mode, limit=limit, offset=offset)
    return [
        RequestSummary(
            id=r["id"],
            mode=r["mode"],
            status=r["status"],
            duration_ms=r["duration_ms"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@router.get("/requests/{request_id}", response_model=RequestDetail)
async def get_request_detail(request_id: str) -> RequestDetail:
    row = await get_request(request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Request not found")

    delivery_trace: list[CallbackAttemptDetail] = []
    if row["mode"] == "async":
        attempts = await get_callback_attempts(request_id)
        delivery_trace = [
            CallbackAttemptDetail(
                attempt_number=a["attempt_number"],
                status_code=a["status_code"],
                error=a["error"],
                duration_ms=a["duration_ms"],
                created_at=a["created_at"],
            )
            for a in attempts
        ]

    return RequestDetail(
        id=row["id"],
        mode=row["mode"],
        input_data=row["input_data"],
        iterations=row["iterations"],
        status=row["status"],
        result=row["result"],
        duration_ms=row["duration_ms"],
        callback_url=row["callback_url"],
        callback_status=row["callback_status"],
        callback_attempts=row["callback_attempts"],
        callback_error=row["callback_error"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
        delivery_trace=delivery_trace,
    )
