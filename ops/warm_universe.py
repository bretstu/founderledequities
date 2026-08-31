#!/usr/bin/env python3
"""Warm the EDGAR cache for the every-public-company universe -- safely,
slowly, and without touching anything the live site depends on.

WHY THIS EXISTS. Expanding from the S&P 500 to every US company over $1B
is mostly a waiting problem: the cold walk is ~90% network fetches. The
cache is keyed by URL and append-only, so those fetches can happen weeks
before any pipeline code exists to use them -- this script is that head
start. Kill it anytime; re-running skips everything already cached.

WHAT IT NEVER DOES: write to any file the site or the nightly reads. Its
only outputs are cache entries and universe/warm-candidates.csv.

HOW IT STAYS OUT OF THE NIGHTLY'S WAY:
  - 4 requests/second (the nightly runs at 8; SEC fair access allows 10;
    the two never overlap anyway, because...)
  - quiet hours: fetching pauses 02:05-03:35 machine time, bracketing the
    02:31 timer.
  - atomic cache writes (fle/edgar.py) make same-URL races harmless.

STAGES (each resumable, each skippable):
  1  candidates   SEC's company_tickers.json -- every registrant with a ticker
  2  eligibility  one submissions fetch per registrant; keep domestic
                  10-K filers (Section 16 does not reach 20-F filers, so
                  foreign private issuers can never appear on the site)
  3  size         shares outstanding (one small XBRL fact per company) x
                  the newest close (one grouped-daily request for the whole
                  market) -> market cap filter
  4  documents    --deep only: prefetch what CEO identification reads --
                  the Form 3s since 2015 and the newest proxies and cover
                  reports. Exactly what the live panel stage fetches; the
                  CEO's own Form 4s wait for the CEO to be identified.

USAGE:
  python3 ops/warm_universe.py                 # stages 1-3, writes the list
  python3 ops/warm_universe.py --deep          # 1-4 (run in tmux; ~2-3 evenings)
  python3 ops/warm_universe.py --min-cap 5e8 --limit 200   # trial run
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fle.config import SETTINGS  # noqa: E402
from fle.edgar import EdgarClient  # noqa: E402

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
CONCEPT_URL = ("https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}"
               "/dei/EntityCommonStockSharesOutstanding.json")
GROUPED_URL = ("https://api.polygon.io/v2/aggs/grouped/locale/us/market/"
               "stocks/{day}?adjusted=true&apiKey={key}")
DETAILS_URL = "https://api.polygon.io/v3/reference/tickers/{ticker}?apiKey={key}"

QUIET_START, QUIET_END = dt.time(2, 5), dt.time(3, 35)


def polite(client: EdgarClient, rate: float) -> None:
    client._limiter._min_interval = 1.0 / rate


def quiet_hours() -> None:
    """Sleep through the nightly's window rather than compete with it."""
    now = dt.datetime.now().time()
    if QUIET_START <= now <= QUIET_END:
        until = dt.datetime.combine(dt.date.today(), QUIET_END)
        wait = (until - dt.datetime.now()).total_seconds() + 30
        print(f"  quiet hours (the nightly owns {QUIET_START}-{QUIET_END}); "
              f"sleeping {wait/60:.0f} min")
        time.sleep(max(wait, 0))


def stage1_candidates(client) -> list:
    raw = json.loads(client.get(TICKERS_URL))
    by_cik = {}
    for row in raw.values():
        cik = int(row["cik_str"])
        tk = (row.get("ticker") or "").upper()
        # one company, many listings: keep the shortest ticker (the common
        # line, usually) and let eligibility sort the rest out
        if cik not in by_cik or len(tk) < len(by_cik[cik][0]):
            by_cik[cik] = (tk, row.get("title") or "")
    out = [(cik, tk, title) for cik, (tk, title) in sorted(by_cik.items())]
    print(f"  stage 1: {len(out):,} registrants with tickers")
    return out


def stage2_eligible(client, cands, limit=None) -> list:
    kept, seen = [], 0
    for cik, tk, title in cands:
        if limit and seen >= limit:
            break
        seen += 1
        quiet_hours()
        try:
            subs = client.submissions(cik)
        except Exception:  # noqa: BLE001 -- dead registrants are expected
            continue
        forms = {f.get("form") for f in subs.get("_filings", [])}
        if "10-K" not in forms and "10-K/A" not in forms:
            continue                     # funds, FPIs, shells: not our world
        if not any(f in forms for f in ("3", "4", "5")):
            continue                     # no Section 16 activity at all
        kept.append((cik, tk, title))
        if seen % 250 == 0:
            print(f"  stage 2: {seen:,} checked, {len(kept):,} are 10-K filers")
    print(f"  stage 2: {len(kept):,} domestic 10-K filers with Section 16")
    return kept


def newest_shares(client, cik) -> float | None:
    """A coarse share count for a FILTER, made hard to get badly wrong.

    Facts are taken from ONE filing -- the most recently filed -- so a
    date reported by both a 10-K and its amendment is never summed twice.
    Within that filing, a multi-class cover files one fact per class and a
    single-class cover files one; summing the facts at the filing's latest
    date handles both. Anything stranger returns None, and None means
    "size unknown, warm it anyway" -- the caller never drops a company for
    a counting failure. The site's own denominator comes from the audited
    cover parser in fle/outstanding.py, never from here.
    """
    try:
        facts = json.loads(client.get(CONCEPT_URL.format(cik=cik)))
        vals = [v for v in facts.get("units", {}).get("shares", [])
                if v.get("val") and v.get("accn")]
        if not vals:
            return None
        newest_accn = max(vals, key=lambda v: v.get("filed") or "")["accn"]
        mine = [v for v in vals if v["accn"] == newest_accn]
        latest_end = max(v.get("end") or "" for v in mine)
        at_end = [float(v["val"]) for v in mine if v.get("end") == latest_end]
        return sum(at_end) if at_end else None
    except Exception:  # noqa: BLE001
        return None


def _polygon_ticker(t: str) -> str:
    # SEC writes BRK-B; Polygon writes BRK.B -- same rule as fle/prices.py
    return t.upper().replace("-", ".")


def vendor_mcap(client, ticker) -> float | None:
    """Polygon's own market cap for the ticker: the number the rest of the
    world means by the phrase, maintained by the vendor, not parsed by us."""
    key = SETTINGS.polygon_api_key
    if not key:
        return None
    try:
        data = json.loads(client.get(DETAILS_URL.format(
            ticker=_polygon_ticker(ticker), key=key)))
        mc = (data.get("results") or {}).get("market_cap")
        return float(mc) if mc else None
    except Exception:  # noqa: BLE001
        return None


def stage3_size(client, eligible, prices, min_cap, out_path) -> list:
    """Two independent measures, and a rule that never drops a company on
    a counting failure.

    PRIMARY: the vendor's market cap (Polygon ticker details).
    CROSS-CHECK: SEC cover shares x newest close, computed by us.
    Both agree within 25%%: sized with confidence. They disagree: kept and
    flagged -- that row is a question for a human, not a silent decision.
    Neither available: kept and flagged unsized.

    Only a company BOTH measures put under the bar is dropped. This is a
    warming filter and errs generous; the published universe is decided
    later by the same two measures plus a human reading of the flagged
    rows -- a claim on the hero earns that much.
    """
    kept, unsized, disagree, under = [], 0, 0, 0
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["cik", "ticker", "name", "mcap_vendor", "mcap_sec",
                    "shares_sec", "close", "status"])
        for i, (cik, tk, title) in enumerate(eligible, 1):
            quiet_hours()
            mv = vendor_mcap(client, tk)
            sh = newest_shares(client, cik)
            px = prices.get(tk) or prices.get(_polygon_ticker(tk))
            ms = sh * px if (sh and px) else None
            measures = [m for m in (mv, ms) if m]
            if not measures:
                status = "unsized"; unsized += 1; keep = True
            elif len(measures) == 2 and abs(mv - ms) / max(mv, ms) > 0.25:
                status = "disagree"; disagree += 1; keep = max(measures) >= min_cap
            else:
                status = "sized"; keep = max(measures) >= min_cap
            if keep:
                kept.append((cik, tk))
            else:
                under += 1
            if keep or status != "sized":
                w.writerow([cik, tk, title, int(mv) if mv else "",
                            int(ms) if ms else "", int(sh) if sh else "",
                            px or "", status if keep else status + "-under"])
            if i % 250 == 0:
                print(f"  stage 3: {i:,}/{len(eligible):,} checked, "
                      f"{len(kept):,} kept, {disagree} disagree, "
                      f"{unsized} unsized, {under} under")
    print(f"  stage 3: {len(kept):,} kept over ${min_cap:,.0f} "
          f"({disagree:,} where vendor and SEC disagree by >25%, "
          f"{unsized:,} unsized -- both kept, both flagged); "
          f"{under:,} under the bar -> {out_path}")
    return kept


def market_prices(client) -> dict:
    key = SETTINGS.polygon_api_key
    if not key:
        print("  no POLYGON_API_KEY; cannot size companies", file=sys.stderr)
        return {}
    day = dt.date.today()
    for _ in range(7):                       # walk back to a trading day
        url = GROUPED_URL.format(day=day.isoformat(), key=key)
        try:
            data = json.loads(client.get(url, use_cache=False))
            res = data.get("results") or []
            if res:
                print(f"  prices: {len(res):,} tickers at the "
                      f"{day} close")
                return {r["T"].upper(): float(r["c"]) for r in res
                        if r.get("T") and r.get("c")}
        except Exception:  # noqa: BLE001
            pass
        day -= dt.timedelta(days=1)
    return {}


DOC_FLOOR = "2015-01-01"   # the site's record starts 2016; one year of margin

# WHAT THE LIVE PIPELINE ACTUALLY READS BEFORE IT KNOWS THE CEO.
# build_ledger fetches the issuer's index, then -- when it only has a name
# from the proxy -- reads the Form 3s first (one per insider, a short list)
# until the reporting owner matches, then walks THAT person's filings.
# So the documents that can be prefetched exactly, with no waste, are the
# ones identification reads: the Form 3s, and the proxy and cover-page
# reports the panel stage consults. The CEO's Form 4s cannot be chosen
# until the CEO is chosen; that fetch belongs to the real walk.
IDENT_FORMS = {"3", "3/A"}
PANEL_FORMS = {"DEF 14A": 2, "10-K": 1, "10-Q": 1}   # newest N of each


def stage4_documents(client, keepers, limit=None) -> None:
    from fle.ledger import _doc_url
    total = 0
    for n, (cik, tk) in enumerate(keepers, 1):
        if limit and n > limit:
            break
        quiet_hours()
        try:
            subs = client.submissions(cik)
        except Exception:  # noqa: BLE001
            continue
        filings = [f for f in subs.get("_filings", []) if f.get("primaryDocument")]
        want = [f for f in filings
                if f.get("form") in IDENT_FORMS
                and (f.get("filingDate") or "") >= DOC_FLOOR]
        for form, keep in PANEL_FORMS.items():
            newest = sorted((f for f in filings if f.get("form") == form),
                            key=lambda f: f.get("filingDate") or "",
                            reverse=True)[:keep]
            want.extend(newest)
        for f in want:
            quiet_hours()
            try:
                client.get(_doc_url(cik, f["accessionNumber"],
                                    f["primaryDocument"]))
                total += 1
            except Exception:  # noqa: BLE001
                continue
        if n % 50 == 0:
            print(f"  stage 4: {n:,}/{len(keepers):,} companies, "
                  f"{total:,} identification documents warm "
                  f"(~{total/n:.0f} per company)")
    print(f"  stage 4: {total:,} identification documents in cache")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-cap", type=float, default=1e9)
    ap.add_argument("--rate", type=float, default=4.0,
                    help="requests/second (nightly runs at 8; SEC allows 10)")
    ap.add_argument("--deep", action="store_true",
                    help="also prefetch every Section 16 document")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap companies per stage, for trial runs")
    ap.add_argument("--out", default="universe/warm-candidates.csv")
    args = ap.parse_args()

    client = EdgarClient()
    polite(client, args.rate)
    print(f"[warm] cache={client.cache_dir}  rate={args.rate}/s  "
          f"min_cap=${args.min_cap:,.0f}")

    cands = stage1_candidates(client)
    eligible = stage2_eligible(client, cands, limit=args.limit)
    prices = market_prices(client)
    keepers = stage3_size(client, eligible, prices, args.min_cap, args.out)
    if args.deep:
        stage4_documents(client, keepers, limit=args.limit)
    else:
        print("  (run again with --deep to prefetch Section 16 documents)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
