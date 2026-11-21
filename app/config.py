"""Central settings. Everything is local; there are no API keys in this project."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


OLLAMA_HOST = env("OLLAMA_HOST", "http://127.0.0.1:11434")
ALLOW_LAN = env("HARVEY_ALLOW_LAN_OLLAMA", "0") == "1"
MODEL = env("HARVEY_MODEL", "")  # empty -> hardware recommendation
EMBED_MODEL = env("HARVEY_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
STRICT_LOCAL = env("HARVEY_STRICT_LOCAL", "1") == "1"
QUEUE_WORKER = env("HARVEY_QUEUE_WORKER", "1") == "1"
LLM_TIMEOUT = float(env("HARVEY_LLM_TIMEOUT", "180"))

DATA_DIR = Path(env("HARVEY_DATA_DIR", str(ROOT / "data"))).resolve()
DB_PATH = Path(env("HARVEY_DB", str(ROOT / "var" / "harvey.db")))
LOG_DIR = Path(env("HARVEY_LOG_DIR", str(ROOT / "var" / "logs")))

if STRICT_LOCAL:
    # After the one-time download, the embedder must never touch the Hugging Face hub.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
