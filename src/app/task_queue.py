import asyncio
import logging

from app.callback import deliver_callback
from app.config import settings
from app.database import update_request_result
from app.work import compute_work

logger = logging.getLogger(__name__)

task_queue: "AsyncTaskQueue | None" = None


class AsyncTaskQueue:
    """Bounded async task queue with worker pool.

    Workers pull tasks from an asyncio.Queue, run compute_work via
    asyncio.to_thread() (critical: don't block event loop), update the
    DB, and deliver the callback.
    """

    def __init__(self, max_size: int, num_workers: int) -> None:
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self._num_workers = num_workers
        self._workers: list[asyncio.Task] = []
        self._shutdown_event = asyncio.Event()
        self._active_count = 0

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    @property
    def active_workers(self) -> int:
        return self._active_count

    def start(self) -> None:
        for i in range(self._num_workers):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)
        logger.info("Started %d queue workers", self._num_workers)

    async def enqueue(self, request_id: str, input_data: str, iterations: int, callback_url: str) -> bool:
        """Enqueue a task. Returns False if the queue is full (back-pressure)."""
        try:
            self._queue.put_nowait((request_id, input_data, iterations, callback_url))
            return True
        except asyncio.QueueFull:
            return False

    async def _worker(self, worker_id: int) -> None:
        logger.info("Worker %d started", worker_id)
        while not self._shutdown_event.is_set():
            try:
                request_id, input_data, iterations, callback_url = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue

            self._active_count += 1
            try:
                await self._process_task(worker_id, request_id, input_data, iterations, callback_url)
            finally:
                self._active_count -= 1
                self._queue.task_done()

        logger.info("Worker %d stopped", worker_id)

    async def _process_task(
        self, worker_id: int, request_id: str, input_data: str, iterations: int, callback_url: str
    ) -> None:
        """Process a single task: compute work, update DB, deliver callback."""
        # --- Step 1: Compute work ---
        try:
            work_result = await asyncio.to_thread(compute_work, input_data, iterations)
        except Exception:
            logger.exception("Worker %d: compute_work failed for %s", worker_id, request_id)
            await self._handle_failure(request_id, callback_url, "Work computation failed")
            return

        # --- Step 2: Update DB ---
        try:
            await update_request_result(
                request_id, "completed", work_result["result"], work_result["duration_ms"]
            )
        except Exception:
            logger.exception("Worker %d: DB update failed for %s", worker_id, request_id)
            # Still deliver callback — the work was done, even if DB is inconsistent

        # --- Step 3: Deliver callback ---
        payload = {
            "request_id": request_id,
            "status": "completed",
            "result": work_result["result"],
            "iterations": work_result["iterations"],
            "duration_ms": work_result["duration_ms"],
        }
        await deliver_callback(request_id, callback_url, payload)

    async def _handle_failure(self, request_id: str, callback_url: str, error_msg: str) -> None:
        """Update DB to failed and deliver error callback."""
        try:
            await update_request_result(request_id, "failed", "", 0)
        except Exception:
            logger.exception("Failed to update error status for %s", request_id)

        # Deliver error callback so the client knows about the failure
        error_payload = {
            "request_id": request_id,
            "status": "failed",
            "error": error_msg,
        }
        try:
            await deliver_callback(request_id, callback_url, error_payload)
        except Exception:
            logger.exception("Failed to deliver error callback for %s", request_id)

    async def shutdown(self, timeout: float = 30.0) -> None:
        """Graceful shutdown: signal workers, drain queue, cancel stragglers."""
        logger.info("Shutting down task queue...")
        self._shutdown_event.set()

        # Wait for queue to drain
        try:
            await asyncio.wait_for(self._queue.join(), timeout=timeout)
            logger.info("Queue drained successfully")
        except asyncio.TimeoutError:
            logger.warning("Queue drain timed out after %.1fs", timeout)

        # Cancel workers
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        logger.info("All workers stopped")


def init_task_queue() -> AsyncTaskQueue:
    global task_queue
    task_queue = AsyncTaskQueue(
        max_size=settings.max_queue_size,
        num_workers=settings.max_workers,
    )
    task_queue.start()
    return task_queue
