"""The ONLY place in this project that performs LLM inference.

* Talks exclusively to a local (or your own LAN) Ollama server.
* Refuses any non-local endpoint at construction time.
* Never falls back to another provider. If Ollama is down it raises
  OllamaUnavailable, and callers queue the task (see taskqueue.py).
* Every request is logged (SQLite + JSONL) with model, endpoint, token counts, latency.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import re
import time
from urllib.parse import urlparse

import httpx

from . import config, db, hardware

log = logging.getLogger("harvey.llm")


class OllamaUnavailable(RuntimeError):
    """Ollama is not reachable (or timed out). Callers must queue, never reroute."""


class ModelNotInstalled(OllamaUnavailable):
    pass


class NonLocalEndpointError(RuntimeError):
    pass


class BadModelOutput(RuntimeError):
    pass


def validate_endpoint(url: str) -> str:
    p = urlparse(url)
    host = p.hostname or ""
    if p.scheme not in ("http", "https"):
        raise NonLocalEndpointError(f"Unsupported scheme in {url!r}")
    if host != "localhost":
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            raise NonLocalEndpointError(
                f"{url!r} is not a local address. Harvey only talks to Ollama on this machine "
                "(or a private-IP host if HARVEY_ALLOW_LAN_OLLAMA=1)."
            ) from None
        if not (ip.is_loopback or (config.ALLOW_LAN and ip.is_private)):
            raise NonLocalEndpointError(f"{url!r} is not a loopback/private address; refusing.")
    return url.rstrip("/")


_THINK = re.compile(r"<think>.*?</think>", re.S)


def _validate(obj, schema) -> str | None:
    """Tiny structural check (required keys + basic types). Returns an error or None."""
    if schema.get("type") == "object":
        if not isinstance(obj, dict):
            return "expected an object"
        for k in schema.get("required", []):
            if k not in obj:
                return f"missing key {k!r}"
        for k, sub in schema.get("properties", {}).items():
            if k in obj and sub.get("type") == "array" and not isinstance(obj[k], list):
                return f"{k!r} must be a list"
    return None


def _extract_json(text: str):
    text = _THINK.sub("", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise


class OllamaClient:
    def __init__(self, host: str | None = None, transport: httpx.BaseTransport | None = None):
        self.host = validate_endpoint(host or config.OLLAMA_HOST)
        self._transport = transport

    def _http(self, timeout: float) -> httpx.Client:
        # trust_env=False: never pick up proxy env vars that could redirect traffic.
        return httpx.Client(base_url=self.host, timeout=timeout, transport=self._transport, trust_env=False)

    # ---- health / models -------------------------------------------------
    def health(self) -> dict:
        try:
            with self._http(3) as c:
                r = c.get("/api/tags")
                r.raise_for_status()
                models = [m["name"] for m in r.json().get("models", [])]
            return {"up": True, "host": self.host, "models": models}
        except (httpx.HTTPError, OSError, ValueError) as e:
            return {"up": False, "host": self.host, "models": [], "error": f"{type(e).__name__}: {e}"}

    def show(self, model: str) -> dict:
        with self._http(10) as c:
            r = c.post("/api/show", json={"model": model})
            r.raise_for_status()
            return r.json()

    def resolve_model(self, installed: list[str] | None = None) -> str:
        if config.MODEL:
            return config.MODEL
        rec = hardware.recommend()["model"]
        if installed is None:
            installed = self.health().get("models", [])
        if rec in installed or not installed:
            return rec
        order = [t for t, _ in hardware.LADDER]
        usable = [t for t in order[: order.index(rec) + 1] if t in installed]
        return usable[-1] if usable else rec

    # ---- inference -------------------------------------------------------
    def chat(self, *, task: str, system: str, prompt: str, schema: dict | None = None,
             model: str | None = None, temperature: float = 0.2, max_tokens: int = 900):
        model = model or self.resolve_model()
        num_ctx = hardware.recommend()["num_ctx"]
        payload = {
            "model": model,
            "stream": False,
            "think": False,  # Qwen3: skip chain-of-thought; structured output is enough
            "keep_alive": "10m",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": num_ctx},
        }
        if schema:
            payload["format"] = schema
        last_err = ""
        for attempt in (1, 2):
            if attempt == 2:
                payload["messages"].append({"role": "user", "content": f"Your last reply was invalid ({last_err}). Return ONLY valid JSON matching the schema."})
            data, lat = self._post(task, model, payload)
            content = data.get("message", {}).get("content", "")
            if not schema:
                return _THINK.sub("", content).strip()
            try:
                obj = _extract_json(content)
                err = _validate(obj, schema)
                if not err:
                    return obj
                last_err = err
            except (json.JSONDecodeError, ValueError) as e:
                last_err = f"not JSON: {e}"
            self._log(task, model, data, lat, ok=False, error=f"invalid output: {last_err}", preview=content)
        raise BadModelOutput(f"{task}: model returned invalid output twice ({last_err})")

    def _post(self, task: str, model: str, payload: dict):
        t0 = time.time()
        try:
            with self._http(config.LLM_TIMEOUT) as c:
                r = c.post("/api/chat", json=payload)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError, OSError) as e:
            msg = (f"Ollama is not reachable at {self.host} ({type(e).__name__}). "
                   "Start it with `ollama serve`. No cloud fallback is used; the task was queued.")
            self._log(task, model, {}, time.time() - t0, ok=False, error=msg)
            raise OllamaUnavailable(msg) from e
        lat = time.time() - t0
        if r.status_code == 404:
            msg = f"Model {model!r} is not installed. Run: ollama pull {model}"
            self._log(task, model, {}, lat, ok=False, error=msg)
            raise ModelNotInstalled(msg)
        if r.status_code >= 400:
            msg = f"Ollama returned HTTP {r.status_code}: {r.text[:200]}"
            self._log(task, model, {}, lat, ok=False, error=msg)
            raise OllamaUnavailable(msg)
        data = r.json()
        self._log(task, model, data, lat, ok=True, preview=data.get("message", {}).get("content", ""))
        return data, lat

    def _log(self, task, model, data, lat, *, ok, error="", preview=""):
        rec = {
            "ts": time.time(), "task": task, "model": model, "endpoint": f"{self.host}/api/chat",
            "prompt_tokens": data.get("prompt_eval_count", 0) or 0,
            "completion_tokens": data.get("eval_count", 0) or 0,
            "latency_ms": int(lat * 1000), "ok": 1 if ok else 0, "error": error,
            "output_preview": preview[:160],
        }
        try:
            db.run(
                "INSERT INTO inference_log(ts,task,model,endpoint,prompt_tokens,completion_tokens,latency_ms,ok,error,output_preview)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                tuple(rec[k] for k in ("ts", "task", "model", "endpoint", "prompt_tokens", "completion_tokens", "latency_ms", "ok", "error", "output_preview")),
            )
            config.LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(config.LOG_DIR / "inference.jsonl", "a") as f:
                f.write(json.dumps(rec) + "\n")
        except Exception:  # logging must never break inference
            log.exception("could not write inference log")
        log.info("LOCAL_INFERENCE task=%s model=%s endpoint=%s in=%s out=%s %sms ok=%s",
                 task, model, rec["endpoint"], rec["prompt_tokens"], rec["completion_tokens"], rec["latency_ms"], bool(ok))


_client: OllamaClient | None = None


def get_client() -> OllamaClient:
    global _client
    if _client is None:
        _client = OllamaClient()
    return _client


def set_client(c: OllamaClient | None) -> None:
    global _client
    _client = c


async def transport(prompt: str, *, agent: str = "", task: str = "", timeout: float = 120, expect_json: bool = False) -> str:
    """Drop-in for Harvey/Sellbird's `Brain(transport=...)` seam. Returns "" on failure."""
    import asyncio
    try:
        out = await asyncio.to_thread(
            get_client().chat, task=f"{agent}:{task}".strip(":") or "transport",
            system="You are Harvey, a sales assistant. Follow the instructions exactly.", prompt=prompt)
        return out if isinstance(out, str) else json.dumps(out)
    except (OllamaUnavailable, BadModelOutput) as e:
        log.warning("transport failed: %s", e)
        return ""
