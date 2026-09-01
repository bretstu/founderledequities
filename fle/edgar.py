"""Rate-limited EDGAR client.

Everything that touches sec.gov goes through here so the fair-access rate
limit is enforced in exactly one place, and so every response can be cached
to disk. Caching matters more than it looks: a backtest re-run should never
re-fetch, and cached raw documents are what let you reproduce a historical
number after EDGAR has moved on.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
import threading
import time
from typing import Any

import requests

from .config import SEC_BASE, SEC_DATA, MAX_REQUESTS_PER_SECOND, SETTINGS


# Set on Ctrl+C: every worker waiting on the limiter or resting through a
# block abandons its request at once, so a run stops in seconds instead
# of finishing the queue. (A ThreadPoolExecutor's context exit waits for
# ALL queued work; with 2,000 companies queued, Ctrl+C once did nothing.)
STOP = threading.Event()


class Stopped(BaseException):
    """The run was interrupted; the in-flight company is abandoned.

    A BaseException, like KeyboardInterrupt, ON PURPOSE: the ledger and
    the certification search skip individual bad filings with generic
    `except Exception` handlers, and when this was a RuntimeError the
    01:55 timer's interrupt was swallowed inside a worker's fetch -- the
    ledger finished with an empty filing list and three CEOs were
    checkpointed as owning nothing. An interrupt must pass through every
    handler that was written for network hiccups."""


class RateLimiter:
    """Simple token-bucket limiter, thread-safe -- with a shared circuit
    breaker for SEC's fair-access block.

    A 429 from SEC is a rolling block that STAYS OPEN while requests keep
    arriving. Per-thread backoff got that exactly wrong: four workers each
    retrying every 45-135s kept a probe landing every twenty seconds, the
    block never closed, and each company burned sixteen minutes on the
    way to an error. So a block is shared state: the first worker to see
    it sets a quiet period for ALL of them, they all sleep through it, and
    exactly one request goes out afterwards to test the door. If that one
    is refused, the quiet period doubles -- eleven minutes, then twenty-two, then
    twenty-two -- and only after ~two hours of continuous refusal does anything
    give up. Silence is what lifts the block; the breaker manufactures it.
    """

    def __init__(self, per_second: float = MAX_REQUESTS_PER_SECOND):
        self._min_interval = 1.0 / per_second
        self._last = 0.0
        self._lock = threading.Lock()
        self._blocked_until = 0.0
        self._consecutive = 0

    def wait(self) -> None:
        while True:
            if STOP.is_set():
                raise Stopped("interrupted")
            with self._lock:
                now = time.monotonic()
                until = self._blocked_until
            if until <= now:
                break
            time.sleep(min(until - now, 1.0))
        if STOP.is_set():
            raise Stopped("interrupted")
        with self._lock:
            now = time.monotonic()
            sleep_for = self._min_interval - (now - self._last)
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._last = time.monotonic()

    def trip(self, retry_after: float = 0.0) -> float:
        """Record a refusal; returns the quiet period set (seconds)."""
        with self._lock:
            now = time.monotonic()
            if self._blocked_until > now:
                return 0.0            # already resting; join the same nap
            self._consecutive += 1
            # SEC's rule, in its own words: the block lifts once requests
            # have stayed below the threshold FOR TEN MINUTES, and any
            # request during the time-out extends it. So the first rest is
            # the full ten minutes -- a shorter probe only resets the clock.
            # Eleven, not ten: the other workers may each have a request
            # in flight when the breaker trips, and those land inside the
            # time-out. A minute of margin costs nothing; a probe one second
            # early resets the entire window.
            quiet = max(retry_after, min(660.0 * 2 ** (self._consecutive - 1), 1320.0))
            self._blocked_until = now + quiet
            return quiet

    def clear(self) -> None:
        with self._lock:
            self._consecutive = 0

    @property
    def exhausted(self) -> bool:
        return self._consecutive > 6



# Every flavour of Unicode whitespace, so a non-breaking space that arrives
# as U+00A0 does not survive as a word boundary.
_WS = re.compile(r"[\s\u00a0\u1680\u2000-\u200b\u202f\u205f\u3000\ufeff]+")


def html_to_text(raw: str) -> str:
    """Strip tags, DECODE ENTITIES, normalise whitespace.

    The decoding is the part that was missing, and it cost five companies.
    SEC filings routinely write accented letters as numeric character
    references rather than UTF-8, so AES's certification reads

        I, Andr&#233;s R. Gluski, certify that:

    Hand-replacing three known entities and leaving the rest meant the
    signer's name arrived as "Andr&#233;s R. Gluski", which is not shaped
    like a name -- the check requires each word to be a capital followed by
    word characters, and it stops dead at the ampersand. So the certification
    was located, fetched, correctly recognised AS a certification, and then
    discarded because one letter arrived as seven characters.

    AES, F5, M&T, Moderna and UPS all fell back to reading a job title off a
    Form 4 because of this -- the weakest identity signal available, and the
    one that once picked Microsoft's "CEO of Commercial Business" over Satya
    Nadella.

    Decode ONCE, here, at the point text enters the pipeline. The same class
    of failure has appeared four times in different disguises -- a curly
    apostrophe, a non-breaking space, an accent stripped by a character
    class, an accent never decoded -- and each was patched at the comparison
    that happened to trip over it. Fixing the boundary is what stops a fifth.
    """
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return _WS.sub(" ", text).strip()

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
        attempt = 0
        while attempt < retries:
            self._limiter.wait()
            try:
                resp = self._session.get(url, timeout=30)
                if resp.status_code == 404:
                    raise FileNotFoundError(f"404 for {url}")
                if resp.status_code in (403, 429):
                    # FAIR-ACCESS BLOCK. Trip the SHARED breaker: every
                    # worker rests, one request tests the door afterwards.
                    if self._limiter.exhausted:
                        last_err = RuntimeError(
                            f"{resp.status_code} for {url} (SEC block did "
                            f"not lift in ~an hour of quiet)")
                        break
                    ra = (resp.headers.get("Retry-After") or "").strip()
                    quiet = self._limiter.trip(float(ra) if ra.isdigit() else 0.0)
                    if quiet:
                        print(f"  [sec {resp.status_code}: all workers resting "
                              f"{quiet/60:.0f} min]", file=sys.stderr, flush=True)
                    continue
                resp.raise_for_status()
                self._limiter.clear()
                text = resp.text
                if use_cache:
                    # ATOMIC: a cache-warmer and the nightly can fetch the
                    # same URL in the same instant; write-then-rename means
                    # any reader sees the old body or the new one, never a
                    # torn half-written file.
                    tmp = f"{path}.{os.getpid()}.tmp"
                    with open(tmp, "w", encoding="utf-8") as fh:
                        fh.write(text)
                    os.replace(tmp, path)
                return text
            except FileNotFoundError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                attempt += 1
                time.sleep(1.5 * attempt)
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
        failed = []
        for extra in data.get("filings", {}).get("files", []):
            extra_url = f"{SEC_DATA}/submissions/{extra['name']}"
            try:
                rows.extend(_columns_to_rows(self.get_json(extra_url)))
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{extra['name']}: {exc}")
        if failed:
            # A PARTIAL INDEX IS NOT AN INDEX. This once said "older history
            # is optional" and passed silently. For a company that files
            # prospectus supplements daily -- Ally, AGNC -- the last 1,000
            # filings are all 424B2s and every 10-K and 10-Q lives in the
            # history files; when those failed inside SEC's throttle, the
            # certification search found no periodic filing to read and
            # recorded "no certification", and a history walk would have
            # silently lost years of Form 4s. Missing history is a fetch
            # failure and must raise like one: retryable, never answered.
            raise RuntimeError(
                f"submissions index for CIK {cik} is partial: "
                f"{len(failed)} history file(s) unavailable ({failed[0][:80]})")
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
        """The documents in one filing, keyed the way index.json returns them.

        EDGAR's index.json for an accession sometimes lists only the
        submission wrappers -- the complete .txt, the two index pages, the
        XBRL zip -- and omits every document in the filing, though those
        documents are present and fetchable at the same path. EchoStar's
        FY2025 10-K is one: index.json returns four entries where the filing
        holds twenty-one, Exhibit 31.1 among them.

        A four-entry listing is indistinguishable from a genuinely small
        filing, so nothing downstream could detect this. The certification
        reader found no exhibit, said nothing, and walked back to a 10-Q
        filed the day before the CEO changed -- naming a man who had left
        the company. Brown-Forman, Biogen and EQT hit the same listing and
        had no older filing to fall back to, so they produced no CEO at all.

        When the JSON carries nothing but wrappers, the filing index PAGE is
        read instead. It lists every document and, unlike the JSON, its
        declared EDGAR type ("EX-31.1") -- which is what the exhibit ranking
        wanted in the first place.
        """
        data = self.get_json(f"{self.filing_dir(cik, accession)}/index.json")
        items = data.get("directory", {}).get("item", [])
        if any(not _is_submission_wrapper(it.get("name") or "", accession)
               for it in items):
            return data

        from_page = self.filing_index_page(cik, accession)
        if from_page:
            data.setdefault("directory", {})["item"] = from_page
            data["_from_index_page"] = True
        return data

    def filing_index_page(self, cik: int, accession: str) -> list[dict]:
        """Documents from `{accession}-index.htm`, in index.json's shape.

        Returns [] rather than raising: a failure here must leave the
        caller with whatever the JSON gave it, not lose the filing.
        """
        url = f"{self.filing_dir(cik, accession)}/{accession}-index.htm"
        # A missing page (404) is genuine absence -- return nothing. A
        # FETCH failure is not: swallowing a 429 here once made a blocked
        # filing look like a filing with no documents, and eight of those
        # in a row became "no certification". Let it raise.
        try:
            return _documents_from_index_page(self.get(url))
        except FileNotFoundError:
            return []

    def primary_document(self, cik: int, accession: str, doc_name: str) -> str:
        return self.get(f"{self.filing_dir(cik, accession)}/{doc_name}")


def _columns_to_rows(cols: dict) -> list[dict]:
    """EDGAR submissions JSON is column-oriented; make it row-oriented."""
    if not cols or "accessionNumber" not in cols:
        return []
    keys = list(cols.keys())
    n = len(cols["accessionNumber"])
    return [{k: cols[k][i] for k in keys if i < len(cols[k])} for i in range(n)]


# ------------------------------------------------- the filing index page

_TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
_TD_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.I | re.S)
_HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def _cell_text(fragment: str) -> str:
    text = _TAG_RE.sub(" ", fragment)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&#160;", " "))
    return " ".join(text.split())


def _is_submission_wrapper(name: str, accession: str) -> bool:
    """True for the artifacts EDGAR adds around a filing's real documents.

    Every wrapper is named for the accession -- `{acc}.txt`, `{acc}-index.htm`,
    `{acc}-index-headers.html`, `{acc}-xbrl.zip` -- except the generated
    workbook. A listing of nothing but these carries no documents at all.
    """
    lower = name.strip().lower()
    if not lower:
        return True
    return (lower.startswith(accession.strip().lower())
            or lower == "financial_report.xlsx")


def _documents_from_index_page(html: str) -> list[dict]:
    """Parse the document table, keeping index.json's field names.

    The row is Seq | Description | Document | Type | Size. The filename is
    taken from the link rather than the cell text, because an inline-XBRL
    document renders as "name.htm   iXBRL" and links through the viewer as
    `/ix?doc=/Archives/...`, so the real path sits after `doc=`.
    """
    items: list[dict] = []
    seen: set[str] = set()
    for row in _TR_RE.findall(html or ""):
        cells = _TD_RE.findall(row)
        if len(cells) < 3:
            continue
        href = _HREF_RE.search(row)
        if not href:
            continue
        target = href.group(1)
        if "doc=" in target:
            target = target.split("doc=", 1)[1]
        target = target.split("?")[0].split("#")[0].rstrip("/")
        name = target.split("/")[-1]
        if not name or name in seen:
            continue
        seen.add(name)
        items.append({
            "name": name,
            "type": _cell_text(cells[3]) if len(cells) > 3 else "",
            "size": _cell_text(cells[-1]),
        })
    return items
