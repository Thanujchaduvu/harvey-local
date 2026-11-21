from __future__ import annotations

import re

from .. import db


class NoLocalData(ValueError):
    """The prospect has no stored text to research (add data or fetch it online first)."""


def untrusted(text: str, limit: int = 6000) -> str:
    return f"<untrusted_data>\n{(text or '')[:limit]}\n</untrusted_data>"


def _norm(s: str) -> str:
    s = (s or "").lower().replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return " ".join(re.sub(r"[^a-z0-9%$]+", " ", s).split())


def quote_in_source(quote: str, source: str) -> bool:
    q = _norm(quote)
    return len(q) >= 8 and q in _norm(source)


def verify_quotes(quotes: list[str], source: str) -> tuple[list[str], list[str]]:
    ok, bad = [], []
    for q in quotes or []:
        (ok if quote_in_source(q, source) else bad).append(q)
    return ok, bad


def get_prospect(pid: int) -> dict:
    p = db.one("SELECT * FROM prospects WHERE id=?", (pid,))
    if not p:
        raise KeyError(f"prospect {pid} not found")
    return p


def get_product(pid: int) -> dict:
    p = db.one("SELECT * FROM products WHERE id=?", (pid,))
    if not p:
        raise KeyError(f"product {pid} not found")
    return p


def get_business(bid: int) -> dict:
    b = db.one("SELECT * FROM businesses WHERE id=?", (bid,))
    if not b:
        raise KeyError(f"business {bid} not found")
    return b


def product_block(product: dict, business: dict) -> str:
    profile = db.jload(business.get("profile_json"), {})
    icp = db.jload(product.get("icp_json"), {})
    return (
        f"Company: {business['name']}\nCompany profile: {db.jdump(profile) if profile else 'not generated yet'}\n"
        f"Product: {product['name']}\nDescription: {product['description']}\n"
        f"Key benefits: {', '.join(db.jload(product['benefits_json'], []))}\nPricing: {product['pricing'] or 'unknown'}\n"
        f"ICP: {db.jdump(icp) if icp else 'not generated yet'}"
    )


def prospect_block(p: dict) -> str:
    return (f"Name: {p['name']}\nTitle: {p['title']}\nCompany: {p['company']}\nIndustry: {p['industry']}\n"
            f"Employees: {p['employees']}\nLocation: {p['location']}")
