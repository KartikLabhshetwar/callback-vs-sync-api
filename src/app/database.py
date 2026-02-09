import aiosqlite

from app.config import settings

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    if _db is None:
        raise RuntimeError("Database not initialized — call init_db() first")
    return _db


async def init_db() -> None:
    global _db
    _db = await aiosqlite.connect(settings.database_path)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.execute("PRAGMA busy_timeout=5000")
    await _db.executescript(
        """
        CREATE TABLE IF NOT EXISTS requests (
            id TEXT PRIMARY KEY,
            mode TEXT NOT NULL,
            input_data TEXT NOT NULL,
            iterations INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            result TEXT,
            duration_ms REAL,
            callback_url TEXT,
            callback_status TEXT,
            callback_attempts INTEGER DEFAULT 0,
            callback_error TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS callback_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL REFERENCES requests(id),
            attempt_number INTEGER NOT NULL,
            status_code INTEGER,
            error TEXT,
            duration_ms REAL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_requests_mode ON requests(mode);
        CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
        CREATE INDEX IF NOT EXISTS idx_callback_attempts_request_id ON callback_attempts(request_id);
        """
    )
    await _db.commit()


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def insert_request(
    request_id: str,
    mode: str,
    input_data: str,
    iterations: int,
    callback_url: str | None = None,
) -> None:
    db = await get_db()
    await db.execute(
        """INSERT INTO requests (id, mode, input_data, iterations, callback_url)
           VALUES (?, ?, ?, ?, ?)""",
        (request_id, mode, input_data, iterations, callback_url),
    )
    await db.commit()


async def update_request_result(
    request_id: str, status: str, result: str, duration_ms: float
) -> None:
    db = await get_db()
    await db.execute(
        """UPDATE requests
           SET status = ?, result = ?, duration_ms = ?, completed_at = datetime('now')
           WHERE id = ?""",
        (status, result, duration_ms, request_id),
    )
    await db.commit()


async def update_callback_status(
    request_id: str, callback_status: str, attempts: int, error: str | None = None
) -> None:
    db = await get_db()
    await db.execute(
        """UPDATE requests
           SET callback_status = ?, callback_attempts = ?, callback_error = ?
           WHERE id = ?""",
        (callback_status, attempts, error, request_id),
    )
    await db.commit()


async def insert_callback_attempt(
    request_id: str,
    attempt_number: int,
    status_code: int | None,
    error: str | None,
    duration_ms: float,
) -> None:
    db = await get_db()
    await db.execute(
        """INSERT INTO callback_attempts (request_id, attempt_number, status_code, error, duration_ms)
           VALUES (?, ?, ?, ?, ?)""",
        (request_id, attempt_number, status_code, error, duration_ms),
    )
    await db.commit()


async def get_request(request_id: str) -> dict | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM requests WHERE id = ?", (request_id,))
    row = await cursor.fetchone()
    if row is None:
        return None
    return dict(row)


async def get_callback_attempts(request_id: str) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM callback_attempts WHERE request_id = ? ORDER BY attempt_number",
        (request_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def list_requests(
    mode: str | None = None, limit: int = 50, offset: int = 0
) -> list[dict]:
    db = await get_db()
    if mode:
        cursor = await db.execute(
            "SELECT * FROM requests WHERE mode = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (mode, limit, offset),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM requests ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
