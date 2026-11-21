#!/usr/bin/env python3
"""One-time ONLINE setup: pull the recommended Qwen3 model into Ollama and cache the embedding model.

After this finishes you can disconnect from the internet; nothing else is downloaded at run time.
Usage: python scripts/download_models.py [--model qwen3:4b] [--skip-embeddings]
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import os  # noqa: E402

os.environ["HARVEY_STRICT_LOCAL"] = "0"  # this script is the ONLY place downloads are allowed
for k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
    os.environ.pop(k, None)

from app import config, hardware  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--skip-embeddings", action="store_true")
    a = ap.parse_args()
    rec = hardware.recommend()
    model = a.model or config.MODEL or rec["model"]
    print(f"Hardware profile: {rec['profile']} -> {model}  ({rec['reason']})")
    for n in rec["notes"]:
        print("  note:", n)
    if not shutil.which("ollama"):
        print("ERROR: Ollama is not installed. Get it from https://ollama.com/download (MIT licence), then re-run.")
        return 1
    print(f"Pulling {model} via Ollama ...")
    if subprocess.run(["ollama", "pull", model]).returncode != 0:
        print("ERROR: `ollama pull` failed. Is `ollama serve` running?")
        return 1
    if not a.skip_embeddings:
        try:
            from sentence_transformers import SentenceTransformer
            print(f"Caching embedding model {config.EMBED_MODEL} ...")
            SentenceTransformer(config.EMBED_MODEL)
        except ImportError:
            print("sentence-transformers not installed: app will use the labelled hashing fallback. pip install sentence-transformers")
    print("Done. You can go offline now. Start the app with: uvicorn app.main:app --host 127.0.0.1 --port 8000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
