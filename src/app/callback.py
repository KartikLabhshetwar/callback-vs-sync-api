import ipaddress
import logging
import random
import socket
import time
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.database import insert_callback_attempt, update_callback_status

logger = logging.getLogger(__name__)

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


class SSRFError(Exception):
    pass


def _is_private_ip(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # treat unparseable as private (safe default)
    return any(addr in net for net in _PRIVATE_NETWORKS)


def validate_callback_url(url: str) -> None:
    """Validate callback URL scheme and resolve DNS to check for private IPs.

    Raises SSRFError if the URL targets a private/internal address.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFError(f"Invalid scheme: {parsed.scheme}. Only http/https allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("No hostname in callback URL")

    # Resolve DNS and check all addresses
    try:
        results = socket.getaddrinfo(hostname, parsed.port or 80, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise SSRFError(f"DNS resolution failed for {hostname}: {e}")

    if not settings.allow_private_callbacks:
        for family, _type, _proto, _canonname, sockaddr in results:
            ip = sockaddr[0]
            if _is_private_ip(ip):
                raise SSRFError(
                    f"Callback URL resolves to private IP {ip}. "
                    "Set CONSUMA_ALLOW_PRIVATE_CALLBACKS=true for local testing."
                )


def _revalidate_at_delivery_time(url: str) -> None:
    """Re-validate callback URL at delivery time (DNS rebinding protection)."""
    validate_callback_url(url)


async def deliver_callback(
    request_id: str,
    callback_url: str,
    payload: dict,
) -> None:
    """Deliver callback with exponential backoff + jitter.

    Retries up to callback_max_retries times. Logs every attempt to the
    callback_attempts table. Does NOT retry SSRF failures (permanent fail).
    """
    max_retries = settings.callback_max_retries
    base_delay = 2.0
    max_delay = 60.0

    for attempt in range(1, max_retries + 1):
        start = time.monotonic()
        status_code = None
        error_msg = None

        try:
            # Re-validate at delivery time (DNS rebinding protection)
            _revalidate_at_delivery_time(callback_url)
        except SSRFError as e:
            error_msg = f"SSRF blocked: {e}"
            elapsed_ms = round((time.monotonic() - start) * 1000, 2)
            await insert_callback_attempt(request_id, attempt, None, error_msg, elapsed_ms)
            await update_callback_status(request_id, "failed", attempt, error_msg)
            logger.warning("SSRF blocked for request %s: %s", request_id, e)
            return  # permanent fail — do not retry

        try:
            async with httpx.AsyncClient(
                timeout=settings.callback_timeout,
                follow_redirects=False,  # prevent SSRF via redirect
            ) as client:
                response = await client.post(
                    callback_url,
                    json=payload,
                    headers={
                        "X-Request-ID": request_id,
                        "X-Attempt-Number": str(attempt),
                        "Content-Type": "application/json",
                    },
                )
                status_code = response.status_code
                elapsed_ms = round((time.monotonic() - start) * 1000, 2)

                if 200 <= status_code < 300:
                    await insert_callback_attempt(
                        request_id, attempt, status_code, None, elapsed_ms
                    )
                    await update_callback_status(request_id, "delivered", attempt)
                    logger.info(
                        "Callback delivered for %s on attempt %d (%dms)",
                        request_id, attempt, elapsed_ms,
                    )
                    return
                else:
                    error_msg = f"HTTP {status_code}"

        except httpx.TimeoutException:
            error_msg = "Timeout"
        except httpx.RequestError as e:
            error_msg = f"Connection error: {e}"
        except Exception as e:
            error_msg = f"Unexpected error: {e}"

        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        await insert_callback_attempt(request_id, attempt, status_code, error_msg, elapsed_ms)
        logger.warning(
            "Callback attempt %d/%d failed for %s: %s",
            attempt, max_retries, request_id, error_msg,
        )

        if attempt < max_retries:
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            jitter = delay * 0.25 * (2 * random.random() - 1)  # ±25%
            await _sleep(delay + jitter)

    # All retries exhausted
    await update_callback_status(
        request_id, "failed", max_retries, f"All {max_retries} attempts failed"
    )
    logger.error("Callback delivery failed for %s after %d attempts", request_id, max_retries)


async def _sleep(seconds: float) -> None:
    """Wrapper for asyncio.sleep to allow test patching."""
    import asyncio
    await asyncio.sleep(seconds)
