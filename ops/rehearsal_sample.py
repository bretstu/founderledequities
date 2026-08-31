#!/usr/bin/env python3
"""Build the rehearsal universe: 50 S&P companies the pipeline already knows,
50 it has never walked, chosen to surface what the full universe will.

WHY 100 AND NOT 1,000. A systematic problem -- the panel misidentifying a
kind of chief executive, the walk mishandling a structure -- shows up in
fifty new names as surely as in a thousand, and fifty finish in an hour.
The S&P half is the control group: known answers, diffed against prod.

HOW THE NEW FIFTY ARE CHOSEN. Stratified by size (the largest, the middle,
the smallest members), with the hard shapes deliberately included: the
successor issuer, the young spin-off, the controlled companies, an MLP,
a REIT, a bank, a dual-class filer. Deterministic: the same seed gives the
same sample, so a re-run after a fix walks the same names.

    python3 ops/rehearsal_sample.py            # -> universe/rehearsal-100.csv
"""
import csv
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SP = "universe/sp500-2026-08-25.csv"
EVIDENCE = None   # newest universe-*-evidence.csv found below
OUT = "universe/rehearsal-100.csv"
SEED = 2026

# S&P names that carry a known shape, always in the control group
SP_MUST = ["XOM", "HONA", "BX", "ERIE", "TPL", "FDXF", "TSLA", "META", "ABNB",
           "ECHO", "AKAM", "GOOGL", "BRK-B", "KKR", "APO", "HOOD", "RDDT"]
# new names that carry a known shape, always in the experiment
NEW_MUST = ["AB"]   # AllianceBernstein Holding: an LP with units


def main() -> int:
    import glob
    ev = sorted(glob.glob("universe/universe-????-??-??-evidence.csv"))
    if not ev:
        print("no universe evidence file; run the snapshot first"); return 1
    evidence = ev[-1]
    with open(SP, encoding="utf-8-sig") as fh:
        sp = list(csv.DictReader(fh))
    sp_tk = {r["ticker"] for r in sp}
    with open(evidence, encoding="utf-8-sig") as fh:
        members = [r for r in csv.DictReader(fh) if r["decision"] in ("in", "kept")]
    new = [r for r in members if r["ticker"] not in sp_tk]
    for r in new:
        r["_cap"] = float(r.get("mcap_vendor") or r.get("mcap_sec") or 0)
    new.sort(key=lambda r: -r["_cap"])

    rng = random.Random(SEED)
    # control: the must-haves plus a random fill to 50
    control = [r for r in sp if r["ticker"] in SP_MUST]
    rest = [r for r in sp if r["ticker"] not in SP_MUST]
    rng.shuffle(rest)
    control += rest[:50 - len(control)]

    # experiment: must-haves, then 15 largest, 20 from the middle, 15 smallest
    chosen = [r for r in new if r["ticker"] in NEW_MUST]
    taken = {r["ticker"] for r in chosen}
    n = len(new)
    bands = [(0, 60, 15), (n // 2 - 150, n // 2 + 150, 20), (n - 80, n, 15)]
    for lo, hi, k in bands:
        pool = [r for r in new[max(lo, 0):hi] if r["ticker"] not in taken]
        rng.shuffle(pool)
        for r in pool[:k]:
            chosen.append(r); taken.add(r["ticker"])
    chosen = chosen[:50]

    rows = [(r["cik"], r["ticker"], r["company"], "control") for r in control] + \
           [(r["cik"], r["ticker"], r["company"], "new") for r in chosen]
    with open(OUT, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["cik", "ticker", "company", "added"])
        for cik, tk, co, group in rows:
            w.writerow([cik, tk, co, group])
    print(f"{len(control)} control + {len(chosen)} new -> {OUT}")
    print("new names:", ", ".join(r["ticker"] for r in chosen))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
