"""TEST FIXTURE ONLY. A fake Ollama HTTP responder so the test-suite can run without a GPU/model.

It is never imported by the application. All application behaviour shown to users comes from a real
local Ollama model; these canned replies exist only to test plumbing (queueing, validation, guards).
"""
from __future__ import annotations

import json
import re

import httpx


def _snippet(prompt: str) -> str:
    m = re.search(r"<untrusted_data>\n(.*?)\n</untrusted_data>", prompt, re.S)
    return " ".join(m.group(1).split()[:12]) if m else "unknown"


def _reply_for(title: str, prompt: str) -> dict:
    snip = _snippet(prompt)
    name = re.search(r"Name: (\S+)", prompt)
    first = name.group(1) if name else "there"
    return {
        "profile": {"summary": "s", "value_proposition": "v", "target_customers": ["smb"], "differentiators": ["fast"],
                    "proof_points": ["6 day onboarding"], "tone": "plain", "information_gaps": []},
        "icp": {"summary": "Field service operators", "industries": ["HVAC and plumbing services", "Solar installation"],
                "company_size": {"min_employees": 20, "max_employees": 250}, "titles": ["Operations Manager", "COO", "Owner"],
                "geographies": ["US"], "pain_points": ["missed arrival windows"], "buying_triggers": ["hiring dispatchers"],
                "keywords": ["dispatch"], "disqualifiers": ["non-service business"]},
        "research": {"company_summary": "A service company.", "offerings": ["service"], "tools_mentioned": [],
                     "recent_events": [], "pain_hints": ["scheduling"], "evidence": [snip, "this quote is invented and absent"]},
        "signals": {"signals": [{"type": "hiring", "strength": 4, "evidence": snip, "why_it_matters": "growth"},
                                {"type": "funding", "strength": 5, "evidence": "totally fabricated quote not in text", "why_it_matters": "x"}]},
        "problem": {"problem_statement": "Scheduling is manual.", "business_impact": "overtime", "why_now": "growth",
                    "product_angle": "routing", "confidence": "medium"},
        "fit": {"fit_score": 8, "reasoning": "good fit", "risks": []},
        "email": {"subject": "Dispatch capacity at growth stage",
                  "body": f"Hi {first}, I saw you are hiring dispatchers while opening two new counties. That usually means scheduling gets harder "
                          "before it gets easier, especially when jobs live in a shared spreadsheet and arrival windows slip during busy weeks. "
                          "Dispatchly gives dispatchers drag-and-drop, route-aware scheduling and sends customers arrival-window texts, and teams "
                          "are typically live in about six working days. Would a 15-minute call next week be useful?",
                  "personalization_points": ["hiring dispatchers"]},
        "reply": {"label": "interested", "confidence": 0.8, "rationale": "asks to learn more", "suggested_action": "book call",
                  "suggested_reply": "Great, here are two times."},
    }[title]


def make_handler(calls: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3:4b"}]})
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"license": "Apache License\nVersion 2.0"})
        body = json.loads(request.content)
        title = body["format"]["title"]
        if calls is not None:
            calls.append({"title": title, "host": request.url.host, "model": body["model"]})
        content = _reply_for(title, body["messages"][-1]["content"])
        return httpx.Response(200, json={"message": {"content": json.dumps(content)}, "prompt_eval_count": 111, "eval_count": 55})
    return handler


def working_transport(calls=None) -> httpx.MockTransport:
    return httpx.MockTransport(make_handler(calls))


def down_transport() -> httpx.MockTransport:
    def h(request):
        raise httpx.ConnectError("connection refused")
    return httpx.MockTransport(h)
