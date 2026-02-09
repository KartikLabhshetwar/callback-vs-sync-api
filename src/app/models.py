from pydantic import BaseModel, Field


class SyncRequest(BaseModel):
    input_data: str = Field(..., min_length=1, max_length=10_000)
    iterations: int | None = Field(None, ge=1, le=1_000_000)


class AsyncRequest(BaseModel):
    input_data: str = Field(..., min_length=1, max_length=10_000)
    callback_url: str = Field(..., min_length=1, max_length=2048)
    iterations: int | None = Field(None, ge=1, le=1_000_000)


class SyncResponse(BaseModel):
    request_id: str
    status: str
    result: str
    iterations: int
    duration_ms: float


class AsyncResponse(BaseModel):
    request_id: str
    status: str
    message: str


class CallbackAttemptDetail(BaseModel):
    attempt_number: int
    status_code: int | None = None
    error: str | None = None
    duration_ms: float | None = None
    created_at: str | None = None


class RequestDetail(BaseModel):
    id: str
    mode: str
    input_data: str
    iterations: int
    status: str
    result: str | None = None
    duration_ms: float | None = None
    callback_url: str | None = None
    callback_status: str | None = None
    callback_attempts: int = 0
    callback_error: str | None = None
    created_at: str | None = None
    completed_at: str | None = None
    delivery_trace: list[CallbackAttemptDetail] = []


class RequestSummary(BaseModel):
    id: str
    mode: str
    status: str
    duration_ms: float | None = None
    created_at: str | None = None


class HealthResponse(BaseModel):
    status: str
    queue_depth: int
    active_workers: int
    db_connected: bool
    uptime_seconds: float
