from __future__ import annotations

from .. import db, prompts, schemas
from ..llm_client import get_client
from ..taskqueue import register
from .common import NoLocalData, get_business, get_product, get_prospect, product_block, prospect_block, untrusted, verify_quotes


@register("research")
def research_prospect(payload: dict) -> dict:
    """Workflow 3: research a prospect from previously downloaded/stored text (no internet needed)."""
    p = get_prospect(payload["prospect_id"])
    if not (p["raw_text"] or "").strip():
        raise NoLocalData("No stored data for this prospect. Import it, or use 'Fetch from web' while online.")
    prod = get_product(p["product_id"])
    biz = get_business(prod["business_id"])
    c = get_client()
    model = c.resolve_model()
    out = c.chat(task="research", system=prompts.RESEARCH, schema=schemas.RESEARCH, model=model,
                 prompt=f"{product_block(prod, biz)}\n\nProspect:\n{prospect_block(p)}\n\nDownloaded text:\n{untrusted(p['raw_text'])}")
    ok, bad = verify_quotes(out.get("evidence", []), p["raw_text"])
    out["evidence"], out["evidence_rejected"] = ok, bad  # anti-hallucination: keep only verbatim quotes
    out["model"] = model
    db.update("prospects", p["id"], research_json=db.jdump(out), status="researched")
    return out
