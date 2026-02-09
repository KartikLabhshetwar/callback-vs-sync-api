import asyncio
import threading
from collections import Counter

import click
import uvicorn
from rich.console import Console

from loadgen.callback_server import app as callback_app
from loadgen.runner import run_async_test, run_sync_test
from loadgen.stats import compute_percentiles, print_report


def _start_callback_server(port: int) -> threading.Thread:
    """Start the callback server in a background thread."""
    config = uvicorn.Config(callback_app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return thread


@click.command()
@click.option("--server-url", default="http://localhost:8000", help="Base URL of the API server")
@click.option("--num-requests", default=100, help="Number of requests to send")
@click.option("--concurrency", default=20, help="Max concurrent requests")
@click.option("--mode", type=click.Choice(["sync", "async", "both"]), default="both", help="Test mode")
@click.option("--iterations", default=10000, help="SHA-256 iterations per request")
@click.option("--callback-port", default=9000, help="Port for callback receiver server")
@click.option("--timeout", default=120.0, help="Request timeout in seconds")
def main(
    server_url: str,
    num_requests: int,
    concurrency: int,
    mode: str,
    iterations: int,
    callback_port: int,
    timeout: float,
) -> None:
    """Load test runner for sync vs async API comparison."""
    console = Console()
    console.rule("[bold]Sync vs Async Load Test[/bold]")
    console.print(f"Server: {server_url}")
    console.print(f"Requests: {num_requests}, Concurrency: {concurrency}")
    console.print(f"Iterations: {iterations}, Mode: {mode}")
    console.print()

    # Start callback server if needed
    if mode in ("async", "both"):
        console.print(f"Starting callback server on port {callback_port}...")
        _start_callback_server(callback_port)
        import time
        time.sleep(1)  # give it a moment to start

    callback_url = f"http://localhost:{callback_port}/callback"

    sync_stats = None
    async_accept_stats = None
    async_callback_stats = None
    sync_errors = 0
    async_errors = 0
    missing_callbacks = 0
    all_error_details: Counter = Counter()

    if mode in ("sync", "both"):
        console.print("[bold red]Running sync test...[/bold red]")
        latencies, sync_errors, sync_err_details = asyncio.run(
            run_sync_test(server_url, num_requests, concurrency, iterations, timeout)
        )
        all_error_details.update(sync_err_details)
        sync_stats = compute_percentiles(latencies)
        console.print(f"  Done: {len(latencies)} successful, {sync_errors} errors")
        if sync_err_details:
            for err, count in sync_err_details.most_common():
                console.print(f"    [dim]{count}x {err}[/dim]")

    if mode in ("async", "both"):
        console.print("[bold green]Running async test...[/bold green]")
        accept_lat, cb_lat, async_errors, missing_callbacks, async_err_details = asyncio.run(
            run_async_test(
                server_url, num_requests, concurrency, iterations, callback_url, timeout
            )
        )
        all_error_details.update(async_err_details)
        async_accept_stats = compute_percentiles(accept_lat)
        async_callback_stats = compute_percentiles(cb_lat)
        console.print(
            f"  Done: {len(accept_lat)} accepted, {len(cb_lat)} callbacks received, "
            f"{async_errors} errors, {missing_callbacks} missing"
        )
        if async_err_details:
            for err, count in async_err_details.most_common():
                console.print(f"    [dim]{count}x {err}[/dim]")

    print_report(
        sync_stats, async_accept_stats, async_callback_stats,
        sync_errors, async_errors, missing_callbacks,
    )


if __name__ == "__main__":
    main()
