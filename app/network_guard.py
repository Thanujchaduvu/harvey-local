"""Socket-level proof that the AI process never talks to the internet.

When STRICT_LOCAL is on, every outbound connect() to a non-loopback address
raises ExternalNetworkBlocked and is recorded. The only exception is the
explicit `allow_external()` context used by app/webresearch.py, which is the
sole module permitted to fetch public web pages (and never calls an LLM).
"""
from __future__ import annotations

import ipaddress
import json
import socket
import threading
import time
from contextlib import contextmanager

from . import config

_local = threading.local()
_installed = False
_orig_connect = socket.socket.connect
_orig_connect_ex = socket.socket.connect_ex
violations: list[dict] = []


class ExternalNetworkBlocked(PermissionError):
    pass


def _allowed(addr) -> bool:
    if not isinstance(addr, tuple) or not addr:
        return True  # AF_UNIX etc.
    host = addr[0]
    if isinstance(host, bytes):
        host = host.decode(errors="ignore")
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if ip.is_loopback:
        return True
    return bool(config.ALLOW_LAN and ip.is_private)


def _check(addr) -> None:
    if getattr(_local, "allow", 0) > 0 or _allowed(addr):
        return
    rec = {"ts": time.time(), "address": str(addr)}
    violations.append(rec)
    try:
        config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(config.LOG_DIR / "network_violations.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass
    raise ExternalNetworkBlocked(f"Blocked outbound connection to {addr}: strict local mode is on.")


def _connect(self, addr):
    _check(addr)
    return _orig_connect(self, addr)


def _connect_ex(self, addr):
    _check(addr)
    return _orig_connect_ex(self, addr)


def install() -> bool:
    global _installed
    if _installed or not config.STRICT_LOCAL:
        return _installed
    socket.socket.connect = _connect  # type: ignore[assignment]
    socket.socket.connect_ex = _connect_ex  # type: ignore[assignment]
    _installed = True
    return True


def uninstall() -> None:
    global _installed
    socket.socket.connect = _orig_connect  # type: ignore[assignment]
    socket.socket.connect_ex = _orig_connect_ex  # type: ignore[assignment]
    _installed = False


def is_installed() -> bool:
    return _installed


@contextmanager
def allow_external():
    """Only for public-web research. Never wrap an LLM call in this."""
    _local.allow = getattr(_local, "allow", 0) + 1
    try:
        yield
    finally:
        _local.allow -= 1
