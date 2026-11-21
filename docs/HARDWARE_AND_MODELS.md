# Hardware requirements and model selection

`app/hardware.py` detects RAM, CPU cores, NVIDIA GPUs (`nvidia-smi`) and Apple silicon, then picks the largest Qwen3 size that fits with headroom. Run `python -m app.hardware` or open **Local trace** in the dashboard.

| Qwen3 tag | Approx. memory needed (Q4) | Typical machine |
|---|---|---|
| 0.6b | 1 GB | Very old / 4 GB RAM (limited quality) |
| 1.7b | 2 GB | 8 GB RAM laptop, no GPU |
| **4b** | 3.5 GB | **Standard profile: ordinary 16 GB laptop, no GPU** |
| 8b | 6 GB | 32 GB RAM + 8 cores, or 8 GB VRAM |
| **14b** | 10.5 GB | **High-performance profile: 12+ GB VRAM or 32 GB Apple silicon** |
| 32b | 22 GB | 24 GB+ VRAM |

Logic: GPU present -> budget = VRAM. Apple silicon -> 65% of unified memory. CPU only -> 60% of RAM, capped by cores (below 4 cores: 1.7b; 8+ cores and 32+ GB: up to 8b; otherwise up to 4b) because CPU speed, not just fit, is the constraint. Context window: 4096 (standard) or 8192 (high-performance).

Override with `HARVEY_MODEL=qwen3:8b`. If the recommended model is not installed but a smaller Qwen3 is, the app uses the largest installed one and shows the mismatch in the header. No GPU is required. Expect several seconds per response on CPU; the full pipeline for one prospect makes 5 model calls.
The memory figures are approximations for planning, not measurements; check yours with `ollama ps`.
