import statistics

from rich.console import Console
from rich.panel import Panel
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


def _bar(value: float, max_value: float, width: int = 30) -> str:
    """Create a simple ASCII bar for visual comparison."""
    if max_value == 0:
        return ""
    filled = int((value / max_value) * width)
    filled = max(1, min(filled, width))
    return "\u2588" * filled + "\u2591" * (width - filled)


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

    # --- Latency comparison table ---
    table = Table(title="Latency Comparison (ms)", show_lines=True)
    table.add_column("Metric", style="bold")
    if sync_stats:
        table.add_column("Sync (response)", justify="right", style="red")
    if async_accept_stats:
        table.add_column("Async (accept)", justify="right", style="green")
    if async_callback_stats and async_callback_stats["count"] > 0:
        table.add_column("Async (callback)", justify="right", style="cyan")

    metrics = ["count", "min", "p50", "p95", "p99", "max", "mean"]
    for m in metrics:
        row = [m.upper()]
        if sync_stats:
            row.append(f"{sync_stats.get(m, 0):.1f}" if m != "count" else str(sync_stats.get(m, 0)))
        if async_accept_stats:
            row.append(f"{async_accept_stats.get(m, 0):.1f}" if m != "count" else str(async_accept_stats.get(m, 0)))
        if async_callback_stats and async_callback_stats["count"] > 0:
            row.append(f"{async_callback_stats.get(m, 0):.1f}" if m != "count" else str(async_callback_stats.get(m, 0)))
        table.add_row(*row)

    console.print(table)

    # --- Error summary ---
    error_table = Table(title="Error Summary", show_lines=True)
    error_table.add_column("Metric", style="bold")
    error_table.add_column("Value", justify="right")
    if sync_stats:
        error_table.add_row("Sync errors", str(sync_errors))
    if async_accept_stats is not None:
        error_table.add_row("Async errors", str(async_errors))
        error_table.add_row("Missing callbacks", str(async_missing_callbacks))
    console.print(error_table)

    # --- Visual bar comparison of P50, P95, P99 ---
    if sync_stats and async_accept_stats and sync_stats["count"] > 0 and async_accept_stats["count"] > 0:
        has_callback = async_callback_stats and async_callback_stats["count"] > 0

        for percentile in ("p50", "p95", "p99"):
            console.print()
            values = [sync_stats[percentile], async_accept_stats[percentile]]
            if has_callback:
                values.append(async_callback_stats[percentile])
            max_val = max(values) if values else 1

            console.print(f"[bold]{percentile.upper()} Latency Visual Comparison:[/bold]")
            console.print(
                f"  Sync response:  {_bar(sync_stats[percentile], max_val)} {sync_stats[percentile]:.0f}ms",
                style="red",
            )
            console.print(
                f"  Async accept:   {_bar(async_accept_stats[percentile], max_val)} {async_accept_stats[percentile]:.0f}ms",
                style="green",
            )
            if has_callback:
                console.print(
                    f"  Async callback: {_bar(async_callback_stats[percentile], max_val)} {async_callback_stats[percentile]:.0f}ms",
                    style="cyan",
                )

    # --- Insight panel ---
    console.print()
    insights = []

    if sync_stats and sync_stats["count"] > 0 and async_accept_stats and async_accept_stats["count"] > 0:
        for pct in ("p50", "p95", "p99"):
            ratio = sync_stats[pct] / async_accept_stats[pct] if async_accept_stats[pct] > 0 else 0
            if ratio > 1:
                insights.append(
                    f"Async accept is ~{ratio:.0f}x faster than sync response ({pct.upper()}). "
                    f"Sync {pct.upper()}: {sync_stats[pct]:.0f}ms vs Async accept {pct.upper()}: {async_accept_stats[pct]:.0f}ms."
                )

    if async_callback_stats and async_callback_stats["count"] > 0 and sync_stats and sync_stats["count"] > 0:
        cb_ratio = async_callback_stats["p50"] / sync_stats["p50"] if sync_stats["p50"] > 0 else 0
        if cb_ratio > 0.8 and cb_ratio < 1.5:
            insights.append(
                "Async callback total time is similar to sync — the work takes the same time. "
                "But the client was FREE during that time instead of blocking."
            )
        elif cb_ratio >= 1.5:
            insights.append(
                "Async callback total time is higher than sync. This includes queue wait time + "
                "work time + callback delivery — the trade-off for non-blocking."
            )

    if sync_errors > 0 and sync_stats and sync_stats["count"] > 0:
        error_rate = sync_errors / (sync_stats["count"] + sync_errors) * 100
        insights.append(f"Sync error rate: {error_rate:.1f}% — this shows how sync degrades under load.")

    if async_errors > 0 and async_accept_stats is not None:
        total = (async_accept_stats["count"] if async_accept_stats else 0) + async_errors
        if total > 0:
            error_rate = async_errors / total * 100
            insights.append(f"Async error rate: {error_rate:.1f}%")

    if insights:
        console.print(Panel("\n".join(f"  {i+1}. {insight}" for i, insight in enumerate(insights)),
                            title="[bold]Key Insights[/bold]", border_style="blue"))
    console.print()
