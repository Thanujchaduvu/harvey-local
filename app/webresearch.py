"""Public-web research (ONLINE ONLY). Deliberately separate from AI inference.

* This module never imports the inference client; tests enforce that.
* It is the only code allowed to open non-local sockets (via network_guard.allow_external()).
* Polite by design: robots.txt is honoured, identifiable user-agent, SSRF guard, size limit.
* Output is plain text stored on the prospect row; the local model reads it later, offline.
"""
from __future__ import annotations

import ipaddress
import socket
import time
from urllib import robotparser
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from . import db, network_guard

UA = "HarveyLocalBot/0.1 (sales research; honours robots.txt)"
MAX_CHARS = 20000


class WebResearchUnavailable(RuntimeError):
    pass


def _check_public(url: str) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise WebResearchUnavailable("Only http(s) URLs are allowed.")
    try:
        infos = socket.getaddrinfo(p.hostname, None)
    except socket.gaierror as e:
        raise WebResearchUnavailable(f"Cannot resolve {p.hostname}: no internet or bad hostname.") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise WebResearchUnavailable("Refusing to fetch private/loopback addresses.")


def _allowed_by_robots(url: str, client: httpx.Client) -> bool:
    p = urlparse(url)
    rp = robotparser.RobotFileParser()
    try:
        r = client.get(f"{p.scheme}://{p.netloc}/robots.txt")
        if r.status_code >= 400:
            return True
        rp.parse(r.text.splitlines())
    except httpx.HTTPError:
        return True
    return rp.can_fetch(UA, url)


def extract_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "nav", "footer", "header", "form", "svg"]):
        t.decompose()
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    text = " ".join(soup.get_text(" ").split())
    return title, text[:MAX_CHARS]


def fetch_page_text(url: str, render_js: bool = False, timeout: float = 15) -> dict:
    with network_guard.allow_external():
        _check_public(url)
        try:
            with httpx.Client(timeout=timeout, headers={"User-Agent": UA}, follow_redirects=True, max_redirects=3) as c:
                if not _allowed_by_robots(url, c):
                    raise WebResearchUnavailable("robots.txt disallows fetching this page.")
                if render_js:
                    html = _render_playwright(url, timeout)
                else:
                    r = c.get(url)
                    r.raise_for_status()
                    html = r.text
        except httpx.HTTPError as e:
            raise WebResearchUnavailable(f"Fetch failed ({type(e).__name__}). Offline? Local data is still usable.") from e
    title, text = extract_text(html)
    return {"url": url, "title": title, "text": text, "fetched_at": time.time()}


def _render_playwright(url: str, timeout: float) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise WebResearchUnavailable("Playwright is not installed (optional): pip install playwright && playwright install chromium") from e
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        try:
            page = b.new_page(user_agent=UA)
            page.goto(url, timeout=int(timeout * 1000), wait_until="networkidle")
            return page.content()
        finally:
            b.close()


def attach_to_prospect(prospect_id: int, url: str, render_js: bool = False) -> dict:
    page = fetch_page_text(url, render_js)
    p = db.one("SELECT raw_text FROM prospects WHERE id=?", (prospect_id,))
    if p is None:
        raise KeyError("prospect not found")
    merged = ((p["raw_text"] or "") + f"\n\n[Fetched from {url}]\n" + page["text"]).strip()
    db.update("prospects", prospect_id, raw_text=merged, source=f"web:{url}")
    return {"url": url, "title": page["title"], "chars": len(page["text"])}
