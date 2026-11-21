from __future__ import annotations

import re

from .. import db, prompts, schemas
from ..llm_client import get_client
from ..taskqueue import register
from .common import get_business, get_product, get_prospect, product_block, prospect_block

FOOTER = "\n\nIf this isn't relevant, just reply \"stop\" and I won't follow up."
BAD_PHRASES = ["hope this email finds you", "hope this finds you", "i hope you're well"]


def check_email(subject: str, body: str, p: dict) -> list[str]:
    issues = []
    words = len(body.split())
    if words > 130:
        issues.append(f"too long ({words} words; max 110)")
    if words < 35:
        issues.append(f"too short ({words} words)")
    if re.search(r"\[[^\]]+\]|\{\{|\}\}", body + subject):
        issues.append("contains a placeholder")
    first = (p["name"] or "").split(" ")[0].lower()
    if first and first not in body.lower() and (p["company"] or "").lower() not in body.lower():
        issues.append("does not mention the prospect or company by name")
    if "?" not in body:
        issues.append("no question / call to action")
    if any(b in body.lower() for b in BAD_PHRASES):
        issues.append("uses a cliché opener")
    return issues


@register("email")
def generate_email(payload: dict) -> dict:
    """Workflow 6: personalised email grounded in research, signals and the problem statement."""
    p = get_prospect(payload["prospect_id"])
    prod = get_product(p["product_id"])
    biz = get_business(prod["business_id"])
    research = db.jload(p["research_json"], {})
    signals = db.jload(p["signals_json"], {}).get("signals", [])
    problem = db.jload(p["problem_json"], {})
    if not problem:
        raise ValueError("Generate the problem statement first.")
    c = get_client()
    model = c.resolve_model()
    base = (f"{product_block(prod, biz)}\n\nSender: {biz['persona_name']}, {biz['persona_role']} at {biz['name']}\n"
            f"Call to action: ask for a {prod['cta']}\n\nProspect:\n{prospect_block(p)}\n"
            f"Research: {db.jdump({k: research.get(k) for k in ('company_summary','pain_hints','recent_events')})}\n"
            f"Signals: {db.jdump(signals)}\nProblem statement: {db.jdump({k: v for k, v in problem.items() if k != 'model'})}")
    out, issues = {}, []
    for attempt in (1, 2):
        extra = "" if not issues else f"\n\nFix these problems from your previous draft: {'; '.join(issues)}."
        out = c.chat(task="email", system=prompts.EMAIL, schema=schemas.EMAIL, model=model, temperature=0.5,
                     prompt=base + extra)
        issues = check_email(out["subject"], out["body"], p)
        if not issues:
            break
    body = out["body"].strip() + FOOTER
    eid = db.run("INSERT INTO emails(prospect_id,subject,body,checks_json,model,created_at) VALUES(?,?,?,?,?,?)",
                 (p["id"], out["subject"].strip(), body, db.jdump({"issues": issues, "attempts": attempt}), model, db.now()))
    db.update("prospects", p["id"], status="emailed")
    return {"email_id": eid, "subject": out["subject"], "body": body, "personalization_points": out.get("personalization_points", []),
            "quality_issues": issues, "attempts": attempt, "model": model}
