# Demo script (about 8 minutes)

Record screen + terminal. Say what you are doing; show, don't claim.

| Time | Do | Show |
|---|---|---|
| 0:00 | `python scripts/audit_no_cloud.py` and `ollama list` | 0 findings; local Qwen3 model installed |
| 0:30 | `python -m app.hardware`, start the app | Detected RAM/CPU/GPU and recommended model |
| 1:00 | Dashboard -> **Load sample data** (say: synthetic inputs) | Two products under one business |
| 1:30 | **Generate business profile** | Profile generated; header tape shows `qwen3... -> 127.0.0.1:11434` |
| 2:15 | **Generate ICP** for Dispatchly, then Ledgerline | Different ICPs per product |
| 3:00 | Pipeline -> pick Maria Okafor -> **Run all stages** | Verified evidence, signals, problem, score breakdown, email |
| 4:30 | Open Pixel & Pine Studio (injection text) -> Run all | Low tier; injected instruction ignored |
| 5:00 | Replies -> run the 12 samples | Accuracy table; opt-out/out-of-office via rules |
| 5:45 | **Local trace** page + terminal `tail var/logs/app.log` | `LOCAL_INFERENCE ... endpoint=http://127.0.0.1:11434` lines |
| 6:15 | **Stop Ollama**, click a stage | Red chip, clear error, task queued, no cloud call; start Ollama -> **Process queue now** |
| 7:00 | **Disconnect Wi-Fi** (show it off), run `python scripts/offline_acceptance.py --require-offline` | PASS, `internet_reachable: false`, blocked attempts 0 |
| 8:00 | Show `var/acceptance_report.md` and `docs/KNOWN_LIMITATIONS.md` | Evidence and honest limits |
