"""JSON Schemas passed to Ollama's structured-output `format` parameter."""

def _obj(title, props, required=None):
    return {"title": title, "type": "object", "properties": props, "required": required or list(props)}

S = {"type": "string"}
def L(item=S): return {"type": "array", "items": item}

SIGNAL_TYPES = ["hiring", "funding", "expansion", "leadership_change", "tech_adoption",
                "pain_expressed", "compliance_event", "competitor_mention"]
REPLY_LABELS = ["interested", "meeting_request", "pricing_objection", "timing_objection", "has_solution",
                "not_interested", "unsubscribe", "out_of_office", "referral", "question", "other"]

PROFILE = _obj("profile", {
    "summary": S, "value_proposition": S, "target_customers": L(), "differentiators": L(),
    "proof_points": L(), "tone": S, "information_gaps": L()})

ICP = _obj("icp", {
    "summary": S, "industries": L(), "company_size": _obj("size", {"min_employees": {"type": "integer"}, "max_employees": {"type": "integer"}}),
    "titles": L(), "geographies": L(), "pain_points": L(), "buying_triggers": L(), "keywords": L(), "disqualifiers": L()})

RESEARCH = _obj("research", {
    "company_summary": S, "offerings": L(), "tools_mentioned": L(), "recent_events": L(),
    "pain_hints": L(), "evidence": L()})

SIGNALS = _obj("signals", {"signals": L(_obj("signal", {
    "type": {"type": "string", "enum": SIGNAL_TYPES}, "strength": {"type": "integer", "minimum": 1, "maximum": 5},
    "evidence": S, "why_it_matters": S}))})

PROBLEM = _obj("problem", {
    "problem_statement": S, "business_impact": S, "why_now": S, "product_angle": S,
    "confidence": {"type": "string", "enum": ["low", "medium", "high"]}})

FIT = _obj("fit", {"fit_score": {"type": "integer", "minimum": 0, "maximum": 10}, "reasoning": S, "risks": L()})

EMAIL = _obj("email", {"subject": S, "body": S, "personalization_points": L()})

REPLY = _obj("reply", {
    "label": {"type": "string", "enum": REPLY_LABELS}, "confidence": {"type": "number"},
    "rationale": S, "suggested_action": S, "suggested_reply": S})
