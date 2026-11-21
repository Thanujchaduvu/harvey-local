"""Loads the SYNTHETIC sample company, products and prospects (input data only; no outputs)."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from . import config, db

SAMPLE_NAME = "Kestrel Works (sample)"


def read_docs(folder: Path | None = None) -> str:
    folder = (folder or config.DATA_DIR / "company_docs").resolve()
    if not folder.is_relative_to(config.DATA_DIR):
        raise ValueError("Documents must live inside the data directory.")
    parts = [f"### {f.name}\n{f.read_text(errors='ignore')}" for f in sorted(folder.glob("*")) if f.suffix in (".md", ".txt")]
    if not parts:
        raise FileNotFoundError(f"No .md/.txt files in {folder}")
    return "\n\n".join(parts)


def import_prospects(product_id: int, items: list[dict], source: str = "import") -> int:
    n = 0
    for it in items:
        emp = it.get("employees")
        db.run("INSERT INTO prospects(product_id,name,company,title,industry,employees,location,email,website,raw_text,source,created_at)"
               " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
               (product_id, it.get("name", ""), it.get("company", ""), it.get("title", ""), it.get("industry", ""),
                int(emp) if str(emp or "").isdigit() else None, it.get("location", ""), it.get("email", ""),
                it.get("website", ""), it.get("raw_text", ""), it.get("source", source), db.now()))
        n += 1
    return n


def parse_file(path: Path) -> list[dict]:
    path = path.resolve()
    if not path.is_relative_to(config.DATA_DIR):
        raise ValueError("Prospect files must live inside the data directory.")
    text = path.read_text(errors="ignore")
    return json.loads(text) if path.suffix == ".json" else list(csv.DictReader(io.StringIO(text)))


def seed_demo() -> dict:
    existing = db.one("SELECT id FROM businesses WHERE name=?", (SAMPLE_NAME,))
    if existing:
        return {"business_id": existing["id"], "created": False}
    bid = db.run("INSERT INTO businesses(name,website,persona_name,persona_role,raw_docs,is_sample,created_at) VALUES(?,?,?,?,?,1,?)",
                 (SAMPLE_NAME, "https://kestrelworks.example", "Jordan Lee", "Account Executive", read_docs(), db.now()))
    defs = {
        "dispatchly": dict(name="Dispatchly", description="Dispatch and scheduling software for field-service companies (HVAC, plumbing, electrical, solar maintenance).",
                           pricing="$49 per technician per month", benefits=["Drag-and-drop, route-aware scheduling", "Customer arrival-window texts", "Technician app works without signal", "Live in about 6 working days"],
                           objections={"too expensive": "Flat per-technician price; no implementation fees.", "already have a tool": "Ask what the tool does worst during peak season."}, cta="15-minute call"),
        "ledgerline": dict(name="Ledgerline", description="Invoice capture and approval automation for small finance teams: reads invoices from email, matches POs, flags duplicates.",
                           pricing="$299 per month for up to 5,000 invoices", benefits=["Invoices captured from email automatically", "Duplicate-invoice detection", "Approval routing", "Exports to common accounting systems"],
                           objections={"too expensive": "Flat monthly price is typically below one AP clerk's weekly cost.", "already have ERP": "Ledgerline sits in front of the ERP and feeds it."}, cta="15-minute call"),
    }
    ids = {}
    for key, d in defs.items():
        ids[key] = db.run("INSERT INTO products(business_id,name,description,pricing,benefits_json,objections_json,cta,created_at) VALUES(?,?,?,?,?,?,?,?)",
                          (bid, d["name"], d["description"], d["pricing"], db.jdump(d["benefits"]), db.jdump(d["objections"]), d["cta"], db.now()))
    items = json.loads((config.DATA_DIR / "sample" / "prospects.json").read_text())
    for key, pid in ids.items():
        import_prospects(pid, [i for i in items if i.get("product_hint") == key])
    return {"business_id": bid, "product_ids": ids, "created": True}
