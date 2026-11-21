#!/usr/bin/env python3
"""Fail if the codebase contains any hosted-LLM dependency. Works on this repo or on your Harvey fork.

Usage: python scripts/audit_no_cloud.py [path]   (default: repo root)
Writes var/audit_report.txt and exits 1 on any finding.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "var", "__pycache__", "docs", "tests", ".pytest_cache"}
EXTS = {".py", ".js", ".ts", ".html", ".toml", ".yaml", ".yml", ".json", ".sh", ".cfg", ".txt", ".env", ".example", ""}
PATTERNS = {
    "OpenAI endpoint/SDK": r"api\.openai\.com|openai\.azure\.com|\bimport openai\b|\bfrom openai\b|OPENAI_API_KEY|langchain_openai",
    "Anthropic endpoint/SDK": r"api\.anthropic\.com|\bimport anthropic\b|\bfrom anthropic\b|ANTHROPIC_API_KEY|@anthropic-ai",
    "Gemini/Google AI": r"generativelanguage\.googleapis|google\.generativeai|GEMINI_API_KEY|GOOGLE_API_KEY|vertexai",
    "Other hosted inference": r"openrouter\.ai|api\.groq\.com|api\.together\.xyz|api\.cohere|api-inference\.huggingface|api\.mistral\.ai|litellm|bedrock-runtime",
    "Claude/Codex CLI or subscription": r"\bclaude\s+(-p|--print)\b|\"claude\"\s*,|\bcodex\s+exec\b|CLAUDE_CODE|CODEX_|provider:\s*[\"']?(claude|codex)\b",
}
DEP_NAMES = re.compile(r"^\s*[\"']?(openai|anthropic|google-generativeai|litellm|langchain-openai|cohere|groq|mistralai)\b", re.I | re.M)

findings = []
for f in TARGET.rglob("*"):
    if not f.is_file() or any(part in SKIP_DIRS for part in f.relative_to(TARGET).parts) or f.resolve() == Path(__file__).resolve():
        continue
    if f.suffix not in EXTS and f.name not in {"Dockerfile"}:
        continue
    try:
        text = f.read_text(errors="ignore")
    except OSError:
        continue
    for label, pat in PATTERNS.items():
        for m in re.finditer(pat, text):
            line = text.count("\n", 0, m.start()) + 1
            findings.append((label, str(f.relative_to(TARGET)), line, m.group(0)))
    if f.name.startswith("requirements") or f.name == "pyproject.toml":
        for m in DEP_NAMES.finditer(text):
            findings.append(("Paid-LLM dependency", str(f.relative_to(TARGET)), text.count("\n", 0, m.start()) + 1, m.group(1)))

lines = [f"Cloud-LLM audit of {TARGET}", f"Findings: {len(findings)}"]
for label, path, line, hit in sorted(findings):
    lines.append(f"  [{label}] {path}:{line}  {hit}")
if not findings:
    lines.append("PASS: no hosted-LLM endpoints, SDKs, API-key variables or CLI subscriptions found.")
report = "\n".join(lines)
print(report if len(lines) < 80 else "\n".join(lines[:80]) + f"\n  ... {len(lines) - 80} more (see var/audit_report.txt)")
(ROOT / "var").mkdir(exist_ok=True)
(ROOT / "var" / "audit_report.txt").write_text(report + "\n")
sys.exit(1 if findings else 0)
