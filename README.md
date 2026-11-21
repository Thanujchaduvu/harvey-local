# Harvey Local

Document link: https://docs.google.com/document/d/1X_5ww3-M5um0UaVapm2tuFS4hpe468IH/edit?usp=sharing&ouid=102096746767866940566&rtpof=true&sd=true
Loom video: https://www.loom.com/share/ffae3cbac2974ac39214af25f821ee70


A multi-product AI sales agent that runs **entirely on your own computer**: local LLM inference through
Ollama (Qwen3, Apache-2.0), SQLite storage, FastAPI backend, local sentence-transformer embeddings, and a
dependency-free dashboard. No API keys, no per-token billing, no cloud inference, no silent fallback.

> Built for the EDXSO AI Engineer Intern Assignment 2. Read `docs/HARVEY_FORK_GUIDE.md` to merge this package
> into your fork of `ethanplusai/harvey` (the assignment requires a fork), and `docs/KNOWN_LIMITATIONS.md`
> before you record the demo.

## What it does

| # | Workflow | Where | Notes |
|---|---|---|---|
| 1 | Business profile from stored company docs | `workflows/profile.py` | Reads `data/company_docs/` or pasted text |
| 2 | Product-specific ICP | `workflows/icp.py` | One ICP per product, grounded in the profile |
| 3 | Prospect research from stored data | `workflows/research.py` | Quotes are verified verbatim against the source; invented quotes are rejected |
| 4 | Buying-signal classification | `workflows/signals.py` | Fixed taxonomy, strength 1-5, unverifiable evidence is capped |
| 5 | Problem statement | `workflows/problems.py` | Grounded in research + signals |
| 6 | Personalised email | `workflows/emails.py` | Draft only (nothing is sent). Quality checks + one automatic retry |
| 7 | Prospect scoring | `workflows/scoring.py` | Explainable: rules 30% + local embeddings 20% + signals 25% + model fit 25% |
| 8 | Reply classification | `workflows/replies.py` | 11 labels; opt-outs and auto-replies use deterministic rules |

## Quick start

```bash
# 1. Install Ollama (MIT) from https://ollama.com/download and start it:  ollama serve
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt            # or requirements-lite.txt (no PyTorch; uses labelled fallback embedder)
python scripts/download_models.py          # ONLINE, one time: pulls the right Qwen3 size + the embedding model
uvicorn app.main:app --host 127.0.0.1 --port 8000
# open http://127.0.0.1:8000  ->  "Load sample data"  ->  walk through the four sections
```

Check what model your machine gets: `python -m app.hardware`.

## Prove it works offline

```bash
python scripts/audit_no_cloud.py                       # 0 findings = no hosted-LLM endpoints/SDKs/keys
pytest -q                                              # plumbing tests (use a fake Ollama; see docs/TEST_EVIDENCE.md)
# disconnect Wi-Fi / unplug Ethernet, then:
python scripts/offline_acceptance.py --require-offline --limit 3
```
The acceptance script runs all eight workflows on your real model, blocks and records any non-loopback socket
attempt, and writes `var/acceptance_report.md` (attach it to your submission).

## Layout

```
app/                 FastAPI backend
  llm_client.py      the ONLY inference code: Ollama on localhost, refuses non-local hosts, logs every call
  taskqueue.py       SQLite queue used when Ollama is down
  hardware.py        RAM/CPU/GPU detection and model recommendation
  embeddings.py      sentence-transformers (local files only) + labelled fallback
  network_guard.py   socket-level block on non-loopback connections
  webresearch.py     online-only public-web fetch (httpx + BeautifulSoup, optional Playwright); no AI inside
  workflows/         the 8 workflows
frontend/            dashboard (plain HTML/CSS/JS, no CDN, works offline)
data/                SYNTHETIC sample company docs, prospects, conversations (inputs only)
scripts/             download_models.py, audit_no_cloud.py, offline_acceptance.py
tests/               pytest suite (+ fake_ollama.py test fixture, never used at runtime)
docs/                architecture, licences, cost statement, hardware, fork guide, limitations, demo script
```

## Configuration (`.env`, no secrets needed)

`OLLAMA_HOST` (must be loopback; private LAN IPs only with `HARVEY_ALLOW_LAN_OLLAMA=1`), `HARVEY_MODEL`
(empty = hardware recommendation), `HARVEY_EMBED_MODEL`, `HARVEY_STRICT_LOCAL` (default 1).

## API (all under `/api`)

`GET status | hardware | models | inference-log | queue | businesses | replies`,
`POST demo/seed`, `businesses`, `businesses/{id}/docs`, `businesses/{id}/profile`, `products`, `products/{id}/icp`,
`products/{id}/prospects/import`, `prospects/{id}/{research|signals|problem|score|email|run-all|fetch-web}`,
`replies/classify`, `replies/eval-sample`, `queue/process`. Interactive docs at `/docs`.
