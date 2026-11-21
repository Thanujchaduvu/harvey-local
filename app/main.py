"""FastAPI backend + static dashboard."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, config, db, embeddings, hardware, network_guard, seed, taskqueue, webresearch
from .llm_client import BadModelOutput, get_client
from .taskqueue import run_or_queue
from .workflows import replies as replies_wf
from .workflows.common import NoLocalData

config.LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler(config.LOG_DIR / "app.log")])
log = logging.getLogger("harvey")


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    if network_guard.install():
        log.info("Strict local mode ON: non-loopback sockets are blocked outside web research.")
    taskqueue.start_worker()
    yield


app = FastAPI(title="Harvey Local", version=__version__, lifespan=lifespan)


@app.exception_handler(KeyError)
async def _404(_, exc: KeyError):
    return JSONResponse({"detail": str(exc).strip("'\"")}, status_code=404)


@app.exception_handler(NoLocalData)
async def _409(_, exc: NoLocalData):
    return JSONResponse({"detail": str(exc)}, status_code=409)


@app.exception_handler(ValueError)
async def _422(_, exc: ValueError):
    return JSONResponse({"detail": str(exc)}, status_code=422)


@app.exception_handler(BadModelOutput)
async def _502(_, exc: BadModelOutput):
    return JSONResponse({"detail": str(exc)}, status_code=502)


# ---------- status / hardware / models -------------------------------------------------
@app.get("/api/status")
def status():
    c = get_client()
    h = c.health()
    emb = embeddings.get_embedder()
    return {
        "version": __version__, "ollama": h, "model": c.resolve_model(h.get("models")),
        "model_installed": c.resolve_model(h.get("models")) in h.get("models", []),
        "queue": taskqueue.counts(), "strict_local": network_guard.is_installed(),
        "blocked_connections": len(network_guard.violations), "embedder": emb.name,
        "embedder_fallback_reason": embeddings.fallback_reason(),
        "last_inference": db.one("SELECT * FROM inference_log ORDER BY id DESC LIMIT 1"),
    }


@app.get("/api/hardware")
def hw():
    d = hardware.detect()
    return {"hardware": d, "recommendation": hardware.recommend(d)}


@app.get("/api/models")
def models():
    c = get_client()
    h = c.health()
    out = []
    for m in h.get("models", []):
        try:
            lic = (c.show(m).get("license") or "").strip().splitlines()
            out.append({"model": m, "license_header": lic[0] if lic else "not reported by Ollama"})
        except Exception:  # noqa: BLE001
            out.append({"model": m, "license_header": "unavailable"})
    return {"installed": out, "ollama_up": h["up"]}


@app.get("/api/inference-log")
def inference_log(limit: int = 100):
    return db.rows("SELECT * FROM inference_log ORDER BY id DESC LIMIT ?", (min(limit, 500),))


# ---------- business / products -----------------------------------------------------------
class BusinessIn(BaseModel):
    name: str = Field(min_length=1)
    website: str = ""
    persona_name: str = "Alex"
    persona_role: str = "Business Development"
    raw_docs: str = ""


class ProductIn(BaseModel):
    business_id: int
    name: str = Field(min_length=1)
    description: str = ""
    pricing: str = ""
    benefits: list[str] = []
    objections: dict[str, str] = {}
    cta: str = "15-minute call"


def _biz(b: dict) -> dict:
    b = dict(b)
    b["profile"] = db.jload(b.pop("profile_json", None))
    b["has_docs"] = bool((b.get("raw_docs") or "").strip())
    b["docs_chars"] = len(b.get("raw_docs") or "")
    b.pop("raw_docs", None)
    return b


def _prod(p: dict) -> dict:
    p = dict(p)
    p["icp"] = db.jload(p.pop("icp_json", None))
    p["benefits"] = db.jload(p.pop("benefits_json"), [])
    p["objections"] = db.jload(p.pop("objections_json"), {})
    p["prospect_count"] = db.one("SELECT COUNT(*) n FROM prospects WHERE product_id=?", (p["id"],))["n"]
    return p


@app.post("/api/demo/seed")
def demo_seed():
    return seed.seed_demo()


@app.get("/api/businesses")
def list_businesses():
    return [dict(_biz(b), products=[_prod(p) for p in db.rows("SELECT * FROM products WHERE business_id=? ORDER BY id", (b["id"],))])
            for b in db.rows("SELECT * FROM businesses ORDER BY id")]


@app.post("/api/businesses")
def create_business(b: BusinessIn):
    return {"id": db.run("INSERT INTO businesses(name,website,persona_name,persona_role,raw_docs,created_at) VALUES(?,?,?,?,?,?)",
                         (b.name, b.website, b.persona_name, b.persona_role, b.raw_docs, db.now()))}


@app.post("/api/businesses/{bid}/docs")
def set_docs(bid: int, body: dict):
    """Store company documents: pass {"text": "..."} or {"load_folder": true} to read data/company_docs."""
    if not db.one("SELECT id FROM businesses WHERE id=?", (bid,)):
        raise KeyError(f"business {bid} not found")
    text = seed.read_docs() if body.get("load_folder") else str(body.get("text", ""))
    db.update("businesses", bid, raw_docs=text)
    return {"chars": len(text)}


@app.post("/api/businesses/{bid}/profile")
def make_profile(bid: int):
    return run_or_queue("profile", {"business_id": bid})


@app.post("/api/products")
def create_product(p: ProductIn):
    return {"id": db.run("INSERT INTO products(business_id,name,description,pricing,benefits_json,objections_json,cta,created_at) VALUES(?,?,?,?,?,?,?,?)",
                         (p.business_id, p.name, p.description, p.pricing, db.jdump(p.benefits), db.jdump(p.objections), p.cta, db.now()))}


@app.post("/api/products/{pid}/icp")
def make_icp(pid: int):
    return run_or_queue("icp", {"product_id": pid})


# ---------- prospects ---------------------------------------------------------------------------
def _prospect(p: dict, full: bool = False) -> dict:
    p = dict(p)
    for k in ("research", "signals", "problem", "score"):
        p[k + "_data"] = db.jload(p.pop(k + "_json", None))
    p["has_text"] = bool((p.get("raw_text") or "").strip())
    if full:
        p["emails"] = db.rows("SELECT * FROM emails WHERE prospect_id=? ORDER BY id DESC", (p["id"],))
    else:
        p["raw_chars"] = len(p.pop("raw_text") or "")
    return p


@app.get("/api/products/{pid}/prospects")
def list_prospects(pid: int):
    return [_prospect(p) for p in db.rows("SELECT * FROM prospects WHERE product_id=? ORDER BY COALESCE(score,-1) DESC, id", (pid,))]


@app.post("/api/products/{pid}/prospects/import")
def import_prospects(pid: int, body: dict):
    """Body: {"prospects": [...]} or {"path": "sample/prospects.json"} (relative to the data dir)."""
    if "path" in body:
        items = seed.parse_file(config.DATA_DIR / body["path"])
    else:
        items = body.get("prospects") or []
    return {"imported": seed.import_prospects(pid, items)}


@app.get("/api/prospects/{prid}")
def get_prospect(prid: int):
    p = db.one("SELECT * FROM prospects WHERE id=?", (prid,))
    if not p:
        raise KeyError(f"prospect {prid} not found")
    return _prospect(p, full=True)


@app.post("/api/prospects/{prid}/run-all")
def run_all(prid: int):
    steps = []
    for st in ("research", "signals", "problem", "score", "email"):
        out = run_or_queue(st, {"prospect_id": prid})
        steps.append({"stage": st, "status": out["status"]})
        if out["status"] == "queued":
            break
    return {"steps": steps, "prospect": get_prospect(prid)}


class FetchIn(BaseModel):
    url: str
    render_js: bool = False


@app.post("/api/prospects/{prid}/fetch-web")
def fetch_web(prid: int, body: FetchIn):
    """ONLINE-ONLY public-web research. Contains no AI; stores text for later local analysis."""
    try:
        return webresearch.attach_to_prospect(prid, body.url, body.render_js)
    except webresearch.WebResearchUnavailable as e:
        raise HTTPException(503, str(e))


STAGES = {"research": "research", "signals": "signals", "problem": "problem", "score": "score", "email": "email"}


@app.post("/api/prospects/{prid}/{stage}")
def run_stage(prid: int, stage: str):
    if stage not in STAGES:
        raise HTTPException(404, f"unknown stage {stage}")
    out = run_or_queue(STAGES[stage], {"prospect_id": prid})
    return {**out, "prospect": get_prospect(prid)}


# ---------- replies -------------------------------------------------------------------------------
class ReplyIn(BaseModel):
    text: str = Field(min_length=1)
    thread: list[dict] = []
    prospect_id: int | None = None


@app.post("/api/replies/classify")
def classify(r: ReplyIn):
    rid = replies_wf.create_reply(r.text, r.thread, r.prospect_id)
    out = run_or_queue("reply", {"reply_id": rid})
    return {**out, "reply": db.one("SELECT * FROM replies WHERE id=?", (rid,))}


@app.get("/api/replies")
def list_replies():
    return db.rows("SELECT * FROM replies ORDER BY id DESC LIMIT 100")


@app.post("/api/replies/eval-sample")
def eval_sample():
    return replies_wf.eval_samples()


# ---------- queue ------------------------------------------------------------------------------------
@app.get("/api/queue")
def queue_list():
    return {"counts": taskqueue.counts(), "tasks": db.rows("SELECT * FROM tasks ORDER BY id DESC LIMIT 50")}


@app.post("/api/queue/process")
def queue_process():
    return taskqueue.process()


_FRONT = Path(__file__).resolve().parent.parent / "frontend"
if _FRONT.exists():
    app.mount("/", StaticFiles(directory=_FRONT, html=True), name="ui")
