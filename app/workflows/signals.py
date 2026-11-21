from __future__ import annotations

from .. import db, prompts, schemas
from ..llm_client import get_client
from ..taskqueue import register
from .common import NoLocalData, get_product, get_prospect, prospect_block, untrusted, quote_in_source


@register("signals")
def classify_signals(payload: dict) -> dict:
    """Workflow 4: buying-signal classification with verbatim-evidence verification."""
    p = get_prospect(payload["prospect_id"])
    if not (p["raw_text"] or "").strip():
        raise NoLocalData("No stored data for this prospect.")
    prod = get_product(p["product_id"])
    icp = db.jload(prod["icp_json"], {})
    c = get_client()
    model = c.resolve_model()
    out = c.chat(task="signals", system=prompts.SIGNALS, schema=schemas.SIGNALS, model=model,
                 prompt=f"Product: {prod['name']} - {prod['description']}\nBuying triggers for this product: "
                        f"{', '.join(icp.get('buying_triggers', [])) or 'unknown'}\n\nProspect:\n{prospect_block(p)}\n\n"
                        f"Text:\n{untrusted(p['raw_text'])}")
    cleaned = []
    for s in out.get("signals", []):
        s["strength"] = max(1, min(5, int(s.get("strength", 1))))
        s["evidence_verified"] = quote_in_source(s.get("evidence", ""), p["raw_text"])
        if not s["evidence_verified"]:
            s["strength"] = min(s["strength"], 2)  # unverifiable claims cannot be strong signals
        cleaned.append(s)
    result = {"signals": cleaned, "model": model}
    db.update("prospects", p["id"], signals_json=db.jdump(result), status="signals")
    return result
