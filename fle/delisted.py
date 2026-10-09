"""A COMPANY THAT WAS ACQUIRED LEAVES THE SITE (2026-09-17). Crinetics was
bought by Vertex on 1 September and AtaiBeckley by Lilly on 11 September;
each founder's last Form 4 disposes of every share for the merger
consideration, so the ledger's 0 is correct, and a page that says the
founder of a company that no longer trades owns 0.00% of it, at high
confidence, in the "hired under 1%" screen, is wrong in every way but
arithmetic. The monthly universe snapshot drops delisted tickers at month
end; this is the same fact on the day it happens.

THE SIGNAL IS STRUCTURED: after a merger the issuer files Form 25 (the
exchange delists the stock) and Form 15 (registration terminated), both
entries in the submissions feed the pipeline already reads. An issuer with
either form filed on or after its chief executive's newest Section 16
filing is gone. The panel row records it; the row is dropped before the
panel is published, the ticker is written to universe/delisted.csv (data,
beside the partnership register), and read_universe drops it thereafter.
A Form 15 filed years before the person's filings (a subsidiary's debt
registration, an old suspension) is not this and is not read as it.
"""
import csv
import os

# THE FORM 15 ONLY (2026-09-17, second try). A Form 25 is filed for whatever
# leaves the exchange: AT&T's, Cheniere Partners', D-Wave's were for notes,
# warrants and a preferred, and the first rule read them as the stock going
# and dropped eight listed companies. A Form 15 terminates the registration:
# the company stops reporting, which is what "gone" means, and no warrant
# delisting produces one. The cost is days: Crinetics' 25 came on 3 Sept, its
# 15 on the 15th.
#
# THE FORM 15 IS NOT ENOUGH EITHER (2026-10-09, third try). A 15-12G ends a
# 12(g) registration, and an issuer can hold several: Bristol Myers filed
# one in March for a class that was not its stock, Apollo and ONEOK in the
# summer, Enbridge a 15-12B in 2019 for a redeemed preferred. Eight listed
# companies left the site on 17 September and were not missed for three
# weeks; Gladstone Land and Wave would have gone the same way on the first
# walk of the $200M expansion. The form says a registration ended, not which.
# Whether the STOCK still trades is the vendor's fact: Polygon's reference
# record for the ticker carries `active`, false with a `delisted_utc` once
# the exchange is done with it. So: the Form 15 raises the question and the
# vendor answers it. Without an answer (no key, a vendor error) nobody
# leaves: a founder page reading 0.00% for a few weeks is a flaw, deleting
# Bristol Myers is a different kind of thing, and the quarterly snapshot
# drops delisted tickers regardless.
DELISTING_FORMS = {"15", "15-12B", "15-12G", "15-15D"}
FILE = os.path.join("universe", "delisted.csv")


def still_listed(client, ticker: str, api_key: str | None) -> bool | None:
    """-> True when the vendor says the ticker is active, False when it says
    delisted, None when it cannot say (no key, no record, an error)."""
    if not api_key or not ticker:
        return None
    import json
    from .market_universe import DETAILS_URL, polygon_ticker
    try:
        data = json.loads(client.get(
            DETAILS_URL.format(ticker=polygon_ticker(ticker), key=api_key),
            use_cache=False))
    except Exception:  # noqa: BLE001
        return None
    r = data.get("results") or {}
    if "active" not in r:
        return None
    return bool(r["active"]) and not r.get("delisted_utc")


def delisting(client, cik: int, after: str, ticker: str = "",
              api_key: str | None = None, listed=None) -> tuple | None:
    """-> (form, filingDate) of the earliest delisting form filed on or after
    `after` (the person's newest filing date) WHEN the vendor confirms the
    stock no longer trades; None otherwise. `listed` is the vendor check,
    (client, ticker, api_key) -> bool | None; the default asks Polygon."""
    if not after:
        return None
    try:
        subs = client.submissions(int(cik))
    except Exception:  # noqa: BLE001
        return None
    hits = sorted((f.get("filingDate") or "", f.get("form") or "") for f in subs.get("_filings", [])
                  if (f.get("form") or "") in DELISTING_FORMS and (f.get("filingDate") or "") >= after)
    if not hits:
        return None
    trading = (listed or still_listed)(client, ticker, api_key)
    if trading is False:
        return (hits[0][1], hits[0][0])
    return None


def path_for(universe_path: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(universe_path)), "delisted.csv")


def read(path: str) -> dict:
    """-> {TICKER: {form, date, noted}}"""
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return {(r.get("ticker") or "").upper(): r for r in csv.DictReader(fh) if r.get("ticker")}


def record(path: str, rows: list) -> int:
    """Append the tickers not already there; -> how many were new."""
    have = read(path)
    new = [r for r in rows if (r.get("ticker") or "").upper() not in have]
    if not new:
        return 0
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fresh = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["ticker", "cik", "company", "ceo", "form", "date", "noted"])
        if fresh:
            w.writeheader()
        for r in new:
            w.writerow({k: r.get(k, "") for k in ["ticker", "cik", "company", "ceo", "form", "date", "noted"]})
    return len(new)
