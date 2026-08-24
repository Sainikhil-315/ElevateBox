import re
import sqlite3
import threading
from datetime import datetime, timezone

from src.config import get_settings

_local = threading.local()


def _conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        path = _sqlite_path(get_settings().database_url)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return conn


def _sqlite_path(url: str) -> str:
    m = re.match(r"sqlite:///(.*)", url)
    if not m:
        raise ValueError(f"Only sqlite DATABASE_URL supported, got: {url}")
    return m.group(1) or "./calls.db"


SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    call_sid      TEXT PRIMARY KEY,
    to_number     TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'queued',
    duration_sec  INTEGER,
    transcript    TEXT DEFAULT '',
    classification TEXT,
    barrier       TEXT,
    callback_at   TEXT,
    whatsapp_sent INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS turn_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    call_sid    TEXT NOT NULL REFERENCES calls(call_sid),
    ts          TEXT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    stt_confidence REAL,
    latency_ms  INTEGER
);
"""


def init_db() -> None:
    conn = _conn()
    conn.executescript(SCHEMA)
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_call(call_sid: str, to_number: str, status: str = "queued") -> None:
    now = _now()
    conn = _conn()
    conn.execute(
        """INSERT INTO calls (call_sid, to_number, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(call_sid) DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at""",
        (call_sid, to_number, status, now, now),
    )
    conn.commit()


def update_call_status(call_sid: str, status: str, duration_sec: int | None = None) -> None:
    sets = ["status = ?", "updated_at = ?"]
    vals = [status, _now()]
    if duration_sec is not None:
        sets.append("duration_sec = ?")
        vals.append(duration_sec)
    vals.append(call_sid)
    conn = _conn()
    conn.execute(f"UPDATE calls SET {', '.join(sets)} WHERE call_sid = ?", vals)
    conn.commit()


def get_call(call_sid: str) -> dict | None:
    row = _conn().execute("SELECT * FROM calls WHERE call_sid = ?", (call_sid,)).fetchone()
    return dict(row) if row else None


def append_turn(call_sid: str, role: str, content: str, stt_confidence: float | None = None, latency_ms: int | None = None) -> None:
    conn = _conn()
    conn.execute(
        "INSERT INTO turn_events (call_sid, ts, role, content, stt_confidence, latency_ms) VALUES (?, ?, ?, ?, ?, ?)",
        (call_sid, _now(), role, content, stt_confidence, latency_ms),
    )
    conn.commit()


def get_turns(call_sid: str) -> list[dict]:
    rows = _conn().execute(
        "SELECT role, content, stt_confidence, latency_ms, ts FROM turn_events WHERE call_sid = ? ORDER BY id",
        (call_sid,),
    ).fetchall()
    return [dict(r) for r in rows]
