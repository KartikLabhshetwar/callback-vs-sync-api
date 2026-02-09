import statistics

from rich.console import Console
from rich.table import Table


def compute_percentiles(latencies: list[float]) -> dict:
    if not latencies:
        return {"p50": 0, "p95": 0, "p99": 0, "min": 0, "max": 0, "mean": 0, "count": 0}
    sorted_lat = sorted(latencies)
    n = len(sorted_lat)
    return {
        "p50": sorted_lat[int(n * 0.50)],
        "p95": sorted_lat[int(n * 0.95)] if n > 1 else sorted_lat[0],
        "p99": sorted_lat[int(n * 0.99)] if n > 1 else sorted_lat[0],
        "min": sorted_lat[0],
        "max": sorted_lat[-1],
        "mean": round(statistics.mean(sorted_lat), 2),
        "count": n,
    }


def print_report(
    sync_stats: dict | None,
    async_accept_stats: dict | None,
    async_callback_stats: dict | None,
    sync_errors: int = 0,
    async_errors: int = 0,
    async_missing_callbacks: int = 0,
) -> None:
    console = Console()
    console.print()
    console.rule("[bold blue]Load Test Results[/bold blue]")
    console.print()

    table = Table(title="Latency Comparison (ms)", show_lines=True)
    table.add_column("Metric", style="bold")
    if sync_stats:
        table.add_column("Sync (response)", justify="right", style="red")
    if async_accept_stats:
        table.add_column("Async (accept)", justify="right", style="green")
    if async_callback_stats:
        table.add_column("Async (callback)", justify="right", style="cyan")

    metrics = ["count", "min", "p50", "p95", "p99", "max", "mean"]
    for m in metrics:
        row = [m.upper()]
        if sync_stats:
            row.append(f"{sync_stats.get(m, 0):.1f}" if m != "count" else str(sync_stats.get(m, 0)))
        if async_accept_stats:
            row.append(f"{async_accept_stats.get(m, 0):.1f}" if m != "count" else str(async_accept_stats.get(m, 0)))
        if async_callback_stats:
            row.append(f"{async_callback_stats.get(m, 0):.1f}" if m != "count" else str(async_callback_stats.get(m, 0)))
        table.add_row(*row)

    console.print(table)

    # Error summary
    error_table = Table(title="Error Summary", show_lines=True)
    error_table.add_column("Metric", style="bold")
    error_table.add_column("Value", justify="right")
    if sync_stats:
        error_table.add_row("Sync errors", str(sync_errors))
    if async_accept_stats:
        error_table.add_row("Async errors", str(async_errors))
    if async_callback_stats:
        error_table.add_row("Missing callbacks", str(async_missing_callbacks))
    console.print(error_table)
    console.print()
