"""Rate-limited EDGAR client.

Everything that touches sec.gov goes through here so the fair-access rate
limit is enforced in exactly one place, and so every response can be cached
to disk. Caching matters more than it looks: a backtest re-run should never
re-fetch, and cached raw documents are what let you reproduce a historical
number after EDGAR has moved on.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from typing import Any

import requests

from .config import SEC_BASE, SEC_DATA, MAX_REQUESTS_PER_SECOND, SETTINGS


class RateLimiter:
    """Simple token-bucket limiter, thread-safe."""

    def __init__(self, per_second: float = MAX_REQUESTS_PER_SECOND):
        self._min_interval = 1.0 / per_second
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            sleep_for = self._min_interval - (now - self._last)
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._last = time.monotonic()


class EdgarClient:
    def __init__(self, user_agent: str | None = None, cache_dir: str | None = None):
        self.user_agent = user_agent or SETTINGS.user_agent
        self.cache_dir = cache_dir or SETTINGS.cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)
        self._limiter = RateLimiter()
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
            }
        )

    # ---------------------------------------------------------------- fetch

    def _cache_path(self, url: str) -> str:
        key = hashlib.sha256(url.encode()).hexdigest()[:32]
        return os.path.join(self.cache_dir, key)

    def get(self, url: str, use_cache: bool = True, retries: int = 3) -> str:
        path = self._cache_path(url)
        if use_cache and os.path.exists(path):
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                return fh.read()

        last_err: Exception | None = None
        for attempt in range(retries):
            self._limiter.wait()
            try:
                resp = self._session.get(url, timeout=30)
                if resp.status_code == 404:
                    raise FileNotFoundError(f"404 for {url}")
                if resp.status_code in (403, 429):
                    # Fair-access throttle. Back off hard; do not hammer.
                    time.sleep(2 ** (attempt + 1))
                    last_err = RuntimeError(f"{resp.status_code} for {url}")
                    continue
                resp.raise_for_status()
                text = resp.text
                if use_cache:
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(text)
                return text
            except FileNotFoundError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"Failed to fetch {url}: {last_err}")

    def get_json(self, url: str, use_cache: bool = True) -> Any:
        return json.loads(self.get(url, use_cache=use_cache))

    # ------------------------------------------------------------ identity

    def ticker_map(self) -> dict[str, int]:
        """ticker -> CIK. Note one CIK can hold several tickers (GOOG/GOOGL)."""
        data = self.get_json(f"{SEC_BASE}/files/company_tickers.json")
        return {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}

    def resolve_cik(self, ticker: str) -> int:
        mapping = self.ticker_map()
        key = ticker.upper().strip()
        if key not in mapping:
            raise KeyError(f"No CIK found for ticker {ticker!r}")
        return mapping[key]

    def submissions(self, cik: int) -> dict:
        """Filing history. Only `recent` is inlined; older sits in extra files."""
        url = f"{SEC_DATA}/submissions/CIK{cik:010d}.json"
        data = self.get_json(url)
        recent = data.get("filings", {}).get("recent", {})
        rows = _columns_to_rows(recent)
        for extra in data.get("filings", {}).get("files", []):
            extra_url = f"{SEC_DATA}/submissions/{extra['name']}"
            try:
                rows.extend(_columns_to_rows(self.get_json(extra_url)))
            except Exception:  # noqa: BLE001
                pass  # older history is optional; do not fail the run
        data["_filings"] = rows
        return data

    def company_facts(self, cik: int) -> dict:
        return self.get_json(f"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik:010d}.json")

    # ------------------------------------------------------------ document

    @staticmethod
    def filing_dir(cik: int, accession: str) -> str:
        acc = accession.replace("-", "")
        return f"{SEC_BASE}/Archives/edgar/data/{cik}/{acc}"

    def filing_index(self, cik: int, accession: str) -> dict:
        return self.get_json(f"{self.filing_dir(cik, accession)}/index.json")

    def primary_document(self, cik: int, accession: str, doc_name: str) -> str:
        return self.get(f"{self.filing_dir(cik, accession)}/{doc_name}")


def _columns_to_rows(cols: dict) -> list[dict]:
    """EDGAR submissions JSON is column-oriented; make it row-oriented."""
    if not cols or "accessionNumber" not in cols:
        return []
    keys = list(cols.keys())
    n = len(cols["accessionNumber"])
    return [{k: cols[k][i] for k in keys if i < len(cols[k])} for i in range(n)]
