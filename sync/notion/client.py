"""Notion API client: settings from .env, the database ids in data/notion/config.json, and small text helpers."""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # project root: .env, data/notion/
DATA_DIR = ROOT / "data" / "notion"
CONFIG = DATA_DIR / "config.json"
API = "https://api.notion.com/v1"
VERSION = "2022-06-28"


def _ssl_context() -> ssl.SSLContext:
    # python.org builds on macOS ship without CA certs; fall back to certifi or the system bundle
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    if Path("/etc/ssl/cert.pem").exists():
        return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    return ssl.create_default_context()


SSL_CTX = _ssl_context()


def env() -> dict[str, str]:
    vals = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def page_id(raw: str) -> str:
    """Accept a bare id, a dashed id or a full Notion URL."""
    m = re.findall(r"[0-9a-f]{32}", raw.replace("-", "").lower())
    if not m:
        raise SystemExit("NOTION_PAGE_ID in .env doesn't look like a Notion page id")
    return m[-1]


def home_page() -> str:
    return page_id(env().get("NOTION_PAGE_ID", ""))


def request(method: str, path: str, body: dict | None = None) -> dict:
    token = env().get("NOTION_TOKEN")
    if not token:
        raise SystemExit("Add NOTION_TOKEN to .env first")
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Notion-Version": VERSION,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Notion {method} {path} -> HTTP {e.code}: {e.read()[:300]!r}") from None


def query(db: str, body: dict | None = None) -> list[dict]:
    """All pages of a database query (follows pagination)."""
    out, cursor = [], None
    while True:
        res = request("POST", f"/databases/{db}/query", {"page_size": 100, **(body or {}), **({"start_cursor": cursor} if cursor else {})})
        out += res["results"]
        if not res.get("has_more"):
            return out
        cursor = res["next_cursor"]


def children(block: str) -> list[dict]:
    out, cursor = [], None
    while True:
        res = request("GET", f"/blocks/{block}/children?page_size=100" + (f"&start_cursor={cursor}" if cursor else ""))
        out += res["results"]
        if not res.get("has_more"):
            return out
        cursor = res["next_cursor"]


def config() -> dict:
    return json.loads(CONFIG.read_text()) if CONFIG.exists() else {}


def save_config(cfg: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=1))


def rt(text: str, bold: bool = False) -> list[dict]:
    """Notion rich text from a plain string."""
    return [{"type": "text", "text": {"content": text[:1900]}, **({"annotations": {"bold": True}} if bold else {})}] if text else []


def plain(prop_or_block: dict) -> str:
    """Plain text of a title/rich_text property or a block's rich_text."""
    parts = prop_or_block.get("title") or prop_or_block.get("rich_text") or []
    return "".join(x.get("plain_text", "") for x in parts)
