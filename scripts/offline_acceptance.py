#!/usr/bin/env python3
"""Final Offline Acceptance Test runner (assignment section 8).

Runs the eight local-AI workflows against YOUR real local Ollama model, with the socket guard
installed so any attempt to reach a non-loopback address is blocked and recorded. Disconnect Wi-Fi first.

Usage: python scripts/offline_acceptance.py [--limit 3] [--require-offline]
Writes var/acceptance_report.json and var/acceptance_report.md (attach them as test evidence).
"""
import argparse
import json
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config, db, network_guard, seed  # noqa: E402
from app.llm_client import OllamaUnavailable, get_client  # noqa: E402
from app.workflows import emails, icp, problems, profile, replies, research, scoring, signals  # noqa: E402,F401


def internet_reachable() -> bool:
    try:
        with network_guard.allow_external():
            socket.create_connection(("1.1.1.1", 53), timeout=2).close()
        return True
    except OSError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=3, help="prospects per product (default 3)")
    ap.add_argument("--require-offline", action="store_true", help="fail if the internet is reachable")
    a = ap.parse_args()

    out_dir = config.ROOT / "var"
    out_dir.mkdir(exist_ok=True)
    db.init(out_dir / "acceptance.db")
    network_guard.install()
    report = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "internet_reachable": internet_reachable(), "steps": []}
    c = get_client()
    h = c.health()
    report["ollama"] = h
    report["model"] = c.resolve_model(h.get("models"))
    print(f"Internet reachable: {report['internet_reachable']} | Ollama up: {h['up']} | model: {report['model']}")
    if not h["up"]:
        print("FAIL: Ollama is not running (start it with `ollama serve`).")
        return 2
    if a.require_offline and report["internet_reachable"]:
        print("FAIL: internet is still reachable. Disconnect Wi-Fi/Ethernet and re-run.")
        return 3

    def step(name, fn):
        t0 = time.time()
        try:
            res = fn()
            report["steps"].append({"step": name, "ok": True, "seconds": round(time.time() - t0, 1), "sample": json.dumps(res)[:400]})
            print(f"  PASS  {name}  ({time.time() - t0:.1f}s)")
            return res
        except Exception as e:  # noqa: BLE001
            report["steps"].append({"step": name, "ok": False, "error": f"{type(e).__name__}: {e}"})
            print(f"  FAIL  {name}: {type(e).__name__}: {e}")

    s = seed.seed_demo()
    bid = s["business_id"]
    step("1 Business profile from locally stored documents", lambda: profile.generate_profile({"business_id": bid}))
    pids = s.get("product_ids") or {r["name"]: r["id"] for r in db.rows("SELECT id,name FROM products")}
    for name, pid in pids.items():
        step(f"2 Product-specific ICP [{name}]", lambda pid=pid: icp.generate_icp({"product_id": pid}))
    for name, pid in pids.items():
        for p in db.rows("SELECT id,name FROM prospects WHERE product_id=? LIMIT ?", (pid, a.limit)):
            tag = f"[{name}/{p['name']}]"
            step(f"3 Prospect research from stored data {tag}", lambda p=p: research.research_prospect({"prospect_id": p["id"]}))
            step(f"4 Buying-signal classification {tag}", lambda p=p: signals.classify_signals({"prospect_id": p["id"]}))
            step(f"5 Problem statement {tag}", lambda p=p: problems.generate_problem({"prospect_id": p["id"]}))
            step(f"7 Prospect scoring {tag}", lambda p=p: scoring.score_prospect({"prospect_id": p["id"]}))
            step(f"6 Personalised email {tag}", lambda p=p: emails.generate_email({"prospect_id": p["id"]}))
    ev = step("8 Reply classification on sample conversations", replies.eval_samples)
    if ev:
        report["reply_accuracy"] = ev.get("accuracy")

    log = db.rows("SELECT model, endpoint, COUNT(*) n, SUM(prompt_tokens) tin, SUM(completion_tokens) tout, SUM(ok) ok FROM inference_log GROUP BY model, endpoint")
    report["inference_summary"] = log
    report["blocked_external_connection_attempts"] = len(network_guard.violations)
    report["all_inference_local"] = all(r["endpoint"].startswith(("http://127.0.0.1", "http://localhost")) for r in log) if log else False
    failed = [s for s in report["steps"] if not s["ok"]]
    report["passed"] = not failed and not network_guard.violations and report["all_inference_local"]
    (out_dir / "acceptance_report.json").write_text(json.dumps(report, indent=2))
    md = [f"# Offline acceptance report ({report['started']})", "",
          f"* Internet reachable during test: **{report['internet_reachable']}**",
          f"* Model: `{report['model']}`  | Ollama: `{h['host']}`",
          f"* External connection attempts blocked: **{report['blocked_external_connection_attempts']}**",
          f"* All inference requests went to localhost: **{report['all_inference_local']}**",
          f"* Reply-classification accuracy on bundled samples: **{report.get('reply_accuracy')}**",
          f"* Steps passed: {len(report['steps']) - len(failed)}/{len(report['steps'])}", "",
          "| model | endpoint | requests | prompt tok | completion tok |", "|---|---|---|---|---|"]
    md += [f"| {r['model']} | {r['endpoint']} | {r['n']} | {r['tin']} | {r['tout']} |" for r in log]
    md += ["", "## Steps", ""] + [f"- {'PASS' if s['ok'] else 'FAIL'} {s['step']}" + (f" - {s.get('error')}" if not s["ok"] else "") for s in report["steps"]]
    (out_dir / "acceptance_report.md").write_text("\n".join(md) + "\n")
    print(f"\nOVERALL: {'PASS' if report['passed'] else 'FAIL'}  -> var/acceptance_report.md")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
