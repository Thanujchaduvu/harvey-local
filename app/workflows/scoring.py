"""Workflow 7: explainable hybrid score = rules + local embeddings + signals + local-LLM fit."""
from __future__ import annotations

import re

from .. import db, prompts, schemas
from ..embeddings import cosine, get_embedder
from ..llm_client import OllamaUnavailable, get_client
from ..taskqueue import register
from .common import get_business, get_product, get_prospect, product_block, prospect_block

WEIGHTS = {"rules": 0.30, "embedding": 0.20, "signals": 0.25, "llm_fit": 0.25}
TIERS = [(75, "A"), (55, "B"), (35, "C"), (0, "D")]
_STOP = {"of", "and", "the", "for", "to", "in", "a", "head", "senior", "sr", "vp", "director", "manager", "chief", "officer"}


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z]+", (s or "").lower()) if t not in _STOP and len(t) > 2}


def rule_fit(p: dict, icp: dict) -> tuple[float, dict]:
    ind = p["industry"].lower() if p["industry"] else ""
    ind_hit = any(i.lower() in ind or ind in i.lower() for i in icp.get("industries", []) if i and ind) or \
        any(_tokens(i) & _tokens(ind) for i in icp.get("industries", []))
    ptoks = _tokens(p["title"])
    title_hit = max([len(ptoks & _tokens(t)) / max(1, len(_tokens(t))) for t in icp.get("titles", [])] or [0])
    sz = icp.get("company_size") or {}
    lo, hi, n = sz.get("min_employees"), sz.get("max_employees"), p["employees"]
    if n is None or lo is None or hi is None:
        size = 0.5
    elif lo <= n <= hi:
        size = 1.0
    elif lo / 2 <= n <= hi * 2:
        size = 0.5
    else:
        size = 0.0
    geos = [g.lower() for g in icp.get("geographies", []) if g]
    geo = 0.5 if not geos else (1.0 if any(g in (p["location"] or "").lower() or (p["location"] or "").lower() in g for g in geos) else 0.0)
    score = 0.35 * float(ind_hit) + 0.25 * min(1.0, title_hit) + 0.25 * size + 0.15 * geo
    return score, {"industry": float(ind_hit), "title": round(min(1.0, title_hit), 2), "size": size, "geography": geo}


def signal_fit(signals: list[dict]) -> float:
    if not signals:
        return 0.0
    top = max(s["strength"] for s in signals) / 5
    return round(0.7 * top + 0.3 * min(len(signals), 3) / 3, 3)


def tier_for(score: float) -> str:
    return next(t for lim, t in TIERS if score >= lim)


@register("score")
def score_prospect(payload: dict) -> dict:
    p = get_prospect(payload["prospect_id"])
    prod = get_product(p["product_id"])
    biz = get_business(prod["business_id"])
    icp = db.jload(prod["icp_json"], {})
    if not icp:
        raise ValueError("Generate the ICP for this product first.")
    research = db.jload(p["research_json"], {})
    signals = db.jload(p["signals_json"], {}).get("signals", [])

    rules, rules_detail = rule_fit(p, icp)
    emb_text = f"{p['title']} at {p['company']} ({p['industry']}). {research.get('company_summary', '')} {' '.join(research.get('pain_hints', []))}"
    icp_text = f"{icp.get('summary', '')} {' '.join(icp.get('industries', []))} {' '.join(icp.get('titles', []))} {' '.join(icp.get('pain_points', []))}"
    cos = cosine(emb_text, icp_text)
    emb = max(0.0, min(1.0, (cos - 0.15) / 0.5))  # heuristic rescale of cosine into 0..1
    comps = {"rules": rules, "embedding": emb, "signals": signal_fit(signals)}
    breakdown = {"rules_detail": rules_detail, "cosine": round(cos, 3), "embedder": get_embedder().name, "weights": WEIGHTS}

    def finish(partial: bool, fit: dict | None):
        parts = dict(comps)
        if fit:
            parts["llm_fit"] = fit["fit_score"] / 10
        w = {k: WEIGHTS[k] for k in parts}
        total = round(100 * sum(parts[k] * w[k] for k in parts) / sum(w.values()), 1)
        out = {"score": total, "tier": tier_for(total), "partial": partial,
               "components": {k: round(v, 3) for k, v in parts.items()}, "llm_fit": fit, **breakdown}
        db.update("prospects", p["id"], score=total, tier=out["tier"], score_json=db.jdump(out), status="scored")
        return out

    c = get_client()
    try:
        model = c.resolve_model()
        fit = c.chat(task="score", system=prompts.FIT, schema=schemas.FIT, model=model,
                     prompt=f"{product_block(prod, biz)}\n\nProspect:\n{prospect_block(p)}\n"
                            f"Research: {db.jdump({k: v for k, v in research.items() if k in ('company_summary','pain_hints')})}\n"
                            f"Signals: {db.jdump(signals)}")
        fit["fit_score"] = max(0, min(10, int(fit["fit_score"])))
        fit["model"] = model
    except OllamaUnavailable:
        finish(True, None)  # deterministic partial score is saved and visible; LLM part gets queued
        raise
    return finish(False, fit)
