from __future__ import annotations

from .. import db, prompts, schemas
from ..llm_client import get_client
from ..taskqueue import register
from .common import get_business, untrusted


@register("profile")
def generate_profile(payload: dict) -> dict:
    """Workflow 1: business profile from locally stored company documents."""
    b = get_business(payload["business_id"])
    if not (b["raw_docs"] or "").strip():
        raise ValueError("No company documents stored. Load docs from data/company_docs or paste text first.")
    c = get_client()
    model = c.resolve_model()
    out = c.chat(task="profile", system=prompts.PROFILE, schema=schemas.PROFILE, model=model,
                 prompt=f"Company name: {b['name']}\nCompany documents:\n{untrusted(b['raw_docs'], 8000)}")
    db.update("businesses", b["id"], profile_json=db.jdump(out), profile_model=model, profile_at=db.now())
    return out
