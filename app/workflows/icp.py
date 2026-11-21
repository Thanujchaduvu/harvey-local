from __future__ import annotations

from .. import db, prompts, schemas
from ..llm_client import get_client
from ..taskqueue import register
from .common import get_business, get_product, product_block


@register("icp")
def generate_icp(payload: dict) -> dict:
    """Workflow 2: product-specific ICP (differs per product, grounded in the business profile)."""
    prod = get_product(payload["product_id"])
    biz = get_business(prod["business_id"])
    c = get_client()
    model = c.resolve_model()
    out = c.chat(task="icp", system=prompts.ICP, schema=schemas.ICP, model=model,
                 prompt=f"{product_block(prod, biz)}\n\nObjections we hear: {prod['objections_json']}\n"
                        "Define the ICP for this specific product only.")
    sz = out.get("company_size") or {}
    if sz.get("min_employees", 0) > sz.get("max_employees", 10**9):
        sz["min_employees"], sz["max_employees"] = sz["max_employees"], sz["min_employees"]
    db.update("products", prod["id"], icp_json=db.jdump(out), icp_model=model, icp_at=db.now())
    return out
