"""A CEO's stake from Schedule 13D/G, for companies whose insiders never
file Section 16.

Shopify was the teaching case. Its certification names Tobias Lütke, its
Section 16 feed is empty -- MJDS/foreign-regime issuers are exempt under
Rule 3a12-3(b) -- and yet his stake IS on EDGAR: a nine-year Schedule 13G
chain whose newest cover page states 80,997,982 shares, 6.3% of the
class. This module reads that: given the issuer and the certified CEO's
name, it walks the issuer's SC 13D/G filings newest-first and returns the
first cover-page stake whose REPORTING PERSON matches the CEO.

Three rules, each learned from a real document the night this was built:

- MATCH THE REPORTING PERSON, decide nothing from the feed. The issuer's
  feed also carries filings the company itself made as an INVESTOR --
  "Shopify Strategic Holdings 3 LLC" reporting a Klaviyo stake lives in
  Shopify's own list. A name match against the certified CEO is the
  subject check: the company-as-investor can never match its CEO's name.
- PICK THE SCHEDULE BY SIZE, not alphabetically. The first .htm in a
  13G's index is often ex1.htm, the joint-filing agreement (5KB); the
  schedule itself (sc13ga8.htm, 70KB) sorts later.
- UNESCAPE BEFORE MATCHING. Older filings write L&#252;tke and pad
  tables with &nbsp;; the raw bytes contain neither the name nor the
  phrase "beneficially owned".
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass

from .names import names_match

SCHEDULE_FORMS = ("SC 13D", "SC 13G", "SC 13D/A", "SC 13G/A")

# The cover page is a numbered table; row 9 is the aggregate, row 11 the
# percent. Filed as HTML tables, flattened to text they read like:
#   "9 AGGREGATE AMOUNT BENEFICIALLY OWNED BY EACH REPORTING PERSON
#    80,997,982 (1)(2) 10 ... 11 PERCENT OF CLASS REPRESENTED BY AMOUNT
#    IN ROW (9) 6.3% (3)"
_PERSON_RE = re.compile(r"NAMES?\s+OF\s+REPORTING\s+PERSONS?", re.I)
_AGG_RE = re.compile(
    r"AGGREGATE\s+AMOUNT\s+BENEFICIALLY\s+OWNED[^0-9]{0,120}?([\d,]{3,})", re.I)
_PCT_RE = re.compile(
    # the phrase is "PERCENT OF CLASS REPRESENTED BY AMOUNT IN ROW (9) 6.3%"
    # -- the skip must cross the digit in "ROW (9)", so the anchor is the
    # trailing %, not "first number after the heading"
    r"PERCENT\s+OF\s+CLASS.{0,160}?([\d.]+)\s*%", re.I | re.S)


@dataclass
class Stake:
    shares: float
    percent: float | None
    form: str
    filing_date: str
    url: str
    reporting_person: str


def _plain(raw: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))


def _schedule_doc(index: dict) -> str | None:
    """The schedule is the LARGEST htm/txt that is not the submission
    wrapper or the index pages."""
    best, best_size = None, -1
    for item in (index.get("directory", {}) or {}).get("item", []) or []:
        name = item.get("name", "")
        if not name.endswith((".htm", ".txt")):
            continue
        if re.match(r"\d{10}-\d\d-\d{6}", name) or "index" in name:
            continue
        try:
            size = int(item.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if size > best_size:
            best, best_size = name, size
    return best


def _stake_for_person(text: str, owner_name: str) -> tuple[float, float | None, str] | None:
    """Scan the cover pages (one per reporting person); return the stake
    from the page whose person matches the certified CEO."""
    starts = [m.start() for m in _PERSON_RE.finditer(text)]
    if not starts:
        return None
    starts.append(len(text))
    for a, b in zip(starts, starts[1:]):
        page = text[a:b]
        # the person's name follows the heading, ending at the next
        # cover-table landmark (item 2 / CHECK / I.R.S.)
        head = page[:300]
        name_m = re.search(
            r"PERSONS?\s*:?\s*(.{4,80}?)\s*(?:\b2\b|CHECK\s+THE|I\.R\.S\.)",
            head, re.S)
        person = (name_m.group(1).strip() if name_m else "").strip(" .")
        if not person or names_match(person, owner_name) < 0.7:
            continue
        agg = _AGG_RE.search(page)
        if not agg:
            continue
        shares = float(agg.group(1).replace(",", ""))
        pct_m = _PCT_RE.search(page)
        pct = float(pct_m.group(1)) if pct_m else None
        return shares, pct, person
    return None


def stake_from_schedule13(client, cik: int, owner_name: str,
                          max_filings: int = 12) -> Stake | None:
    """Newest matching Schedule 13D/G stake for owner_name, or None.

    Fetch failures raise (the caller treats them as retryable errors);
    only a genuine absence returns None -- same contract as everywhere
    else in this codebase: unreadable is not absent."""
    subs = client.submissions(cik)
    schedules = [f for f in subs.get("_filings", [])
                 if (f.get("form") or "") in SCHEDULE_FORMS]
    schedules.sort(key=lambda f: f.get("filingDate", ""), reverse=True)
    for f in schedules[:max_filings]:
        acc = f["accessionNumber"]
        index = client.filing_index(cik, acc)
        doc = _schedule_doc(index)
        if not doc:
            continue
        text = _plain(client.primary_document(cik, acc, doc))
        hit = _stake_for_person(text, owner_name)
        if hit:
            shares, pct, person = hit
            acc_nodash = acc.replace("-", "")
            url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                   f"{acc_nodash}/{doc}")
            return Stake(shares=shares, percent=pct, form=f.get("form", ""),
                         filing_date=f.get("filingDate", ""), url=url,
                         reporting_person=person)
    return None


def is_foreign_reporter(subs: dict) -> bool:
    """Foreign regime NOW: the newest periodic filing is a 20-F/40-F.

    Lifetime tests get Shopify wrong: its feed holds two 10-Ks from a
    2021-22 domestic stint AND eight 40-Fs -- including the current one.
    A company reports under exactly one regime at a time, and the newest
    periodic filing says which."""
    periodic = [f for f in subs.get("_filings", [])
                if (f.get("form") or "") in
                ("10-K", "10-K/A", "10-Q", "10-Q/A",
                 "20-F", "20-F/A", "40-F", "40-F/A")]
    if not periodic:
        return False
    newest = max(periodic, key=lambda f: f.get("filingDate", ""))
    return (newest.get("form") or "").startswith(("20-F", "40-F"))
