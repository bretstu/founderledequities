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

DELISTING_FORMS = {"25", "25-NSE", "15", "15-12B", "15-12G", "15-15D"}
FILE = os.path.join("universe", "delisted.csv")


def delisting(client, cik: int, after: str) -> tuple | None:
    """-> (form, filingDate) of the earliest delisting form filed on or after
    `after` (the person's newest filing date), or None."""
    if not after:
        return None
    try:
        subs = client.submissions(int(cik))
    except Exception:  # noqa: BLE001
        return None
    hits = sorted((f.get("filingDate") or "", f.get("form") or "") for f in subs.get("_filings", [])
                  if (f.get("form") or "") in DELISTING_FORMS and (f.get("filingDate") or "") >= after)
    return (hits[0][1], hits[0][0]) if hits else None


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
