from __future__ import annotations

from .. import db, prompts, schemas
from ..llm_client import get_client
from ..taskqueue import register
from .common import get_business, get_product, get_prospect, product_block, prospect_block


@register("problem")
def generate_problem(payload: dict) -> dict:
    """Workflow 5: problem-statement generation grounded in research + signals."""
    p = get_prospect(payload["prospect_id"])
    prod = get_product(p["product_id"])
    biz = get_business(prod["business_id"])
    research = db.jload(p["research_json"], {})
    signals = db.jload(p["signals_json"], {}).get("signals", [])
    if not research and not signals:
        raise ValueError("Run research and signal classification first.")
    c = get_client()
    model = c.resolve_model()
    out = c.chat(task="problem", system=prompts.PROBLEM, schema=schemas.PROBLEM, model=model,
                 prompt=f"{product_block(prod, biz)}\n\nProspect:\n{prospect_block(p)}\n\n"
                        f"Research: {db.jdump({k: v for k, v in research.items() if k != 'model'})}\n"
                        f"Signals: {db.jdump(signals)}")
    out["model"] = model
    db.update("prospects", p["id"], problem_json=db.jdump(out), status="problem")
    return out
