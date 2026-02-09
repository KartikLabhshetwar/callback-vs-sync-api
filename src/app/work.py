import hashlib
import time


def compute_work(input_data: str, iterations: int) -> dict:
    """Run N rounds of SHA-256 hashing.

    Deterministic and CPU-bound. hashlib uses OpenSSL under the hood,
    which releases the GIL during computation — enabling real parallelism
    via asyncio.to_thread().
    """
    start = time.monotonic()
    digest = input_data.encode("utf-8")
    for _ in range(iterations):
        digest = hashlib.sha256(digest).digest()
    elapsed_ms = round((time.monotonic() - start) * 1000, 2)
    return {
        "result": digest.hex(),
        "iterations": iterations,
        "duration_ms": elapsed_ms,
    }
