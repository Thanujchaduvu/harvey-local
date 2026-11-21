PY ?= python3
.PHONY: setup models run test audit accept
setup:
	$(PY) -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
models:
	. .venv/bin/activate && $(PY) scripts/download_models.py
run:
	. .venv/bin/activate && uvicorn app.main:app --host 127.0.0.1 --port 8000
test:
	. .venv/bin/activate && pytest -q
audit:
	. .venv/bin/activate && $(PY) scripts/audit_no_cloud.py
accept:
	. .venv/bin/activate && $(PY) scripts/offline_acceptance.py --require-offline
