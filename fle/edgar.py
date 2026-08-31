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
        throttled = 0
        while attempt < retries:
            self._limiter.wait()
            try:
                resp = self._session.get(url, timeout=30)
                if resp.status_code == 404:
                    raise FileNotFoundError(f"404 for {url}")
                if resp.status_code in (403, 429):
                    # FAIR-ACCESS BLOCK, NOT A FAILED REQUEST. SEC's
                    # Archives host blocks an IP for ~10 minutes after
                    # heavy traffic; 2-4-8 second sleeps against that are
                    # three knocks on a locked door, and the day this
                    # shipped, eight companies were recorded as having no
                    # certification because every fetch inside the block
                    # "failed". Wait like you mean it -- Retry-After if
                    # offered, else an escalating minute-scale pause --
                    # and do not count patience against the retry budget.
                    throttled += 1
                    if throttled > 6:
                        last_err = RuntimeError(f"{resp.status_code} for {url}")
                        break
                    ra = (resp.headers.get("Retry-After") or "").strip()
                    wait = max(float(ra) if ra.isdigit() else 0.0,
                               45.0 * throttled)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
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
        try:
            return _documents_from_index_page(self.get(url))
        except Exception:  # noqa: BLE001
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
