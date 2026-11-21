# Cost and dependency statement

**Marginal cost per request: zero.** There are no API keys, no billing endpoints and no token metering anywhere in the code. Costs are your own electricity and hardware.

## Requirement-by-requirement
| Assignment requirement | How it is met | Evidence |
|---|---|---|
| No external LLM API calls | The only inference code is `app/llm_client.py`; it posts to Ollama on loopback | `python scripts/audit_no_cloud.py` -> 0 findings; `var/audit_report.txt` |
| No paid inference endpoints | Endpoint validator rejects non-local hosts at construction time | `tests/test_core.py::test_endpoint_guard_rejects_cloud_and_public_ips` |
| No Claude/Codex dependency | No SDKs, CLIs, keys or subscriptions; audit also scans for CLI usage | Audit report |
| No token billing | Local model; token counts are logged only for transparency | `inference_log` table |
| All requests to local inference | Every call logged with endpoint; `network_guard` blocks everything non-loopback | `var/logs/inference.jsonl`, `var/acceptance_report.md` ("all inference local: True", "blocked attempts: 0") |
| Works offline | Models cached; hub offline flags; data in SQLite | Acceptance test run with Wi-Fi off |
| Logs showing local inference | Console + `var/logs/app.log` lines `LOCAL_INFERENCE task=... endpoint=http://127.0.0.1:11434/api/chat ...`; dashboard tape and Trace page | Screen recording |
| No silent fallback | On failure: explicit error + queue; no alternate provider code exists | `test_ollama_down_queues_and_recovers` |
| No paid prospecting/enrichment API | Prospect data comes from imported files or user-triggered public page fetch | `webresearch.py` |

## Every place the app can touch a network
1. **Ollama on 127.0.0.1:11434** (inference). Always local.
2. **`POST /api/prospects/{id}/fetch-web`** (optional, user-triggered, public pages, robots.txt honoured, contains no AI).
3. **`scripts/download_models.py`** (one-time install step: Ollama model pull and embedding model cache).
Nothing else. Browser-side, the dashboard loads no CDN scripts, fonts or images.

## Service limitations to disclose
* Initial setup needs internet (Ollama install, model pull, pip). Model downloads are free but large (about 2.5 GB for qwen3:4b plus about 90 MB for the embedder, approximate).
* Public-web fetching depends on third-party sites staying reachable and permitting access.
* Output quality depends on the local model size chosen for your hardware.
