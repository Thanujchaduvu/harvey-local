# Test evidence (fill in from YOUR runs; do not submit placeholders)

Generate the artefacts, then paste outputs or link files here and add screenshots to `docs/screenshots/`.

| Evidence | Command | File / output to attach |
|---|---|---|
| No hosted-LLM code | `python scripts/audit_no_cloud.py` | `var/audit_report.txt` (expect 0 findings) |
| Plumbing tests | `pytest -q` | terminal output (15 tests; uses fake Ollama, which proves routing/guards, not model quality) |
| Hardware recommendation | `python -m app.hardware` | JSON output + screenshot of Local trace |
| Local inference logs | after any run | `var/logs/inference.jsonl`, `var/logs/app.log` (look for `LOCAL_INFERENCE`) |
| Offline acceptance | `python scripts/offline_acceptance.py --require-offline` | `var/acceptance_report.md` + `.json` |
| Failure handling | stop `ollama serve`, run a stage | screenshot of red chip + queued toast; `GET /api/queue` |
| Sample outputs | dashboard | screenshots of profile, ICPs, signals, score, email, reply table |

## Results (fill in)
* Machine / model / profile: ...
* Acceptance report summary (steps passed, blocked attempts, internet_reachable): ...
* Reply-classification accuracy on the 12 samples: ...
* Notable failures and what you changed: ...
