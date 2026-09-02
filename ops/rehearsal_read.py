#!/usr/bin/env python3
"""Read the rehearsal's results: what the new names did that the known
ones didn't. Run after panel + history + events on universe/rehearsal-100.csv.

    python3 ops/rehearsal_read.py _staging/rh-panel.csv _staging/rh-history.csv universe/sp500-<date>.csv
"""
import csv
import sys
from collections import Counter


def main(panel_path, history_path, prod_panel_path) -> int:
    rows = list(csv.DictReader(open(panel_path, encoding="utf-8-sig")))
    uni = {r["ticker"]: r["added"] for r in
           csv.DictReader(open("universe/rehearsal-100.csv", encoding="utf-8-sig"))}
    ctrl = [r for r in rows if uni.get(r["ticker"]) == "control"]
    new = [r for r in rows if uni.get(r["ticker"]) == "new"]

    def dist(group):
        c = Counter(r.get("confidence") for r in group)
        return ", ".join(f"{k} {v}" for k, v in sorted(c.items(), key=lambda kv: -kv[1]))

    print(f"panel: {len(ctrl)} control, {len(new)} new")
    print(f"  confidence  control: {dist(ctrl)}")
    print(f"  confidence  new:     {dist(new)}")
    for label, group in (("control", ctrl), ("new", new)):
        probs = Counter()
        for r in group:
            for p in (r.get("problems") or "").split("|"):
                if p.strip():
                    probs[p.strip()[:60]] += 1
        print(f"  problems ({label}):")
        for k, v in probs.most_common(8):
            print(f"     {v:3}  {k}")
    settle = [r["ticker"] for r in new if "did not settle" in (r.get("problems") or "")]
    officer = [r["ticker"] for r in new if "not flagged as an officer" in (r.get("problems") or "")]
    zero = [r["ticker"] for r in new if float(r.get("pct") or 0) == 0.0]
    print(f"  new: {len(settle)} did not settle {settle}; {len(officer)} officer-flag gaps {officer}; "
          f"{len(zero)} at 0.000% {zero}")

    # the control group against prod: every changed number needs a reason
    prod = {r["ticker"]: r for r in csv.DictReader(open(prod_panel_path, encoding="utf-8-sig"))}
    moved = []
    for r in ctrl:
        p = prod.get(r["ticker"])
        if not p:
            continue
        try:
            a, b = float(r.get("pct") or 0), float(p.get("pct") or 0)
        except ValueError:
            continue
        if abs(a - b) > 0.01 or (r.get("ceo") or "") != (p.get("ceo") or ""):
            moved.append((r["ticker"], p.get("ceo"), p.get("pct"), "->", r.get("ceo"), r.get("pct")))
    print(f"  control vs prod: {len(moved)} changed")
    for m in moved:
        print("     ", *m)

    # restated census on the walk
    hist = list(csv.DictReader(open(history_path, encoding="utf-8-sig")))
    by = Counter(r["ticker"] for r in hist if r.get("restated"))
    tot = Counter(r["ticker"] for r in hist)
    print(f"history: {len(hist):,} rows across {len(tot)} companies; "
          f"{sum(by.values())} marked restated across {len(by)} companies")
    heavy = [(t, by[t], tot[t]) for t in by if by[t] / max(tot[t], 1) > 0.25]
    if heavy:
        print("  companies with >25% of rows marked (read these):", heavy)
    walked = set(tot)
    missing = [r["ticker"] for r in rows if r["ticker"] not in walked]
    print(f"  not walked: {len(missing)} {missing}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__); raise SystemExit(2)
    raise SystemExit(main(*sys.argv[1:]))
