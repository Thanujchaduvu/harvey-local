"""Detect RAM / CPU / GPU and recommend a Qwen3 size (Apache-2.0 weights).

Approx. memory needed (Q4_K_M weights + KV-cache headroom), in GB.
"""
from __future__ import annotations

import platform
import shutil
import subprocess

import psutil

LADDER: list[tuple[str, float]] = [
    ("qwen3:0.6b", 1.0),
    ("qwen3:1.7b", 2.0),
    ("qwen3:4b", 3.5),
    ("qwen3:8b", 6.0),
    ("qwen3:14b", 10.5),
    ("qwen3:32b", 22.0),
]
HIGH_PERFORMANCE = {"qwen3:8b", "qwen3:14b", "qwen3:32b"}
STANDARD_DEFAULT = "qwen3:4b"       # ordinary 16 GB laptop, no GPU
HIGH_PERF_DEFAULT = "qwen3:14b"     # 12+ GB VRAM or 32+ GB unified memory


def _nvidia() -> list[dict]:
    if not shutil.which("nvidia-smi"):
        return []
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return []
    gpus = []
    for line in out.strip().splitlines():
        name, _, mem = line.partition(",")
        try:
            gpus.append({"name": name.strip(), "vram_gb": round(float(mem) / 1024, 1)})
        except ValueError:
            continue
    return gpus


def detect() -> dict:
    vm = psutil.virtual_memory()
    return {
        "os": platform.system(),
        "machine": platform.machine(),
        "ram_total_gb": round(vm.total / 1024**3, 1),
        "ram_available_gb": round(vm.available / 1024**3, 1),
        "cpu_physical": psutil.cpu_count(logical=False) or psutil.cpu_count() or 1,
        "cpu_logical": psutil.cpu_count() or 1,
        "gpus": _nvidia(),
        "apple_silicon": platform.system() == "Darwin" and platform.machine() == "arm64",
    }


def _largest_fitting(budget_gb: float, cap: str | None = None) -> str:
    best = LADDER[0][0]
    for tag, need in LADDER:
        if need <= budget_gb:
            best = tag
        if cap and tag == cap:
            break
    return best


def recommend(hw: dict | None = None) -> dict:
    hw = hw or detect()
    gpus = hw.get("gpus") or []
    if gpus:
        budget = max(g["vram_gb"] for g in gpus)
        model = _largest_fitting(budget)
        mode = f"GPU ({budget:g} GB VRAM)"
    elif hw.get("apple_silicon"):
        budget = hw["ram_total_gb"] * 0.65
        model = _largest_fitting(budget)
        mode = f"Apple unified memory ({hw['ram_total_gb']:g} GB, ~{budget:.0f} GB usable)"
    else:
        # CPU-only: be conservative — generation speed, not just fit, is the limit.
        budget = hw["ram_total_gb"] * 0.6
        cores = hw["cpu_physical"]
        cap = "qwen3:1.7b" if cores < 4 else ("qwen3:8b" if (cores >= 8 and hw["ram_total_gb"] >= 32) else "qwen3:4b")
        model = _largest_fitting(budget, cap)
        mode = f"CPU only ({hw['ram_total_gb']:g} GB RAM, {cores} cores)"
    profile = "high-performance" if model in HIGH_PERFORMANCE else "standard"
    notes = []
    if model == "qwen3:0.6b":
        notes.append("Very low memory: quality will be limited. Close other apps or use a bigger machine.")
    if not gpus and not hw.get("apple_silicon"):
        notes.append("No GPU detected: expect several seconds per response on CPU. This is supported.")
    return {
        "profile": profile,
        "model": model,
        "mode": mode,
        "num_ctx": 8192 if profile == "high-performance" else 4096,
        "reason": f"Largest Qwen3 size that fits {mode} with headroom.",
        "notes": notes,
        "ladder": [{"model": t, "needs_gb": n} for t, n in LADDER],
        "standard_default": STANDARD_DEFAULT,
        "high_performance_default": HIGH_PERF_DEFAULT,
    }


if __name__ == "__main__":
    import json
    hw = detect()
    print(json.dumps({"hardware": hw, "recommendation": recommend(hw)}, indent=2))
