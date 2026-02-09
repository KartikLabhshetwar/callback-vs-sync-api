from app.work import compute_work


def test_compute_work_deterministic():
    """Same input + iterations should produce same result."""
    r1 = compute_work("hello", 100)
    r2 = compute_work("hello", 100)
    assert r1["result"] == r2["result"]
    assert r1["iterations"] == 100


def test_compute_work_different_input():
    """Different inputs should produce different results."""
    r1 = compute_work("hello", 100)
    r2 = compute_work("world", 100)
    assert r1["result"] != r2["result"]


def test_compute_work_returns_hex():
    """Result should be a valid hex string (SHA-256 = 64 hex chars)."""
    result = compute_work("test", 10)
    assert len(result["result"]) == 64
    int(result["result"], 16)  # should not raise


def test_compute_work_duration():
    """Duration should be a non-negative float."""
    result = compute_work("test", 10)
    assert result["duration_ms"] >= 0
