"""Local embeddings via sentence-transformers (Apache-2.0).

Loaded with local_files_only=True so it works offline after `scripts/download_models.py`.
If unavailable, a deterministic hashing embedder is used and *labelled as such*
in every score breakdown. It is a non-neural fallback, not a substitute for the real model.
"""
from __future__ import annotations

import logging
import re
import zlib

import numpy as np

from . import config

log = logging.getLogger("harvey.embed")
DIM = 512


class HashingEmbedder:
    name = "hashing-fallback (non-neural)"

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            toks = re.findall(r"[a-z0-9]+", t.lower())
            grams = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
            for g in grams:
                h = zlib.crc32(g.encode())
                out[i, h % DIM] += 1.0 if (h >> 16) & 1 else -1.0
            n = np.linalg.norm(out[i])
            if n:
                out[i] /= n
        return out


class STEmbedder:
    def __init__(self, model):
        self._m = model
        self.name = f"sentence-transformers:{config.EMBED_MODEL}"

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self._m.encode(texts, normalize_embeddings=True, show_progress_bar=False))


_emb = None
_reason = ""


def get_embedder():
    global _emb, _reason
    if _emb is None:
        try:
            from sentence_transformers import SentenceTransformer
            _emb = STEmbedder(SentenceTransformer(config.EMBED_MODEL, local_files_only=True))
        except Exception as e:  # not installed, or model not downloaded yet
            _reason = f"{type(e).__name__}: {str(e)[:120]}"
            log.warning("sentence-transformers unavailable (%s); using hashing fallback", _reason)
            _emb = HashingEmbedder()
    return _emb


def fallback_reason() -> str:
    return _reason


def cosine(a: str, b: str) -> float:
    e = get_embedder().encode([a, b])
    return float(np.dot(e[0], e[1]))
