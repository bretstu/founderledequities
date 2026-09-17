"""Which companies to run.

KEYED ON CIK, NOT TICKER. Wikipedia's ticker column has errors and tickers
change hands -- but the CIK is EDGAR's own identifier and never moves. v1
found 503 ticker rows collapsing to about 500 companies once deduplicated by
CIK, because dual-class filers list each class separately: Alphabet appears
as GOOG and GOOGL, Fox as FOX and FOXA, and both of each pair are one filer
with one set of Section 16 filings.

Deduplicating on ticker would run those companies twice and publish the same
chief executive under two rows.

A DATED SNAPSHOT, NOT A LIVE LOOKUP. Membership changes a few times a year,
and a run should be reproducible: the file records what the index was on the
day it was written, so a panel can be re-run months later against the same
universe rather than a moved one.
"""
from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass, asdict
from datetime import date

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

_TAG = re.compile(r"<[^>]+>")
_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)


def _text(html: str) -> str:
    import html as _h
    return _h.unescape(_TAG.sub(" ", html or "")).replace("\xa0", " ").strip()


@dataclass
class Member:
    cik: int
    ticker: str
    company: str
    added: str = ""


def parse_members(html: str) -> list[Member]:
    """The constituents table, deduplicated by CIK.

    Wikipedia's first table is the membership list. Column order has been
    stable for years, but the CIK column is found by shape -- a run of digits
    padded to ten -- rather than by position, so a reordered table degrades
    into missing rows instead of silently mismatched ones.
    """
    out: dict[int, Member] = {}
    for row in _ROW.findall(html):
        cells = [_text(c) for c in _CELL.findall(row)]
        if len(cells) < 4:
            continue
        cik = None
        for c in cells:
            digits = c.strip()
            if digits.isdigit() and 4 <= len(digits) <= 10:
                cik = int(digits)
                break
        if cik is None:
            continue
        ticker = cells[0].replace(".", "-").upper()      # BRK.B -> BRK-B
        company = cells[1]
        added = next((c for c in cells if re.fullmatch(r"\d{4}-\d{2}-\d{2}", c)), "")
        if not ticker or not company:
            continue
        # First occurrence wins: for a dual-class pair either row names the
        # same filer, and the panel only needs one.
        out.setdefault(cik, Member(cik, ticker, company, added))
    return list(out.values())


def fetch_members(client) -> list[Member]:
    return parse_members(client.get(WIKI_URL))


# EVERY REGISTRANT WITH A TICKER, PUBLISHED BY THE SEC ITSELF.
#
# The S&P 500 is a licensed list scraped from a third party. This one is the
# regulator's own file, public domain, and it is the whole exchange-listed
# market rather than the large-cap slice of it -- which is where the
# question this site asks gets interesting, because a founder who still owns
# forty per cent of their company is rarely running an S&P 500 constituent.
ALL_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def parse_all_tickers(raw: str) -> list[Member]:
    """The SEC's ticker file: an object keyed by row number, not a list.

    {"0": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"}}

    Deduplicated by CIK, so a dual-class filer counts once -- the same rule
    the membership table uses, for the same reason: two share classes are
    one company with one chief executive.
    """
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    rows = data.values() if isinstance(data, dict) else data
    seen: dict = {}
    for r in rows:
        try:
            cik = int(r["cik_str"])
        except (KeyError, TypeError, ValueError):
            continue
        ticker = (r.get("ticker") or "").strip().upper()
        title = (r.get("title") or "").strip()
        if not ticker or cik in seen:
            continue
        seen[cik] = Member(cik, ticker, title)
    return list(seen.values())


def fetch_all_tickers(client) -> list[Member]:
    return parse_all_tickers(client.get(ALL_TICKERS_URL))


def write_universe(rows: list[Member], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["cik", "ticker", "company", "added"])
        w.writeheader()
        for r in sorted(rows, key=lambda m: m.ticker):
            w.writerow(asdict(r))


def read_universe(path: str, register: bool = True) -> list[Member]:
    """The universe, less the companies the partnership register excludes
    (fle/partnerships.py, 2026-09-15): dropped here, before the panel walks,
    so nothing downstream ever sees them. Printed once per process."""
    out = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            try:
                out.append(Member(int(row["cik"]), row.get("ticker", ""),
                                  row.get("company", ""), row.get("added", "")))
            except (KeyError, ValueError):
                continue
    if register:
        from .partnerships import excluded, path_for
        from .delisted import read as _delisted, path_for as _dpath
        gone = _delisted(_dpath(path))
        if gone:
            before = len(out)
            out = [m for m in out if m.ticker.upper() not in gone]
            if before != len(out) and not getattr(read_universe, "_said_gone", False):
                print(f"  delisted: {before - len(out)} left the universe (universe/delisted.csv: {', '.join(sorted(gone)[:6])}{'...' if len(gone) > 6 else ''})")
                read_universe._said_gone = True
        drop = excluded(path_for(path))
        if drop:
            before = len(out)
            out = [m for m in out if m.ticker.upper().replace(".", "-") not in drop and m.ticker.upper() not in drop]
            if not getattr(read_universe, "_said", False):
                print(f"  partnerships: {before - len(out)} excluded by universe/partnerships.csv "
                      f"({', '.join(sorted(drop)[:8])}{'...' if len(drop) > 8 else ''})")
                read_universe._said = True
    return out


def default_name(when: date | None = None) -> str:
    return f"universe/sp500-{(when or date.today()).isoformat()}.csv"


def newest_sp_list(universe_dir: str):
    """(path, date) of the newest universe/sp500-<date>.csv, or None."""
    import glob
    import os
    paths = sorted(glob.glob(os.path.join(universe_dir, "sp500-????-??-??.csv")))
    if not paths:
        return None
    stem = os.path.basename(paths[-1])[len("sp500-"):-len(".csv")]
    try:
        return paths[-1], date.fromisoformat(stem)
    except ValueError:
        return None


def sp_list_acceptable(fresh: list, current: list,
                       lo: int = 495, hi: int = 510, max_churn: int = 10):
    """-> (ok, why, added_tickers, dropped_tickers).

    THE LIST IS A SCRAPE, AND A SCRAPE CAN BE WRONG FOR A DAY. The S&P 500
    holds a few more than 500 filers (dual-class members dedupe to one
    CIK; a handful of members are two companies). Anything outside 495-510
    is not the index; a difference of more than ten companies from the
    list we have is not an index change but a broken page. Either keeps
    the current list. Membership is compared by CIK, EDGAR's own key.
    """
    n = len(fresh)
    if not lo <= n <= hi:
        return False, f"{n} members, expected {lo}-{hi}", [], []
    old = {m.cik: m for m in current}
    new = {m.cik: m for m in fresh}
    adds = sorted(new[c].ticker for c in new if c not in old)
    drops = sorted(old[c].ticker for c in old if c not in new)
    if current and len(adds) + len(drops) > max_churn:
        return (False, f"{len(adds)} added and {len(drops)} dropped at once; "
                f"more than {max_churn} is not an index change", adds, drops)
    return True, "", adds, drops
