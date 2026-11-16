"""Garmin Connect Personal API client: paths, SSL, the API-key -> token exchange, GET with retries on
rate limits, and the CSV helpers the sync modules share."""

from __future__ import annotations

import base64
import csv
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]  # project root: .env, data/garmin/


DATA_DIR = ROOT / "data" / "garmin"


TOKEN_CACHE = ROOT / ".garmin_token.json"


BASE_URL = "https://personal.connectapi.garmin.com"


ACTIVITIES_CSV = DATA_DIR / "activities.csv"


DAILY_CSV = DATA_DIR / "daily.csv"


LOAD_CSV = DATA_DIR / "training_load.csv"


ZONES_CSV = DATA_DIR / "hr_zones.csv"


CYCLE_CSV = DATA_DIR / "cycle.csv"


WEIGHT_CSV = DATA_DIR / "weight.csv"


ACTIVITY_OVERLAP_DAYS = 2  # re-fetch recent activities (catches edits / late RPE entry)


DAILY_OVERLAP_DAYS = 3  # re-fetch recent days (sleep/HRV finalize late)


PAGE_SIZE = 100


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


def _read_api_key() -> str:
    key = os.environ.get("GARMIN_API_KEY")
    if not key:
        for line in (ROOT / ".env").read_text().splitlines():
            if line.strip().startswith("GARMIN_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        sys.exit("GARMIN_API_KEY not found in environment or .env")
    return key


def _jwt_exp(token: str) -> float:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])


def get_token(force: bool = False) -> str:
    """Exchange the Personal API key for a ~24h bearer JWT, cached on disk."""
    if not force and TOKEN_CACHE.exists():
        cached = json.loads(TOKEN_CACHE.read_text())
        if cached.get("exp", 0) - time.time() > 3600:
            return cached["token"]
    req = urllib.request.Request(
        BASE_URL + "/personalapitoken-service/personal-api/personal-api-key/token",
        method="POST",
        headers={"Accept": "*/*", "Authorization": f"ApiKey {_read_api_key()}"},
    )
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
        token = resp.read().decode().strip().strip('"')
    TOKEN_CACHE.write_text(json.dumps({"token": token, "exp": _jwt_exp(token)}))
    TOKEN_CACHE.chmod(0o600)
    return token


_token: str | None = None


def api_get(path: str, params: dict | None = None):
    global _token
    url = BASE_URL + path + ("?" + urllib.parse.urlencode(params) if params else "")
    for attempt in range(8):
        _token = _token or get_token()
        req = urllib.request.Request(
            url, headers={"Accept": "application/json", "Authorization": f"Bearer {_token}"}
        )
        try:
            with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
                body = resp.read()
                return json.loads(body) if body else None
        except urllib.error.HTTPError as e:
            if e.code == 401 and attempt == 0:
                _token = get_token(force=True)
                continue
            if e.code == 429 and attempt < 7:  # Garmin allows ~100 requests per short window
                try:
                    wait = float(json.loads(e.read()).get("retryInSeconds", 15))
                except ValueError:
                    wait = 15
                print(f"  rate limited, waiting {wait:.0f}s", flush=True)
                time.sleep(wait + 1)
                continue
            if e.code in (500, 502, 503, 504) and attempt < 3:
                time.sleep(2 ** attempt * 2)
                continue
            raise RuntimeError(f"GET {path} -> HTTP {e.code}: {e.read()[:300]!r}") from None
        except (TimeoutError, ConnectionError, urllib.error.URLError) as e:
            if attempt >= 3:
                raise
            print(f"  network error ({e}), retrying", flush=True)
            time.sleep(5)
    raise RuntimeError(f"GET {path} failed after retries")


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def _r(v, nd=1):
    return round(v, nd) if isinstance(v, (int, float)) else v


def _date_chunks(start: date, end: date, max_days: int):
    while start <= end:
        stop = min(start + timedelta(days=max_days - 1), end)
        yield start, stop
        start = stop + timedelta(days=1)
