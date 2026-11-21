# Known limitations (disclose these in your submission)

**Verification status (read first)**
* The author of this package could not run Ollama or download models in the build environment. The automated tests exercise the plumbing against a **fake Ollama** fixture (`tests/fake_ollama.py`, test-only). They prove routing, queueing, validation, guards and persistence, **not** model quality. You must run `scripts/offline_acceptance.py` on your own machine with a real model and attach the report.
* The sentence-transformers path was not exercised in the build environment (the labelled hashing fallback was). Run `scripts/download_models.py` and confirm the header chip says "sentence-transformers".
* The dashboard was syntax-checked but not browser-tested by the author. Click through it once before recording.

**Product**
* Emails are drafts. Nothing is sent; there is no SMTP/Gmail integration.
* Sample prospects, companies and conversations are **synthetic input data**. All analysis shown is generated at run time.
* Small models (0.6b-1.7b) can be weak at JSON-schema tasks and nuance. Invalid output is retried once, then surfaced as an error.
* Scoring weights and the cosine rescale are heuristics chosen by hand, not trained on conversion data.
* Reply labels are single-label; mixed replies (interest + objection) get one label.
* No authentication: the API assumes it is bound to 127.0.0.1. Do not expose it to a network.
* The queue worker is in-process; tasks survive restarts in SQLite but are only replayed while the app runs.
* Scrapy is not used. Playwright is optional and not installed by default. The socket guard covers the Python process only (a Playwright browser process is not covered).
* Not yet merged into the Harvey fork (see `HARVEY_FORK_GUIDE.md`).
