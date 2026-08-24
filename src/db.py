import json
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
    language      TEXT,
    classification TEXT,
    barrier       TEXT,
    summary       TEXT,
    callback_at   TEXT,
    callback_phrase TEXT,
    whatsapp_sent INTEGER DEFAULT 0,
    followup_sent INTEGER DEFAULT 0,
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
CREATE TABLE IF NOT EXISTS failed_actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    call_sid    TEXT,
    action_type TEXT NOT NULL,
    payload     TEXT NOT NULL,
    error       TEXT,
    attempts    INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sent_actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    call_sid    TEXT NOT NULL,
    action_type TEXT NOT NULL,
    sent_at     TEXT NOT NULL,
    UNIQUE(call_sid, action_type)
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


def update_call_fields(call_sid: str, **fields) -> None:
    if not fields:
        return
    allowed = {
        "language", "classification", "barrier", "summary",
        "callback_at", "callback_phrase", "whatsapp_sent", "followup_sent", "transcript",
    }
    cols, vals = [], []
    for k, v in fields.items():
        if k not in allowed:
            raise ValueError(f"Unknown call field: {k}")
        cols.append(f"{k} = ?")
        vals.append(v)
    cols.append("updated_at = ?")
    vals.append(_now())
    vals.append(call_sid)
    conn = _conn()
    conn.execute(f"UPDATE calls SET {', '.join(cols)} WHERE call_sid = ?", vals)
    conn.commit()


def mark_action_sent(call_sid: str, action_type: str) -> bool:
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO sent_actions (call_sid, action_type, sent_at) VALUES (?, ?, ?)",
            (call_sid, action_type, _now()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def was_action_sent(call_sid: str, action_type: str) -> bool:
    row = _conn().execute(
        "SELECT 1 FROM sent_actions WHERE call_sid = ? AND action_type = ?",
        (call_sid, action_type),
    ).fetchone()
    return row is not None


def record_failed_action(call_sid: str, action_type: str, payload: dict, error: str, attempts: int) -> None:
    conn = _conn()
    conn.execute(
        "INSERT INTO failed_actions (call_sid, action_type, payload, error, attempts, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (call_sid, action_type, json.dumps(payload), error, attempts, _now()),
    )
    conn.commit()
