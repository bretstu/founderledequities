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

NOTHING A SNAPSHOT DECIDES ON IS READ FROM CACHE. Market caps, share
counts and filing indexes are fetched fresh every time; a quarterly
snapshot that reused last quarter's numbers would be a dated list with
the wrong date on it.

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
# DOMESTIC REGISTRANTS ARE EVIDENCED BY ANY DOMESTIC FORM, NOT ONLY A 10-K.
# A company younger than its first annual report -- a recent IPO, a
# spin-off, a holding-company reorganization -- has 10-Qs, a Form 10 or
# S-1, or a successor-issuer 8-K12B on record and no 10-K yet. Requiring
# the 10-K excluded ExxonMobil (a 2025 holdco with a new CIK) and every
# fresh listing, which is where founder-led companies concentrate. Foreign
# private issuers file 20-F, 6-K and F-1; none of these overlap.
DOMESTIC = {"10-K", "10-K/A", "10-Q", "10-Q/A", "10-12B", "10-12B/A",
            "S-1", "S-1/A", "8-K12B"}
PROXY = {"DEF 14A", "DEFA14A", "DEFM14A"}
# ENTITIES WITH NO CHIEF EXECUTIVE IN THE SENSE THIS SITE MEANS: a shell
# awaiting a target, a commodity pool run by a sponsor, a royalty trust
# run by a trustee, a fund run by an adviser. Each files a 10-K; none has
# a person whose own stake in the business the site could measure.
EXCLUDED_SIC = {"6770": "blank-check company",
                "6221": "commodity pool / exchange-traded product",
                "6792": "royalty trust",
                "6726": "investment company / BDC"}
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
        """Everything a human should read: admitted-on-disagreement rows,
        every unsized row (a first snapshot has no prior to keep them, so
        they are out -- but never silently), and any fetch failure."""
        return [r for r in self.rows
                if (r.status == "disagree" and r.decision != "out")
                or r.status in ("unsized", "unfetched")]


def polygon_ticker(t: str) -> str:
    return t.upper().replace("-", ".")


SEC_DATA = "https://data.sec.gov"


def recent_submissions(client, cik: int) -> dict:
    """The main submissions document only -- fetched FRESH, never from cache.

    Eligibility needs the form TYPES a company files, and the `recent`
    block (the last ~1,000 filings) settles that for any active company:
    a listed domestic filer has a 10-K and Form 4s in its recent history
    or it is not one. Reading the extra history files that old companies
    carry (six 1MB documents for Boeing) made the trial crawl at six
    seconds per company for nothing. And a snapshot must see today's
    index, not the one cached last quarter: a company that filed its
    first 10-K since would otherwise be excluded forever."""
    from .edgar import _columns_to_rows
    data = client.get_json(f"{SEC_DATA}/submissions/CIK{cik:010d}.json",
                           use_cache=False)
    return {"_filings": _columns_to_rows(data.get("filings", {}).get("recent", {})),
            "sic": data.get("sic")}


def eligibility(subs: dict) -> str:
    """'' if the site can cover it, else the reason it cannot."""
    forms = {f.get("form") for f in subs.get("_filings", [])}
    if not (forms & DOMESTIC):
        return "no domestic filings (foreign filer, fund, or shell)"
    if not (forms & SECTION16):
        return "no Section 16 filings"
    sic = str(subs.get("sic") or "")
    if sic in EXCLUDED_SIC:
        return f"{EXCLUDED_SIC[sic]} (SIC {sic})"
    # a mature company -- one with an annual report -- also holds annual
    # meetings; no proxy statement means no board standing for election,
    # which is a pool, a trust, or a fund wearing a 10-K. A company too
    # young for its first 10-K is not held to this yet.
    if ("10-K" in forms or "10-K/A" in forms) and not (forms & PROXY):
        return "no proxy statement on record (no board elected by holders)"
    return ""


def newest_shares(client, cik: int) -> float | None:
    """Cover-page share count from the most recently FILED report only, so
    an amendment never double-counts; per-class facts summed."""
    try:
        facts = json.loads(client.get(CONCEPT_URL.format(cik=cik),
                                      use_cache=False))
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
            DETAILS_URL.format(ticker=polygon_ticker(ticker), key=api_key),
            use_cache=False))
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


ROW_FIELDS = ("cik", "ticker", "company", "mcap_vendor", "mcap_sec",
              "shares_sec", "close", "status", "decision", "added",
              "strikes", "note")


def _checkpoint_load(path: str | None, snapshot: str) -> dict:
    """Rows already decided TODAY, keyed by cik. A checkpoint from another
    date is ignored: a snapshot's decisions belong to its date, and a run
    resumed tomorrow would mix two days' market caps under one label."""
    import json
    import os
    out = {}
    if not path or not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("_snapshot") != snapshot:
                continue
            row = Row(**{k: d.get(k) for k in ROW_FIELDS})
            out[row.cik] = row
    return out


def build_snapshot(client, api_key: str | None, entry: float = 1e9,
                   exit_: float = 8e8, prior: dict | None = None,
                   snapshot: str | None = None, limit: int | None = None,
                   on_step=None, checkpoint: str | None = None) -> Snapshot:
    """RESUMABLE WITHIN A DAY. Every decided row is appended to the
    checkpoint as it is made; a rerun on the same date skips those
    registrants and continues. An hour of fetching should never be lost
    to a stray Ctrl+C -- it was, once, at 6,525 of 8,004."""
    import json
    import os
    snapshot = snapshot or dt.date.today().isoformat()
    prior = prior or {}
    snap = Snapshot(date=snapshot)
    done = _checkpoint_load(checkpoint, snapshot)
    ck = None
    if checkpoint:
        os.makedirs(os.path.dirname(checkpoint) or ".", exist_ok=True)
        ck = open(checkpoint, "a", encoding="utf-8")
    closes = market_closes(client, api_key)
    cands = fetch_all_tickers(client)
    if limit:
        cands = cands[:limit]
    for i, m in enumerate(cands, 1):
        if on_step:
            on_step(i, len(cands), m.ticker)
        if m.cik in done:
            snap.rows.append(done[m.cik])
            continue
        row = Row(cik=m.cik, ticker=m.ticker, company=m.company)
        subs = None
        for _attempt in range(2):
            try:
                subs = recent_submissions(client, m.cik)
                break
            except Exception:  # noqa: BLE001 -- one hiccup must not decide membership
                continue
        if subs is None:
            row.status, row.decision = "unfetched", "out"
            row.note = "filing index unavailable twice; read this row"
            snap.rows.append(row); _ck(ck, row, snapshot)
            continue
        why = eligibility(subs)
        if why:
            row.status, row.decision = "excluded: " + why, "out"
            snap.rows.append(row); _ck(ck, row, snapshot)
            continue
        row.mcap_vendor = vendor_mcap(client, m.ticker, api_key)
        row.shares_sec = newest_shares(client, m.cik)
        row.close = closes.get(m.ticker) or closes.get(polygon_ticker(m.ticker))
        row.mcap_sec = (row.shares_sec * row.close
                        if row.shares_sec and row.close else None)
        classify(row)
        decide(row, entry, exit_, prior, snapshot)
        snap.rows.append(row); _ck(ck, row, snapshot)
    if ck:
        ck.close()
    return snap


def _ck(fh, row: Row, snapshot: str) -> None:
    if not fh:
        return
    import json
    d = {k: getattr(row, k) for k in ROW_FIELDS}
    d["_snapshot"] = snapshot
    fh.write(json.dumps(d) + "\n")
    fh.flush()


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
    dump(review_path, sorted(snap.review,
                             key=lambda r: -(r.mcap or (r.shares_sec or 0))))
    return len(snap.members), len(snap.review)


# ------------------------------------------------------------ the record

def newest_snapshot(universe_dir: str):
    """(members_path, evidence_path, taken) for the newest universe-<date>
    snapshot in the folder, or None when the site runs on the S&P list."""
    import glob
    import os
    paths = sorted(glob.glob(os.path.join(universe_dir, "universe-????-??-??.csv")))
    if not paths:
        return None
    members = paths[-1]
    stem = members[:-4]
    try:
        taken = dt.date.fromisoformat(os.path.basename(stem)[len("universe-"):])
    except ValueError:
        return None
    return members, stem + "-evidence.csv", taken


RULES_HTML = """
<p><b>Who is in.</b> Every company in the SEC's own registry of tickered
registrants that files domestic reports (a 10-K or 10-Q, or for a company
too young for either, a Form 10, S-1 or successor-issuer filing), has at
least one Form 3, 4 or 5 on record, holds annual meetings once it is old
enough to have filed an annual report, and had a market capitalization at or
above <b>$1 billion</b> on the snapshot date. One row per company: a
dual-class filer counts once.</p>
<p><b>Who is out, and why.</b> Foreign private issuers file 20-Fs and their
officers file no ownership forms; Section 16 does not reach them, so this site
cannot measure them. Entities with no chief executive in the sense this site
means: blank-check companies, commodity pools and exchange-traded products,
royalty trusts, and investment companies (by SEC industry code). Companies
the sizing rules could not place above the bar.</p>
<p><b>How size is decided.</b> Two independent measures: the market cap
published by the price vendor, and the company's own cover-page share count
(from its most recently filed report) times the newest close. When they agree
within 25%, the company is sized. When they disagree, it is admitted if either
clears the bar and flagged for a human reading. When neither is available, a
current member is kept and a newcomer waits: a counting failure never evicts
and never admits.</p>
<p><b>The edge does not flap.</b> A company enters at $1 billion and leaves
only after two consecutive quarterly snapshots below $800 million. Otherwise
names near the line would blink in and out, their histories appearing and
vanishing.</p>
<p><b>Snapshots are quarterly and dated.</b> This list is what the rules
produced on the date shown, from the sources named. A company that crossed
$1 billion after that date joins at the next snapshot. If you believe a
company is missing in error, write to
<a href="mailto:corrections@founderledequities.com">corrections@founderledequities.com</a>
with the ticker; the evidence behind every decision is kept.</p>
"""


def write_page(members_path: str, evidence_path: str, taken: str,
               about_path: str, out_path: str) -> str | None:
    """The published universe: every member, and the rules, as a page in
    the site's own dress. Built from about.html's head so it inherits the
    fonts and styles without a second stylesheet to keep in step."""
    import html
    import os
    import re
    try:
        shell = open(about_path, encoding="utf-8").read()
    except OSError:
        return None
    m = re.search(r"<main>.*?</main>", shell, re.S)
    if not m:
        return None

    rows = []
    with open(evidence_path, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if r.get("decision") in ("in", "kept"):
                rows.append(r)
    rows.sort(key=lambda r: -float(r.get("mcap_vendor") or r.get("mcap_sec") or 0))
    n = len(rows)
    flagged = sum(1 for r in rows if r.get("status") in ("disagree", "unsized"))

    def money(v):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return "—"
        if v >= 1e12:
            return f"${v/1e12:.2f}T"
        if v >= 1e9:
            return f"${v/1e9:.1f}B"
        return f"${v/1e6:.0f}M"

    trs = "\n".join(
        f"<tr><td class=\"k\">{html.escape(r['ticker'])}</td>"
        f"<td>{html.escape(r['company'])}</td>"
        f"<td class=\"k\" style=\"text-align:right\">{money(r.get('mcap_vendor') or r.get('mcap_sec'))}</td>"
        f"<td class=\"k\" style=\"color:var(--faint)\">{html.escape(r.get('added') or '')}"
        + ("  ·  flagged" if r.get("status") in ("disagree", "unsized") else "")
        + "</td></tr>"
        for r in rows)

    main = f"""<main>
  <h1>Every company on the site.</h1>
  <p class="standfirst">{n:,} US public companies with a market capitalization at or
  above $1 billion on <b>{html.escape(taken)}</b>, chosen by the rules below.
  {flagged:,} carried a flag for human review at that snapshot.</p>

  <section id="rules">
    <h2>The rules</h2>
    {RULES_HTML}
    <p>Sources: SEC EDGAR (company registry, filing histories, cover-page share
    counts); Polygon (market capitalization and closing prices). The rules are
    code, in <span class="k">fle/market_universe.py</span>, and this page is
    regenerated from that code's evidence file at each snapshot.</p>
  </section>

  <section id="members">
    <h2>The list</h2>
    <p style="color:var(--faint);font-size:13px">Sorted by market capitalization on the snapshot date.
    "Added" is the snapshot a company first entered.</p>
    <table style="width:100%;border-collapse:collapse;font-size:13.5px">
      <thead><tr style="text-align:left;font-family:var(--mono);font-size:11px;letter-spacing:.06em;color:var(--faint)">
        <th style="padding:6px 0">TICKER</th><th>COMPANY</th><th style="text-align:right">MARKET CAP</th><th>ADDED</th></tr></thead>
      <tbody>
{trs}
      </tbody>
    </table>
  </section>
</main>"""
    page = shell[:m.start()] + main + shell[m.end():]
    page = page.replace("<title>", "<title>Every company · ", 1)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(page)
    return out_path
