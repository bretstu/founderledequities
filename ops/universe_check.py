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

MUST_FAIL = {  # cik: (ticker, why we know)
    812801: ("NUV", "closed-end fund"),
    1736035: ("BXSL", "BDC"),
    1782524: ("MSDL", "BDC"),
    1411583: ("PBT", "royalty trust"),
    1588489: ("GBTC", "crypto ETP"),
}
MUST_PASS_EXTRA = {2115436: "XOM (successor)", 2089271: "HONA (spin-off)",
                   1393818: "BX", 922621: "ERIE", 1811074: "TPL",
                   2082247: "FDXF"}


def main() -> int:
    client = EdgarClient()
    bad = 0
    with open("universe/sp500-2026-08-25.csv", encoding="utf-8-sig") as fh:
        sp = [(int(r["cik"]), r["ticker"], r["company"]) for r in csv.DictReader(fh)]
    print(f"checking {len(sp)} S&P companies + {len(MUST_PASS_EXTRA)} known passes "
          f"+ {len(MUST_FAIL)} known fails ...")
    for cik, tk, name in sp + [(c, n.split()[0], n) for c, n in MUST_PASS_EXTRA.items()]:
        try:
            why = eligibility(recent_submissions(client, cik), name)
        except Exception as exc:  # noqa: BLE001
            why = f"FETCH FAILED: {exc}"
        if why and why != "successor":
            bad += 1
            print(f"  WRONGLY EXCLUDED  {tk:6} {why}")
    for cik, (tk, what) in MUST_FAIL.items():
        try:
            subs = recent_submissions(client, cik)
            why = eligibility(subs, subs.get("name") or tk)
        except Exception as exc:  # noqa: BLE001
            why = f"FETCH FAILED: {exc}"
        if not why or why == "successor":
            bad += 1
            print(f"  WRONGLY ADMITTED  {tk:6} ({what})")
    print("clean" if not bad else f"{bad} problem(s) -- fix the rules before a full run")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
