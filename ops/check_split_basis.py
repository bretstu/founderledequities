#!/usr/bin/env python3
"""THE ACCEPTANCE RULE FOR THE SPLIT-BASIS CHANGE (2026-09-15): every
company whose stake changed must carry the caution naming the class the
ledger restated through a split, the filing it rests on and the factor.
A change without it is a stop.

    python3 ops/check_split_basis.py                  # reads panel-diff.csv and panel.csv
    python3 ops/check_split_basis.py panel-diff.csv panel.csv ~/backups/pre-split-basis/panel.csv   # and knows a new filing from a rule change
"""
import csv
import sys


def main(diff_p="panel-diff.csv", panel_p="panel.csv", before_p=""):
    """Three verdicts. `before_p` is the panel the diff was taken against
    (the backup); with it, a company whose newest filing is newer than the
    backup's is a NEW FILING, not an unexplained change: the watcher and the
    nightly keep moving numbers on filings while a rule change is being
    judged (Castle, 2026-09-15, a planned sale filed the same afternoon)."""
    panel = {(r.get("ticker") or "").upper(): r for r in csv.DictReader(open(panel_p, encoding="utf-8-sig"))}
    before = {}
    if before_p:
        before = {(r.get("ticker") or "").upper(): r for r in csv.DictReader(open(before_p, encoding="utf-8-sig"))}
    rows = list(csv.DictReader(open(diff_p, encoding="utf-8-sig")))
    if not rows:
        print("  panel-diff.csv is empty: nothing changed")
        return 0
    bad = filed = 0
    print(f"  {'ticker':<7}{'chief executive':<24}{'before':>9}{'after':>9}  verdict")
    for r in rows:
        tk = (r.get("ticker") or "").upper()
        p = panel.get(tk, {})
        caut = p.get("cautions") or ""
        expl = [c for c in caut.split("|") if ("restated" in c and "through the split" in c) or "a split in the feed was not applied" in c]
        b, a = r.get("pct_before") or r.get("shares_before") or "", r.get("pct_after") or p.get("pct") or ""
        try:
            b = f"{float(b):.2f}%" if "pct" in "".join(r.keys()) else f"{int(float(b)):,}"
            a = f"{float(a):.2f}%"
        except (TypeError, ValueError):
            pass
        was = (before.get(tk) or {}).get("shares_as_of") or ""
        now = p.get("shares_as_of") or ""
        if expl:
            print(f"  {tk:<7}{(r.get('ceo') or p.get('ceo') or '')[:22]:<24}{b:>9}{a:>9}  ok: {expl[0]}")
        elif before and now and now > was:
            filed += 1
            print(f"  {tk:<7}{(r.get('ceo') or p.get('ceo') or '')[:22]:<24}{b:>9}{a:>9}  new filing: the holding is as of {now}, the backup's was {was or 'older'}; not the rule change")
        else:
            bad += 1
            print(f"  {tk:<7}{(r.get('ceo') or p.get('ceo') or '')[:22]:<24}{b:>9}{a:>9}  UNEXPLAINED: changed with no restated-class caution; stop and read the page")
    print(f"\n  {len(rows)} changed, {len(rows) - bad - filed} explained by a class carried through a split, "
          f"{filed} by a new filing, {bad} unexplained")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
