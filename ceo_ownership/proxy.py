"""Locating the Item 403 beneficial ownership table inside a proxy statement.

Item 403 standardises the *content* of the table but not its heading, its
position, or its column layout. Regexing on one heading phrase loses 20-30%
of filers, so instead every <table> in the document is scored on features
that follow from the regulation rather than from house style.

The dominant signal is the "all directors and executive officers as a group"
row: Item 403(b) requires that aggregate line, and virtually every filer
phrases it close to those words. It is worth more than every other feature
combined, and it doubles as a validation anchor later (the CEO's holding must
be <= the group's).
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass

from bs4 import BeautifulSoup

try:  # Modern EDGAR filings are inline XBRL, which is XML-flavoured HTML.
    from bs4 import XMLParsedAsHTMLWarning

    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
except ImportError:  # pragma: no cover
    pass

from .config import PROXY_FORMS
from .edgar import EdgarClient

# Item 403(b) requires an aggregate line for directors and executive officers,
# but the wording varies more than a single phrasing allows: "All directors and
# executive officers as a group", "Directors and named executive officers as a
# group", "All current directors and officers as a group". Requiring "as a
# group" keeps it specific while letting the leading "all" be optional.
AS_A_GROUP_RE = re.compile(r"as\s+a\s+group", re.I)


class _GroupRowMatcher:
    """Detect the Item 403(b) aggregate row.

    A fixed phrase does not survive real filings: "All directors and executive
    officers as a group", "All directors, nominees and current executive
    officers as a group", "Directors, Director Nominees, and Executive Officers
    as a Group". Rather than enumerate, require "as a group" with both a
    director word and an officer word close in front of it.
    """

    def search(self, text: str):
        if not text:
            return None
        for m in AS_A_GROUP_RE.finditer(text):
            window = text[max(0, m.start() - 90): m.start()].lower()
            if "director" in window and "officer" in window:
                return m
        return None


GROUP_ROW_RE = _GroupRowMatcher()

# Item 403(a) requires the ADDRESS of each 5% beneficial owner; Item 403(b)
# requires no address for management. An address column is therefore a strong
# marker that a table is the 5%-holder table, not the one we want.
ADDRESS_HEADER_RE = re.compile(
    r"address\s+of\s+(?:the\s+)?beneficial|address\s+of\s+owner|^address$", re.I
)

BENEFICIAL_RE = re.compile(r"beneficial(?:ly)?\s+own", re.I)
PERCENT_HEADER_RE = re.compile(r"percent|%\s*of\s*(class|shares|total)", re.I)
FIVE_PCT_RE = re.compile(r"5%|five percent|principal (stock|share)holders", re.I)
MONEY_RE = re.compile(r"\$\s?[\d,]")


@dataclass
class TableCandidate:
    score: float
    html: str
    text: str
    trailing_context: str
    has_group_row: bool
    reasons: list[str]


# ------------------------------------------------------------------ discovery


def find_proxy_filing(client: EdgarClient, cik: int, before: str | None = None) -> dict:
    """Most recent proxy-type filing, optionally as-of a historical date.

    `before` (YYYY-MM-DD) must be the FILING date cutoff, not an as-of date,
    so backtest callers cannot accidentally see a document before it existed.
    Falls back through DEFR14A / 10-K/A / 10-K because roughly 10-15% of small
    caps incorporate Item 403 by reference and never file a standalone proxy.
    """
    subs = client.submissions(cik)
    filings = subs.get("_filings", [])
    for form in PROXY_FORMS:
        matches = [
            f
            for f in filings
            if f.get("form") == form
            and (before is None or f.get("filingDate", "") <= before)
        ]
        if matches:
            matches.sort(key=lambda f: f.get("filingDate", ""), reverse=True)
            best = matches[0]
            return {
                "cik": cik,
                "form": form,
                "accession": best["accessionNumber"],
                "filing_date": best["filingDate"],
                "primary_document": best.get("primaryDocument", ""),
                "fallback": form != "DEF 14A",
            }
    raise LookupError(f"No proxy-type filing found for CIK {cik}")


def load_proxy_html(client: EdgarClient, filing: dict) -> str:
    return client.primary_document(
        filing["cik"], filing["accession"], filing["primary_document"]
    )


# ------------------------------------------------------------------- scoring


def score_table(table, preceding: str, trailing: str) -> TableCandidate:
    text = table.get_text(" ", strip=True)
    rows = table.find_all("tr")
    reasons: list[str] = []
    score = 0.0

    has_group = bool(GROUP_ROW_RE.search(text))
    if has_group:
        score += 6.0
        reasons.append("group_row(+6)")

    header_text = " ".join(
        r.get_text(" ", strip=True) for r in rows[:3]
    ) if rows else ""
    if PERCENT_HEADER_RE.search(header_text):
        score += 3.0
        reasons.append("percent_header(+3)")

    if BENEFICIAL_RE.search(text) or BENEFICIAL_RE.search(preceding):
        score += 2.5
        reasons.append("beneficial_own(+2.5)")

    if len(rows) >= 5:
        score += 1.5
        reasons.append(f"rows={len(rows)}(+1.5)")
    elif len(rows) < 3:
        score -= 3.0
        reasons.append("too_few_rows(-3)")

    # First column should be names, not numbers.
    first_cells = []
    for r in rows[1:12]:
        cells = r.find_all(["td", "th"])
        if cells:
            first_cells.append(cells[0].get_text(" ", strip=True))
    nonnumeric = [c for c in first_cells if c and not re.match(r"^[\d,.$%()\-\s]+$", c)]
    if first_cells and len(nonnumeric) / len(first_cells) > 0.6:
        score += 1.0
        reasons.append("name_column(+1)")

    # Compensation tables look similar but are full of dollar signs.
    money_hits = len(MONEY_RE.findall(text))
    if money_hits > 5:
        score -= 4.0
        reasons.append(f"money_signs={money_hits}(-4)")

    if ADDRESS_HEADER_RE.search(header_text):
        score -= 4.0
        reasons.append("address_column=5pct_table(-4)")

    if FIVE_PCT_RE.search(preceding) and not has_group:
        score -= 1.0
        reasons.append("looks_like_5pct_table(-1)")

    return TableCandidate(
        score=score,
        html=str(table),
        text=text,
        trailing_context=trailing,
        has_group_row=has_group,
        reasons=reasons,
    )


def locate_ownership_tables(html: str, top_n: int = 3) -> list[TableCandidate]:
    """Return the best-scoring candidate tables, highest first.

    Returns several because dual-class issuers sometimes split management and
    5% holders across two tables, and because a low margin between the top two
    is itself a useful signal that the document is unusual.
    """
    soup = BeautifulSoup(html, "lxml")
    flat = soup.get_text(" ", strip=True)
    candidates: list[TableCandidate] = []

    for table in soup.find_all("table"):
        snippet = table.get_text(" ", strip=True)[:80]
        idx = flat.find(snippet) if snippet else -1
        preceding = flat[max(0, idx - 1200) : idx] if idx > 0 else ""
        # Footnotes live immediately after the table and carry the qualifiers
        # that make the headline numbers interpretable.
        trailing = flat[idx + len(snippet) : idx + len(snippet) + 4000] if idx > 0 else ""
        cand = score_table(table, preceding, trailing)
        if cand.score > 0:
            candidates.append(cand)

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:top_n]


def location_confidence(candidates: list[TableCandidate]) -> str:
    """HIGH when one table clearly wins and carries the required group row."""
    if not candidates:
        return "NONE"
    top = candidates[0]
    if not top.has_group_row:
        return "LOW"
    if len(candidates) == 1 or top.score - candidates[1].score >= 3.0:
        return "HIGH"
    return "MEDIUM"
