"""Settings, and the one rule EDGAR asks of us.

SEC fair access requires a User-Agent that identifies the caller with a real
contact address. Anything else gets throttled to 403, and v1 spent a while
mistaking that for a rate limit.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    for candidate in (Path.cwd() / ".env",
                      Path(__file__).resolve().parent.parent / ".env"):
        if not candidate.exists():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()

DEFAULT_USER_AGENT = os.environ.get(
    "FLE_USER_AGENT", "FounderLedEquities research contact@example.com")


@dataclass
class Settings:
    user_agent: str = DEFAULT_USER_AGENT
    cache_dir: str = field(
        default_factory=lambda: os.environ.get("FLE_CACHE", ".cache"))
    polygon_api_key: str | None = field(
        default_factory=lambda: os.environ.get("POLYGON_API_KEY"))
    anthropic_api_key: str | None = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY"))


SETTINGS = Settings()
# SEC fair access allows ten requests a second. Staying under it is the
# difference between a working pipeline and an IP block.
# SEC's fair-access threshold is 10 requests/second per IP, enforced by an
# automated rolling block (~10 minutes of 429s). Eight was the working
# pace for a year. On a day when the address has already sent hundreds of
# thousands of requests, the threshold trips far below it and a cold
# 2,000-company panel crawled at ten an hour, almost all of it backoff.
# FLE_RATE lets a long run pick a gentler pace: fewer blocks beat more
# requests.
MAX_REQUESTS_PER_SECOND = float(os.environ.get("FLE_RATE") or 8)

SEC_BASE = "https://www.sec.gov"
SEC_DATA = "https://data.sec.gov"
