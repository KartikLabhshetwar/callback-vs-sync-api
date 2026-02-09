import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings


class SlidingWindowRateLimiter(BaseHTTPMiddleware):
    """Sliding window rate limiter, per client IP.

    Uses an in-memory dict of request timestamps. Skips /healthz.
    Returns 429 with Retry-After header when limit exceeded.
    """

    def __init__(self, app, max_requests: int | None = None, window_seconds: int | None = None):
        super().__init__(app)
        self.max_requests = max_requests or settings.rate_limit_requests
        self.window_seconds = window_seconds or settings.rate_limit_window
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/healthz":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        cutoff = now - self.window_seconds

        # Slide the window: drop old timestamps
        timestamps = self._requests[client_ip]
        self._requests[client_ip] = [t for t in timestamps if t > cutoff]
        timestamps = self._requests[client_ip]

        if len(timestamps) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - timestamps[0])) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(max(1, retry_after))},
            )

        timestamps.append(now)
        return await call_next(request)

    def cleanup_stale(self) -> int:
        """Remove entries for IPs with no recent requests. Returns count removed."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        stale_keys = [
            ip for ip, timestamps in self._requests.items()
            if not timestamps or all(t <= cutoff for t in timestamps)
        ]
        for key in stale_keys:
            del self._requests[key]
        return len(stale_keys)
