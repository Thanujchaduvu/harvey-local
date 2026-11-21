"""Workflow 8: reply classification. Compliance-critical cases are handled by deterministic rules (no LLM needed)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .. import config, db, prompts, schemas
from ..llm_client import OllamaUnavailable, get_client
from ..taskqueue import register
from .common import untrusted

UNSUB = re.compile(r"\b(unsubscribe|remove me|take me off|do not (email|contact)|don'?t (email|contact)|stop (emailing|contacting|sending))\b|^\s*stop\s*[.!]?\s*$", re.I)
OOO = re.compile(r"\b(out of (the )?office|automatic reply|auto-?reply|on (annual |parental )?leave|back on [A-Z][a-z]+)", re.I)


def rule_classify(text: str) -> dict | None:
    if UNSUB.search(text):
        return {"label": "unsubscribe", "confidence": 1.0, "method": "rule",
                "rationale": "Explicit opt-out wording detected by deterministic rule.",
                "suggested_action": "Add to suppression list. Do not contact again.", "suggested_reply": ""}
    if OOO.search(text):
        return {"label": "out_of_office", "confidence": 0.95, "method": "rule",
                "rationale": "Auto-reply wording detected by deterministic rule.",
                "suggested_action": "Pause sequence and retry after the return date.", "suggested_reply": ""}
    return None


def _thread_text(thread: list[dict]) -> str:
    return "\n".join(f"{'US' if m.get('from') == 'us' else 'PROSPECT'}: {m.get('text', '')}" for m in thread)


@register("reply")
def classify_reply(payload: dict) -> dict:
    r = db.one("SELECT * FROM replies WHERE id=?", (payload["reply_id"],))
    if not r:
        raise KeyError("reply not found")
    ruled = rule_classify(r["text"])
    if ruled:
        db.update("replies", r["id"], label=ruled["label"], confidence=ruled["confidence"], rationale=ruled["rationale"],
                  suggested_action=ruled["suggested_action"], suggested_reply="", method="rule", model="")
        return ruled
    thread = db.jload(r["thread_json"], [])
    c = get_client()
    model = c.resolve_model()
    out = c.chat(task="reply", system=prompts.REPLY, schema=schemas.REPLY, model=model,
                 prompt=f"Earlier thread:\n{untrusted(_thread_text(thread), 3000) if thread else '(none)'}\n\n"
                        f"Latest reply from prospect:\n{untrusted(r['text'], 2000)}")
    out["confidence"] = max(0.0, min(1.0, float(out.get("confidence", 0.5))))
    out["method"] = "llm"
    db.update("replies", r["id"], label=out["label"], confidence=out["confidence"], rationale=out["rationale"],
              suggested_action=out["suggested_action"], suggested_reply=out.get("suggested_reply", ""), method="llm", model=model)
    return out


def create_reply(text: str, thread: list[dict] | None = None, prospect_id: int | None = None) -> int:
    return db.run("INSERT INTO replies(prospect_id,text,thread_json,created_at) VALUES(?,?,?,?)",
                  (prospect_id, text, db.jdump(thread or []), db.now()))


def eval_samples(path: Path | None = None) -> dict:
    """Run the bundled sample conversations (data/sample/conversations.json) and report accuracy."""
    path = path or config.DATA_DIR / "sample" / "conversations.json"
    items = json.loads(path.read_text())
    results, correct = [], 0
    for it in items:
        thread = it["thread"]
        last = next(m["text"] for m in reversed(thread) if m["from"] == "prospect")
        rid = create_reply(last, thread[:-1])
        try:
            out = classify_reply({"reply_id": rid})
        except OllamaUnavailable as e:
            return {"error": str(e), "completed": len(results), "total": len(items), "results": results}
        ok = out["label"] == it["expected"]
        correct += ok
        results.append({"id": it["id"], "text": last, "expected": it["expected"], "predicted": out["label"],
                        "confidence": out["confidence"], "method": out["method"], "correct": ok})
    return {"accuracy": round(correct / len(items), 3), "correct": correct, "total": len(items), "results": results}
