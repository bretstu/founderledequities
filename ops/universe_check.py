#!/usr/bin/env python3
"""Check the universe's eligibility rules against known answers BEFORE an
hour-long snapshot: every S&P 500 company must pass, and the known
non-companies must fail. Prints only the surprises. ~500 fetches, ~2 min.

    python3 ops/universe_check.py
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fle.edgar import EdgarClient  # noqa: E402
from fle.market_universe import eligibility, recent_submissions  # noqa: E402

# Tickers only -- CIKs are resolved through SEC's own registry, never
# typed by hand. (A hand-typed one pointed the first version of this check
# at the wrong company.)
MUST_FAIL = {"NUV": "closed-end fund", "BXSL": "BDC", "MSDL": "BDC",
             "PBT": "royalty trust", "SBR": "royalty trust",
             "GBTC": "crypto ETP", "DBA": "commodity pool", "USO": "commodity pool",
             "FETH": "crypto fund, no SIC"}
MUST_PASS_EXTRA = {"XOM": "successor issuer", "HONA": "spin-off",
                   "BX": "controlled, no proxy", "ERIE": "controlled, no proxy",
                   "TPL": "ex-trust corporation", "FDXF": "young spin-off"}


def main() -> int:
    from fle.universe import fetch_all_tickers
    client = EdgarClient()
    registry = {m.ticker: m for m in fetch_all_tickers(client)}
    bad = 0

    def judge(cik, name):
        subs = recent_submissions(client, cik)
        return eligibility(subs, subs.get("name") or name), subs.get("name") or name

    with open("universe/sp500-2026-08-25.csv", encoding="utf-8-sig") as fh:
        sp = [(int(r["cik"]), r["ticker"], r["company"]) for r in csv.DictReader(fh)]
    print(f"checking {len(sp)} S&P companies + {len(MUST_PASS_EXTRA)} known passes "
          f"+ {len(MUST_FAIL)} known fails ...")
    extra = []
    for tk, what in MUST_PASS_EXTRA.items():
        m = registry.get(tk)
        if not m:
            print(f"  NOT IN REGISTRY   {tk:6} ({what})"); bad += 1; continue
        extra.append((m.cik, tk, m.company))
    for cik, tk, name in sp + extra:
        try:
            why, _ = judge(cik, name)
        except Exception as exc:  # noqa: BLE001
            why = f"FETCH FAILED: {exc}"
        if why and why != "successor":
            bad += 1
            print(f"  WRONGLY EXCLUDED  {tk:6} {why}")
    for tk, what in MUST_FAIL.items():
        m = registry.get(tk)
        if not m:
            print(f"  NOT IN REGISTRY   {tk:6} ({what}) -- skipped"); continue
        try:
            why, name = judge(m.cik, m.company)
        except Exception as exc:  # noqa: BLE001
            why, name = f"FETCH FAILED: {exc}", m.company
        if not why or why == "successor":
            bad += 1
            print(f"  WRONGLY ADMITTED  {tk:6} ({what})  cik={m.cik}  name={name!r}")
    print("clean" if not bad else f"{bad} problem(s) -- fix the rules before a full run")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
