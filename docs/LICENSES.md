# Licences of models, libraries and tools

Verify each entry against the exact version you install (`pip show <pkg>`, Ollama model card / `ollama show <model>`); the app also displays the licence header Ollama reports for each installed model (Local trace page).

| Component | Role | Licence |
|---|---|---|
| Qwen3 0.6B / 1.7B / 4B / 8B / 14B / 32B (Qwen team) | Local LLM weights | Apache-2.0 (per the Qwen3 model cards; confirm at pull time) |
| Ollama | Local inference server | MIT |
| sentence-transformers/all-MiniLM-L6-v2 | Embedding model | Apache-2.0 |
| sentence-transformers | Embedding library | Apache-2.0 |
| PyTorch (dependency of sentence-transformers) | Tensor library | BSD-3-Clause style |
| FastAPI | Backend | MIT |
| Starlette / Uvicorn | ASGI | BSD-3-Clause |
| Pydantic | Validation | MIT |
| httpx | HTTP client (Ollama + web fetch) | BSD-3-Clause |
| psutil | Hardware detection | BSD-3-Clause |
| NumPy | Vectors | BSD-3-Clause |
| Beautiful Soup 4 | HTML text extraction | MIT |
| Playwright (optional) | JS-rendered pages, online research only | Apache-2.0 |
| Chromium (optional, via Playwright) | Headless browser | BSD-3-Clause plus bundled third-party licences |
| SQLite | Storage | Public domain |
| pytest | Tests | MIT |
| Dashboard (HTML/CSS/JS) | UI | Original code, no third-party libraries or fonts |
| **This package** | | MIT |
| **Harvey / Sellbird (ethanplusai/harvey)** | Required fork base | **AGPL-3.0** (see its `LICENSE`) |

**Not open source:** hosted models (GPT, Claude, Gemini) and any "open-weight" model under a custom licence (e.g. Llama community licence). None are used. If you swap in another model, record its licence here first.

**AGPL note (not legal advice):** merging this MIT code into the AGPL-3.0 Harvey fork makes the combined work AGPL-3.0, including a source-offer obligation if you host a modified version for others over a network.
Scrapy is named in the assignment but is not used; httpx + BeautifulSoup (+ optional Playwright) cover the permitted research needs.
