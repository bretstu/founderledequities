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
            # "officer" OR "executive": GE Aerospace writes "Current
            # directors & executives as a group (16 people)", which requiring
            # the word "officer" missed entirely.
            if "director" in window and ("officer" in window
                                         or "executive" in window):
                return m
        return None


GROUP_ROW_RE = _GroupRowMatcher()

# Item 403(a) requires the ADDRESS of each 5% beneficial owner; Item 403(b)
# requires no address for management. An address column is therefore a strong
# marker that a table is the 5%-holder table, not the one we want.
ADDRESS_HEADER_RE = re.compile(
    r"address\s+of\s+(?:the\s+)?beneficial|address\s+of\s+owner|^address$", re.I
)

# The decisive test: does the header contain a column that COUNTS SHARES
# HELD? Exxon's table of contents earned the "beneficial ownership" credit
# because "CERTAIN BENEFICIAL OWNERS" is a chapter title, and GE's equity
# GRANT table earned the group-row credit because it also totals officers as
# a group. Neither has a holdings column, and no ownership table lacks one.
HOLDINGS_COL_RE = re.compile(
    r"number of shares|shares? beneficially owned|shares? owned|"
    r"total (?:number of )?shares|common stock|amount and nature|"
    r"beneficial ownership|aggregate beneficial|shares? held|"
    r"ordinary shares|class [a-z] (?:common|capital)",
    re.I,
)
# A contents page: most rows end in a bare page number, and -- decisively --
# the table contains no comma-formatted figures anywhere. Every ownership
# table has share counts; no contents page does. Without that second test,
# Exxon's real table was itself penalised, because its options column is all
# zeros and "0" looks like a page number.
TOC_ROW_RE = re.compile(r"^[1-9]\d{0,2}$")
GROUPED_NUMBER_RE = re.compile(r"\d,\d{3}")

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
    # Position in the document. Needed to reassemble page-break fragments in
    # the order they were printed.
    doc_index: int = 0
    # Text immediately BEFORE the table. Filers state shares outstanding in
    # the paragraph that introduces it -- "All percentage calculations are
    # based on ... 621,925,120" -- and discarding this sent the denominator
    # search hunting through the whole document.
    preceding_context: str = ""


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

    # ---- does the header describe holdings at all? ----------------------
    header_cells: list[str] = []
    for r in rows[:3]:
        header_cells += [c.get_text(" ", strip=True)
                         for c in r.find_all(["td", "th"])]
    header_join = " | ".join(header_cells)
    # Also accept a header cell that is simply "Shares" once footnote markers
    # are stripped. Disney's real ownership table is headed "Shares 1,2 (#)",
    # and requiring a longer phrase penalised it 3.5 points.
    # A header cell that is just "Shares" or just "Stock" once footnote
    # markers are stripped. Verizon heads its holdings column "Stock" and
    # the longer phrases missed it, so its real table took the
    # no-holdings-column penalty and lost to something else.
    # "Stock Units" must NOT count -- those are excluded from 13d-3.
    bare_shares = any(
        # "Stock" alone is Verizon's holdings column. "Stock Units" and
        # "Stock Awards Granted" are not holdings at all -- the second is
        # GE's grant table, which must keep failing this test.
        re.fullmatch(r"(shares?|stock)", cleaned)
        or (re.match(r"^shares?\b", cleaned)
            and not re.search(r"\bunits?\b|granted|award", cleaned))
        for cleaned in (
            re.sub(r"[\d,()#*†‡\s]+$", "", c.strip()).strip().lower()
            for c in header_cells[1:]
        )
    )
    if HOLDINGS_COL_RE.search(header_join) or bare_shares:
        score += 3.5
        reasons.append("holdings_column(+3.5)")
    else:
        score -= 3.5
        reasons.append("no_holdings_column(-3.5)")

    # ---- table of contents ----------------------------------------------
    tail_cells = []
    for r in rows[:20]:
        cells = [c.get_text(" ", strip=True) for c in r.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if cells:
            tail_cells.append(cells[-1])
    if tail_cells and not GROUPED_NUMBER_RE.search(text):
        page_like = sum(1 for c in tail_cells if TOC_ROW_RE.match(c))
        if page_like / len(tail_cells) > 0.7:
            score -= 5.0
            reasons.append("contents_page(-5)")

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

    # Only penalise when the 5%-holder heading is immediately above this
    # table. GE prints its 5% table, then directors, then named executives --
    # and the two real tables were both docked for the first one's heading.
    if FIVE_PCT_RE.search(preceding[-220:]) and not has_group:
        score -= 1.0
        reasons.append("looks_like_5pct_table(-1)")

    # A prose table is one where MOST columns are prose, not one that has a
    # single long column. Coca-Cola's ownership table carries an "Additional
    # Information" column of footnote text thousands of characters long
    # beside its name and share columns -- judging by the longest cell
    # anywhere penalised it 7 points and it was never parsed at all.
    #
    # Exxon's legal comparison table, the case this penalty exists for, is
    # prose in two of its three columns.
    col_lengths: dict[int, int] = {}
    for r in rows[:20]:
        for i, c in enumerate(r.find_all(["td", "th"])):
            t = c.get_text(" ", strip=True)
            col_lengths[i] = max(col_lengths.get(i, 0), len(t))
    if col_lengths:
        prose_cols = sum(1 for v in col_lengths.values() if v > 500)
        if prose_cols and prose_cols >= max(2, len(col_lengths) / 2):
            score -= 7.0
            reasons.append(f"prose_table({prose_cols}/{len(col_lengths)}"
                           f"_cols)(-7)")
        elif prose_cols:
            # One annotation column beside real data. Worth a nudge, not a
            # disqualification.
            score -= 1.0
            reasons.append(f"has_footnote_column(-1)")

    # ---- does the header describe holdings at all? ----------------------
    header_cells: list[str] = []
    for r in rows[:3]:
        header_cells += [c.get_text(" ", strip=True)
                         for c in r.find_all(["td", "th"])]
    header_join = " | ".join(header_cells)
    # Also accept a header cell that is simply "Shares" once footnote markers
    # are stripped. Disney's real ownership table is headed "Shares 1,2 (#)",
    # and requiring a longer phrase penalised it 3.5 points.
    # A header cell that is just "Shares" or just "Stock" once footnote
    # markers are stripped. Verizon heads its holdings column "Stock" and
    # the longer phrases missed it, so its real table took the
    # no-holdings-column penalty and lost to something else.
    # "Stock Units" must NOT count -- those are excluded from 13d-3.
    bare_shares = any(
        # "Stock" alone is Verizon's holdings column. "Stock Units" and
        # "Stock Awards Granted" are not holdings at all -- the second is
        # GE's grant table, which must keep failing this test.
        re.fullmatch(r"(shares?|stock)", cleaned)
        or (re.match(r"^shares?\b", cleaned)
            and not re.search(r"\bunits?\b|granted|award", cleaned))
        for cleaned in (
            re.sub(r"[\d,()#*†‡\s]+$", "", c.strip()).strip().lower()
            for c in header_cells[1:]
        )
    )
    if HOLDINGS_COL_RE.search(header_join) or bare_shares:
        score += 3.5
        reasons.append("holdings_column(+3.5)")
    else:
        score -= 3.5
        reasons.append("no_holdings_column(-3.5)")

    # ---- table of contents ----------------------------------------------
    tail_cells = []
    for r in rows[:20]:
        cells = [c.get_text(" ", strip=True) for c in r.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if cells:
            tail_cells.append(cells[-1])
    if tail_cells and not GROUPED_NUMBER_RE.search(text):
        page_like = sum(1 for c in tail_cells if TOC_ROW_RE.match(c))
        if page_like / len(tail_cells) > 0.7:
            score -= 5.0
            reasons.append("contents_page(-5)")

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

    # Only penalise when the 5%-holder heading is immediately above this
    # table. GE prints its 5% table, then directors, then named executives --
    # and the two real tables were both docked for the first one's heading.
    if FIVE_PCT_RE.search(preceding[-220:]) and not has_group:
        score -= 1.0
        reasons.append("looks_like_5pct_table(-1)")

    # A data table has short cells. Exxon's proxy contains a legal comparison
    # table -- "Issue | New Jersey | Texas" -- whose cells run to thousands of
    # characters of prose, and it outranked the real ownership table because
    # that prose happens to mention "beneficial owner" and several
    # percentages.
    #
    # Use the LONGEST cell, not the median: a prose table still has a short
    # header row, which drags a median down below any useful threshold. No
    # legitimate ownership cell approaches 500 characters, footnotes included.
    longest = 0
    for r in rows[:20]:
        for c in r.find_all(["td", "th"]):
            longest = max(longest, len(c.get_text(" ", strip=True)))
    if longest > 500:
        score -= 7.0
        reasons.append(f"prose_cells(max={longest})(-7)")
    elif longest > 260:
        score -= 2.5
        reasons.append(f"longish_cells(max={longest})(-2.5)")

    return TableCandidate(
        score=score,
        html=str(table),
        text=text,
        preceding_context=preceding[-3000:],
        trailing_context=trailing,
        has_group_row=has_group,
        reasons=reasons,
    )


def _header_signature(candidate: "TableCandidate") -> str:
    """First row of a table, normalised, for spotting continuations."""
    soup = BeautifulSoup(candidate.html, "lxml")
    row = soup.find("tr")
    if row is None:
        return ""
    cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
    cells = [re.sub(r"\s+", " ", c).strip().lower() for c in cells if c.strip()]
    return " | ".join(cells)[:160]


def merge_continuations(candidates: list["TableCandidate"]) -> list["TableCandidate"]:
    """Fold page-break fragments back into one table.

    A long ownership table is often emitted as several <table> elements, one
    per printed page, each repeating the header. Cabot's splits into a
    60-row body and a 3-row tail -- and the tail scored higher, because it
    happens to carry the "directors and officers as a group" line. Picking it
    meant reading a table containing two people, neither of them the CEO.

    Fragments sharing a header are concatenated in document order, and the
    merged candidate inherits the best score of its parts.
    """
    if len(candidates) < 2:
        return candidates

    groups: dict[str, list[TableCandidate]] = {}
    for c in candidates:
        sig = _header_signature(c)
        if sig:
            groups.setdefault(sig, []).append(c)

    merged: list[TableCandidate] = []
    used: set[int] = set()
    for sig, parts in groups.items():
        if len(parts) < 2:
            continue
        parts.sort(key=lambda c: c.doc_index)
        combined = "".join(p.html for p in parts)
        best = max(parts, key=lambda c: c.score)
        merged.append(TableCandidate(
            score=best.score + 1.0,   # a complete table beats any fragment
            doc_index=parts[0].doc_index,
            html=combined,
            text=" ".join(p.text for p in parts),
            trailing_context=parts[-1].trailing_context,
            preceding_context=parts[0].preceding_context,
            has_group_row=any(p.has_group_row for p in parts),
            reasons=best.reasons + [f"merged_{len(parts)}_fragments(+1)"],
        ))
        used.update(id(p) for p in parts)

    kept = [c for c in candidates if id(c) not in used]
    out = merged + kept
    out.sort(key=lambda c: c.score, reverse=True)
    return out


def locate_ownership_tables(html: str, top_n: int = 14) -> list[TableCandidate]:
    """Return the best-scoring candidate tables, highest first.

    Returns several because dual-class issuers sometimes split management and
    5% holders across two tables, and because a low margin between the top two
    is itself a useful signal that the document is unusual.
    """
    soup = BeautifulSoup(html, "lxml")
    flat = soup.get_text(" ", strip=True)
    candidates: list[TableCandidate] = []

    for position, table in enumerate(soup.find_all("table")):
        snippet = table.get_text(" ", strip=True)[:80]
        idx = flat.find(snippet) if snippet else -1
        preceding = flat[max(0, idx - 1200) : idx] if idx > 0 else ""
        # Footnotes live immediately after the table and carry the qualifiers
        # that make the headline numbers interpretable.
        #
        # This must start after the WHOLE table, not after the 80-character
        # snippet used to locate it. Every table is longer than 80 characters,
        # so the old arithmetic made "trailing context" mostly table body --
        # and the denominator search, which reads this region, took
        # BlackRock's 158,217,849 holding out of Palantir's ownership table
        # while the correct 2,397,157,109 sat two regions away.
        table_len = len(table.get_text(" ", strip=True))
        after = idx + table_len if idx > 0 else 0
        trailing = flat[after : after + 4000] if idx > 0 else ""
        cand = score_table(table, preceding, trailing)
        cand.doc_index = position
        if cand.score > 0:
            candidates.append(cand)

    candidates.sort(key=lambda c: c.score, reverse=True)
    # Keep a generous list. With the model deciding which table is the
    # ownership table, a candidate wrongly INCLUDED costs one cheap call,
    # while a candidate wrongly EXCLUDED cannot be recovered at all.
    candidates = merge_continuations(candidates[: max(top_n * 4, 24)])
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
