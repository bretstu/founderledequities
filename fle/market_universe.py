"""The market-cap universe: which companies the site covers, and why each.

THE CLAIM ON THE HERO IS A PROMISE. "Every US company over $1B" is a
sentence strangers will test -- someone will search for a $1.3B company
they own and judge every other number by whether it is there. Market caps
move daily, so the only version of that promise that can be kept is a
PRECISE one: a dated snapshot, from named sources, by written rules, with
the list published. This module produces the snapshot; the rules live
here, where the About page can point at them.

WHO IS IN
  - SEC's registry of tickered registrants, one row per company (CIK),
    via universe.fetch_all_tickers -- the same dedup rule the S&P file
    uses, for the same reason
  - domestic filers: a 10-K on record. Foreign private issuers file 20-F
    and their officers file no Forms 3/4/5 -- Section 16 does not reach
    them, so the site cannot measure them. Excluded by construction, not
    by choice, and the About page says so.
  - with Section 16 activity: at least one Form 3, 4 or 5 ever filed
  - market cap at or above the entry bar (default $1B) by the rules below

WHO IS OUT
  - blank-check companies (SIC 6770): a shell has no chief executive in
    the sense this site means
  - anything the sizing rules cannot place above the bar

HOW SIZE IS DECIDED -- two measures, no silent verdicts
  vendor:  Polygon's market_cap for the ticker (the number the rest of
           the world means by the phrase)
  sec:     newest cover-page share count (dei:EntityCommonStockShares
           Outstanding from the most recently FILED report, per-class
           facts summed) x the newest close
  sized    the two agree within 25%; in if the larger clears the bar
  disagree beyond 25%: in if either clears the bar, and FLAGGED for a
           human -- the review file lists every such row
  unsized  neither available: flagged; in only if already a member (a
           counting failure never evicts)

HYSTERESIS -- the edge must not flap
  A company enters at the entry bar and leaves only after two consecutive
  snapshots below the EXIT bar (default $800M). Otherwise names near $1B
  blink in and out each refresh, their histories appearing and vanishing,
  which reads as instability even when every decision was right. The
  prior snapshot's evidence file is the memory.

OUTPUT: the members file has the S&P universe file's exact columns, so
the rest of the pipeline runs on it unchanged. Alongside it: an evidence
file for every registrant considered, and a review file of the rows a
human should read before the snapshot is published.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from dataclasses import dataclass, field

from .universe import Member, fetch_all_tickers, write_universe

CONCEPT_URL = ("https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}"
               "/dei/EntityCommonStockSharesOutstanding.json")
DETAILS_URL = "https://api.polygon.io/v3/reference/tickers/{ticker}?apiKey={key}"
GROUPED_URL = ("https://api.polygon.io/v2/aggs/grouped/locale/us/market/"
               "stocks/{day}?adjusted=true&apiKey={key}")

SECTION16 = {"3", "3/A", "4", "4/A", "5", "5/A"}
SPAC_SIC = {"6770"}
DISAGREE = 0.25
STRIKES_TO_EXIT = 2


@dataclass
class Row:
    cik: int
    ticker: str
    company: str
    mcap_vendor: float | None = None
    mcap_sec: float | None = None
    shares_sec: float | None = None
    close: float | None = None
    status: str = ""       # sized | disagree | unsized | excluded: <why>
    decision: str = ""     # in | kept | out
    added: str = ""
    strikes: int = 0
    note: str = ""

    @property
    def mcap(self) -> float | None:
        m = [x for x in (self.mcap_vendor, self.mcap_sec) if x]
        return max(m) if m else None


@dataclass
class Snapshot:
    date: str
    rows: list = field(default_factory=list)

    @property
    def members(self) -> list:
        return [r for r in self.rows if r.decision in ("in", "kept")]

    @property
    def review(self) -> list:
        return [r for r in self.rows
                if r.status in ("disagree", "unsized") and r.decision != "out"]


def polygon_ticker(t: str) -> str:
    return t.upper().replace("-", ".")


def eligibility(subs: dict) -> str:
    """'' if the site can cover it, else the reason it cannot."""
    forms = {f.get("form") for f in subs.get("_filings", [])}
    if "10-K" not in forms and "10-K/A" not in forms:
        return "no 10-K on record (foreign filer, fund, or shell)"
    if not (forms & SECTION16):
        return "no Section 16 filings"
    if str(subs.get("sic") or "") in SPAC_SIC:
        return "blank-check company (SIC 6770)"
    return ""


def newest_shares(client, cik: int) -> float | None:
    """Cover-page share count from the most recently FILED report only, so
    an amendment never double-counts; per-class facts summed."""
    try:
        facts = json.loads(client.get(CONCEPT_URL.format(cik=cik)))
        vals = [v for v in facts.get("units", {}).get("shares", [])
                if v.get("val") and v.get("accn")]
        if not vals:
            return None
        newest = max(vals, key=lambda v: v.get("filed") or "")["accn"]
        mine = [v for v in vals if v["accn"] == newest]
        end = max(v.get("end") or "" for v in mine)
        return float(sum(float(v["val"]) for v in mine if v.get("end") == end))
    except Exception:  # noqa: BLE001
        return None


def vendor_mcap(client, ticker: str, api_key: str | None) -> float | None:
    if not api_key:
        return None
    try:
        data = json.loads(client.get(
            DETAILS_URL.format(ticker=polygon_ticker(ticker), key=api_key)))
        mc = (data.get("results") or {}).get("market_cap")
        return float(mc) if mc else None
    except Exception:  # noqa: BLE001
        return None


def market_closes(client, api_key: str | None) -> dict:
    """One grouped request: yesterday's close for every US stock."""
    if not api_key:
        return {}
    day = dt.date.today()
    for _ in range(7):
        try:
            data = json.loads(client.get(
                GROUPED_URL.format(day=day.isoformat(), key=api_key),
                use_cache=False))
            res = data.get("results") or []
            if res:
                return {r["T"].upper(): float(r["c"]) for r in res
                        if r.get("T") and r.get("c")}
        except Exception:  # noqa: BLE001
            pass
        day -= dt.timedelta(days=1)
    return {}


def classify(row: Row) -> None:
    mv, ms = row.mcap_vendor, row.mcap_sec
    if not mv and not ms:
        row.status = "unsized"
    elif mv and ms and abs(mv - ms) / max(mv, ms) > DISAGREE:
        row.status = "disagree"
    else:
        row.status = "sized"


def decide(row: Row, entry: float, exit_: float, prior: dict,
           snapshot: str) -> None:
    """Membership with hysteresis. prior: cik -> (added, strikes)."""
    was_in = row.cik in prior
    added, strikes = prior.get(row.cik, ("", 0))
    m = row.mcap or 0.0
    if row.status == "unsized":
        row.decision = "kept" if was_in else "out"
        row.note = ("counting failure; kept as a member" if was_in
                    else "counting failure; never a member")
    elif not was_in:
        row.decision = "in" if m >= entry else "out"
    elif m < exit_:
        strikes += 1
        row.decision = "out" if strikes >= STRIKES_TO_EXIT else "kept"
        row.note = f"below exit bar, strike {strikes} of {STRIKES_TO_EXIT}"
    else:
        strikes = 0
        row.decision = "in"
    row.strikes = strikes
    if row.decision in ("in", "kept"):
        row.added = added or snapshot


def build_snapshot(client, api_key: str | None, entry: float = 1e9,
                   exit_: float = 8e8, prior: dict | None = None,
                   snapshot: str | None = None, limit: int | None = None,
                   on_step=None) -> Snapshot:
    snapshot = snapshot or dt.date.today().isoformat()
    prior = prior or {}
    snap = Snapshot(date=snapshot)
    closes = market_closes(client, api_key)
    cands = fetch_all_tickers(client)
    if limit:
        cands = cands[:limit]
    for i, m in enumerate(cands, 1):
        if on_step:
            on_step(i, len(cands), m.ticker)
        row = Row(cik=m.cik, ticker=m.ticker, company=m.company)
        try:
            subs = client.submissions(m.cik)
        except Exception:  # noqa: BLE001
            row.status, row.decision = "excluded: no filing history", "out"
            snap.rows.append(row)
            continue
        why = eligibility(subs)
        if why:
            row.status, row.decision = "excluded: " + why, "out"
            snap.rows.append(row)
            continue
        row.mcap_vendor = vendor_mcap(client, m.ticker, api_key)
        row.shares_sec = newest_shares(client, m.cik)
        row.close = closes.get(m.ticker) or closes.get(polygon_ticker(m.ticker))
        row.mcap_sec = (row.shares_sec * row.close
                        if row.shares_sec and row.close else None)
        classify(row)
        decide(row, entry, exit_, prior, snapshot)
        snap.rows.append(row)
    return snap


EVIDENCE_COLS = ["cik", "ticker", "company", "mcap_vendor", "mcap_sec",
                 "shares_sec", "close", "status", "decision", "added",
                 "strikes", "note"]


def load_prior(evidence_path: str) -> dict:
    """cik -> (added, strikes) for members of a previous snapshot."""
    out = {}
    try:
        with open(evidence_path, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("decision") in ("in", "kept"):
                    try:
                        strikes = int(r.get("strikes") or 0)
                    except ValueError:
                        strikes = 0
                    out[int(r["cik"])] = (r.get("added") or "", strikes)
    except FileNotFoundError:
        pass
    return out


def write_snapshot(snap: Snapshot, members_path: str, evidence_path: str,
                   review_path: str) -> tuple:
    write_universe([Member(r.cik, r.ticker, r.company, r.added)
                    for r in snap.members], members_path)

    def dump(path, rows):
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=EVIDENCE_COLS)
            w.writeheader()
            for r in rows:
                w.writerow({c: ("" if getattr(r, c) is None
                                else getattr(r, c)) for c in EVIDENCE_COLS})
    dump(evidence_path, snap.rows)
    dump(review_path, sorted(snap.review, key=lambda r: -(r.mcap or 0)))
    return len(snap.members), len(snap.review)
