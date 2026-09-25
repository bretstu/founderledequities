#!/usr/bin/env python3
"""WHAT THE RELABEL TOUCHED, AND NOTHING ELSE (2026-09-25). Run after the
first walk with the sale-natures reader, against the frozen baseline:

    python3 ops/label_diff.py universe/baseline-pre-stc/events.csv events.csv

Rows are keyed (ticker, accession, traded, code). The relabel's contract is
that ONLY the label column moves; a changed row whose shares, value,
holding_after or pct_after differ is a VIOLATION and is printed. The report
is the transition matrix, the tickers most touched, and the companies that
would newly qualify as never-sold -- the derived facts a reviewer checks
against the filings before trusting the deploy."""
import csv
import sys
from collections import Counter

INVARIANT = ["shares", "value", "holding_after", "pct_after", "net_change"]


def load(path):
    with open(path, encoding="utf-8-sig") as fh:
        return {(r["ticker"], r["accession"], r["traded"], r["code"]): r
                for r in csv.DictReader(fh)}


def sellers(rows):
    """ever_sold under build_site_data's rule: a stake-reducing S that is
    neither pre-IPO nor a mandated tax cover."""
    out = set()
    for r in rows.values():
        if r["code"] != "S" or (r.get("pre_ipo") or "") in ("1", "true", "True"):
            continue
        if (r.get("label") or "") == "sold to cover tax":
            continue
        out.add(r["ticker"])
    return out


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    base, new = load(sys.argv[1]), load(sys.argv[2])
    trans, touched, violations = Counter(), Counter(), 0
    for k, b in base.items():
        n = new.get(k)
        if n is None:
            continue
        if (b.get("label") or "") != (n.get("label") or ""):
            trans[(b.get("label") or "", n.get("label") or "")] += 1
            touched[k[0]] += 1
            bad = [c for c in INVARIANT if (b.get(c) or "") != (n.get(c) or "")]
            if bad:
                violations += 1
                print(f"VIOLATION {k}: label changed AND {bad} moved")
    print(f"{sum(trans.values())} row(s) relabeled across {len(touched)} company(ies); "
          f"{violations} violation(s)")
    for (a, b), n in trans.most_common():
        print(f"  {n:5d}  {a!r} -> {b!r}")
    print("most touched:", ", ".join(f"{t} {n}" for t, n in touched.most_common(10)))
    gained = sellers(base) - sellers(new)
    if gained:
        print(f"newly never-sold ({len(gained)}): {', '.join(sorted(gained))} "
              f"-- review each against its filings before trusting the screen")
    if violations:
        sys.exit(1)


if __name__ == "__main__":
    main()
