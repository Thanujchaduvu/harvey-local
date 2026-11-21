"""SQLite storage (single file, no server)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS businesses(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, website TEXT DEFAULT '',
  persona_name TEXT DEFAULT 'Alex', persona_role TEXT DEFAULT 'Business Development',
  raw_docs TEXT DEFAULT '', profile_json TEXT, profile_model TEXT, profile_at REAL,
  is_sample INTEGER DEFAULT 0, created_at REAL);
CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY, business_id INTEGER NOT NULL REFERENCES businesses(id),
  name TEXT NOT NULL, description TEXT DEFAULT '', pricing TEXT DEFAULT '',
  benefits_json TEXT DEFAULT '[]', objections_json TEXT DEFAULT '{}', cta TEXT DEFAULT '15-minute call',
  icp_json TEXT, icp_model TEXT, icp_at REAL, created_at REAL);
CREATE TABLE IF NOT EXISTS prospects(
  id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
  name TEXT, company TEXT, title TEXT, industry TEXT, employees INTEGER, location TEXT,
  email TEXT, website TEXT, raw_text TEXT DEFAULT '', source TEXT DEFAULT '',
  research_json TEXT, signals_json TEXT, problem_json TEXT,
  score REAL, tier TEXT, score_json TEXT, status TEXT DEFAULT 'new', created_at REAL);
CREATE TABLE IF NOT EXISTS emails(
  id INTEGER PRIMARY KEY, prospect_id INTEGER NOT NULL REFERENCES prospects(id),
  subject TEXT, body TEXT, checks_json TEXT, model TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS replies(
  id INTEGER PRIMARY KEY, prospect_id INTEGER, text TEXT NOT NULL, thread_json TEXT,
  label TEXT, confidence REAL, rationale TEXT, suggested_action TEXT, suggested_reply TEXT,
  method TEXT, model TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS tasks(
  id INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload_json TEXT NOT NULL,
  status TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0, error TEXT DEFAULT '',
  created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS inference_log(
  id INTEGER PRIMARY KEY, ts REAL, task TEXT, model TEXT, endpoint TEXT,
  prompt_tokens INTEGER, completion_tokens INTEGER, latency_ms INTEGER,
  ok INTEGER, error TEXT, output_preview TEXT);
"""

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None
_path: Path | None = None


def init(path: Path | str | None = None) -> None:
    global _conn, _path
    with _lock:
        if _conn is not None:
            _conn.close()
        _path = Path(path) if path else config.DB_PATH
        _path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(_path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
        _conn.commit()


def _c() -> sqlite3.Connection:
    if _conn is None:
        init()
    assert _conn is not None
    return _conn


def rows(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in _c().execute(sql, args).fetchall()]


def one(sql: str, args: tuple = ()) -> dict | None:
    r = rows(sql, args)
    return r[0] if r else None


def run(sql: str, args: tuple = ()) -> int:
    with _lock:
        cur = _c().execute(sql, args)
        _c().commit()
        return cur.lastrowid or 0


def update(table: str, row_id: int, **fields: Any) -> None:
    cols = ", ".join(f"{k}=?" for k in fields)
    run(f"UPDATE {table} SET {cols} WHERE id=?", (*fields.values(), row_id))


def jdump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def jload(s: str | None, default: Any = None) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return default


def now() -> float:
    return time.time()
