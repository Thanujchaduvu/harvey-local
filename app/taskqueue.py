"""SQLite-backed queue for LLM tasks that could not run because Ollama was down."""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from . import config, db
from .llm_client import OllamaUnavailable, get_client

log = logging.getLogger("harvey.queue")
HANDLERS: dict[str, Callable[[dict], object]] = {}


def register(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


def enqueue(kind: str, payload: dict, error: str = "") -> int:
    pj = db.jdump(payload)
    dup = db.one("SELECT id FROM tasks WHERE kind=? AND payload_json=? AND status='pending'", (kind, pj))
    if dup:
        return dup["id"]
    return db.run("INSERT INTO tasks(kind,payload_json,error,created_at,updated_at) VALUES(?,?,?,?,?)",
                  (kind, pj, error, db.now(), db.now()))


def run_or_queue(kind: str, payload: dict) -> dict:
    """Run a local-AI workflow; if Ollama is unavailable, queue it. Never reroutes to a cloud API."""
    try:
        return {"status": "done", "result": HANDLERS[kind](payload)}
    except OllamaUnavailable as e:
        tid = enqueue(kind, payload, str(e))
        return {"status": "queued", "task_id": tid, "error": str(e),
                "message": "Local model unavailable. Task queued and will run when Ollama is back. Nothing was sent to a cloud service."}


def counts() -> dict:
    out = {"pending": 0, "running": 0, "done": 0, "failed": 0}
    for r in db.rows("SELECT status, COUNT(*) n FROM tasks GROUP BY status"):
        out[r["status"]] = r["n"]
    return out


def process(max_items: int = 50) -> dict:
    h = get_client().health()
    if not h["up"]:
        return {"processed": 0, "reason": h.get("error", "Ollama unavailable")}
    done = failed = 0
    for t in db.rows("SELECT * FROM tasks WHERE status='pending' ORDER BY id LIMIT ?", (max_items,)):
        db.update("tasks", t["id"], status="running", attempts=t["attempts"] + 1, updated_at=db.now())
        try:
            HANDLERS[t["kind"]](db.jload(t["payload_json"], {}))
            db.update("tasks", t["id"], status="done", error="", updated_at=db.now())
            done += 1
        except OllamaUnavailable as e:
            db.update("tasks", t["id"], status="pending", error=str(e), updated_at=db.now())
            return {"processed": done, "failed": failed, "reason": str(e)}
        except Exception as e:  # noqa: BLE001
            db.update("tasks", t["id"], status="failed", error=f"{type(e).__name__}: {e}", updated_at=db.now())
            failed += 1
    return {"processed": done, "failed": failed}


_worker: threading.Thread | None = None


def start_worker(interval: float = 15.0) -> None:
    global _worker
    if _worker or not config.QUEUE_WORKER:
        return

    def loop():
        while True:
            time.sleep(interval)
            try:
                if counts()["pending"]:
                    process()
            except Exception:  # noqa: BLE001
                log.exception("queue worker error")

    _worker = threading.Thread(target=loop, daemon=True, name="harvey-queue")
    _worker.start()
