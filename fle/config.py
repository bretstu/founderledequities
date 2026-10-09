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

# HOW OLD A SUBMISSIONS FEED MAY BE. Filings are immutable and cache forever;
# the per-company list of filings is not, and a nightly that reads it from a
# clockless cache reads nothing new, ever (production did exactly that for
# five nights after the universe promotion, deploying the same data each
# time and calling it success). Four hours: EDGAR accepts filings until
# 22:00 ET and the nightly runs at 02:30, so a run by hand as late as the
# evening still leaves the nightly asking afresh; a rerun within the hour
# costs no requests.
SUBMISSIONS_MAX_AGE = float(os.environ.get("FLE_SUBMISSIONS_MAX_AGE") or 4 * 3600)

# HOW OLD A SPLIT HISTORY MAY BE (2026-10-09). The vendor's list of a
# ticker's splits is the same kind of thing as a submissions feed: a list of
# what has happened so far. It was cached without a clock, so a company's
# splits were frozen at its first walk and a split executed after that was
# invisible to the denominator until the next cover page caught up (the
# window the split logic exists to bridge). A day: splits are announced
# weeks ahead and executed on a known date, and one small request per
# company per night is nothing.
SPLITS_MAX_AGE = float(os.environ.get("FLE_SPLITS_MAX_AGE") or 24 * 3600)
