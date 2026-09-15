#!/usr/bin/env python3
"""THE ACCEPTANCE RULE FOR THE SPLIT-BASIS CHANGE (2026-09-15): every
company whose stake changed must carry the caution naming the class the
ledger restated through a split, the filing it rests on and the factor.
A change without it is a stop.

    python3 ops/check_split_basis.py                  # reads panel-diff.csv and panel.csv
    python3 ops/check_split_basis.py panel-diff.csv panel.csv
"""
import csv
import sys


def main(diff_p="panel-diff.csv", panel_p="panel.csv"):
    panel = {(r.get("ticker") or "").upper(): r for r in csv.DictReader(open(panel_p, encoding="utf-8-sig"))}
    rows = list(csv.DictReader(open(diff_p, encoding="utf-8-sig")))
    if not rows:
        print("  panel-diff.csv is empty: nothing changed")
        return 0
    bad = 0
    print(f"  {'ticker':<7}{'chief executive':<24}{'before':>9}{'after':>9}  verdict")
    for r in rows:
        tk = (r.get("ticker") or "").upper()
        p = panel.get(tk, {})
        caut = p.get("cautions") or ""
        expl = [c for c in caut.split("|") if "restated" in c and "through the split" in c]
        b, a = r.get("pct_before") or r.get("shares_before") or "", r.get("pct_after") or p.get("pct") or ""
        try:
            b = f"{float(b):.2f}%" if "pct" in "".join(r.keys()) else f"{int(float(b)):,}"
            a = f"{float(a):.2f}%"
        except (TypeError, ValueError):
            pass
        if expl:
            print(f"  {tk:<7}{(r.get('ceo') or p.get('ceo') or '')[:22]:<24}{b:>9}{a:>9}  ok: {expl[0]}")
        else:
            bad += 1
            print(f"  {tk:<7}{(r.get('ceo') or p.get('ceo') or '')[:22]:<24}{b:>9}{a:>9}  UNEXPLAINED: changed with no restated-class caution; stop and read the page")
    print(f"\n  {len(rows)} changed, {len(rows) - bad} explained by a class carried through a split, {bad} unexplained")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
