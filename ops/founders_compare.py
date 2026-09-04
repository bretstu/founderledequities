#!/usr/bin/env python3
"""Two founders files side by side: every company whose verdict changed,
with the evidence each side gave.

    python3 ops/founders_compare.py founders.csv _staging/founders.csv

Built for the day the reader replaced the regex: the only honest way to
ship a classifier change is to read every verdict it moved. Prints the
flips first (yes to no, no to yes), then the softer moves (to or from
uncertain), then a count. Exit code is the number of flips, so a script
can refuse to deploy a change nobody has read.
"""
import csv
import sys


def load(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return {r["ticker"].strip().upper(): r for r in csv.DictReader(fh)}


def main(a_path, b_path, width=170):
    a, b = load(a_path), load(b_path)
    flips, moves = [], []
    for t in sorted(set(a) | set(b)):
        ra, rb = a.get(t), b.get(t)
        if ra is None or rb is None:
            continue
        fa, fb = (ra.get("founder") or "").lower(), (rb.get("founder") or "").lower()
        if fa == fb:
            continue
        (flips if {fa, fb} == {"yes", "no"} else moves).append((t, ra, rb))

    def show(items, title):
        print(f"\n== {title}: {len(items)}")
        for t, ra, rb in items:
            print(f"\n{t}  {ra.get('ceo','')}")
            for tag, r in (("before", ra), ("after ", rb)):
                ev = " ".join((r.get("evidence") or "").split())[:width]
                named = r.get("founders_named") or ""
                print(f"  {tag}: {r.get('founder'):9} {r.get('method','')[:60]}")
                if named:
                    print(f"          founders named: {named[:100]}")
                if ev:
                    print(f"          {ev}")

    show(flips, "FLIPS (yes <-> no)")
    show(moves, "moves (to or from uncertain / unknown)")
    print(f"\n{len(flips)} flips, {len(moves)} softer moves, "
          f"{sum(1 for t in a if t in b and (a[t].get('founder') or '').lower() == (b[t].get('founder') or '').lower())} unchanged")
    return len(flips)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2]))
