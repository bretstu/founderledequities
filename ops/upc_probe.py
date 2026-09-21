#!/usr/bin/env python3
"""THE UP-C PROBE (2026-09-24). Run before building the exchanged-basis rule:

    python3 ops/upc_probe.py            # every company marked operating_partnership
    python3 ops/upc_probe.py HGTY,SYM   # a few

THE RULE IT PREVIEWS. An Up-C founder holds his economics as units of the
operating LLC and his votes as a paired class of the public company (Class V,
Class C, sometimes Class B), one share per unit. One unit + one paired share
exchanges for one Class A share. So: count the units (the money), exclude the
paired class (the vote on the same money), keep every other class, and divide
by the cover's total -- which already sums every class, and the paired class's
count IS the units outstanding, so the total is the exchanged base.

HOW THE PAIRING IS KNOWN: from the person's own filing. A share-class line
whose count equals his units is the wrapper. No 10-K, no census, no prior
knowledge of the structure. If no line matches, nothing is assumed.

THE THREE BUCKETS (the probe's verdict per company):
  PAIRED    a class matches the units -> count units, exclude the class; the number changes
  NO MATCH  units but no class equal to them (UPREIT OP units; a non-1:1 pairing) -> as today
  NO UNITS  the ledger has no units on the newest filings -> unaffected; listed to check the
            Form 3 gap (a Form 3's Table II units have no balance field)

Read-only. No model. One cover read and one ledger build per company.
"""
from __future__ import annotations

import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fle.edgar import EdgarClient             # noqa: E402
from fle.outstanding import shares_outstanding  # noqa: E402
from fle.ledger import build_ledger           # noqa: E402


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def main(argv):
    only = {t.strip().upper() for t in argv[0].split(",")} if argv else None
    panel = list(csv.DictReader(open(os.path.join(ROOT, "panel.csv"), encoding="utf-8-sig")))
    upc = [r for r in panel if (only and r["ticker"].upper() in only) or (not only and (r.get("operating_partnership") or "").lower() == "true")]
    print(f"  {len(upc)} compan{'y' if len(upc) == 1 else 'ies'} to read\n")
    c = EdgarClient()
    buckets = {"PAIRED": [], "NO MATCH": [], "NO UNITS": [], "ERROR": []}
    print(f"  {'TK':6} {'CEO':22} {'bucket':8} {'NOW':>7} {'EXCH':>7}  {'units':>14} {'wrapper':>14}  classes on the filing")
    for r in sorted(upc, key=lambda r: r["ticker"]):
        try:
            out = shares_outstanding(c, int(r["cik"]))
            led = build_ledger(c, int(r["cik"]), owner_cik=r["owner_cik"],
                               share_classes=out.classes if out.ok else 0, class_members=out.per_class)
        except Exception as e:  # noqa: BLE001
            buckets["ERROR"].append(r["ticker"])
            print(f"  {r['ticker']:6} {(r.get('ceo') or '')[:22]:22} ERROR    {e.__class__.__name__}")
            continue
        total = _f(out.shares) if out.ok else 0.0
        units = _f(getattr(led, "partnership_units", 0))
        by_class = {}
        for g in led.groups.values():
            by_class[g.security] = by_class.get(g.security, 0.0) + _f(g.shares)
        counted = sum(by_class.values())
        wrapper = None
        if units > 0:
            exact = [k for k, v in by_class.items() if abs(v - units) < 1]
            near = [k for k, v in by_class.items() if v and abs(v - units) / units < 0.005]
            wrapper = exact[0] if exact else (near[0] if len(near) == 1 else None)
        if units <= 0:
            b = "NO UNITS"; exch = counted / total * 100 if total else 0
        elif wrapper:
            b = "PAIRED"; exch = (counted - by_class[wrapper] + units) / total * 100 if total else 0
        else:
            b = "NO MATCH"; exch = counted / total * 100 if total else 0
        now = counted / total * 100 if total else 0
        buckets[b].append(r["ticker"])
        cls = ", ".join(f"{k[:22]}={v:,.0f}" for k, v in by_class.items())
        wtxt = f"{by_class[wrapper]:,.0f}" if wrapper else "-"
        print(f"  {r['ticker']:6} {(r.get('ceo') or '')[:22]:22} {b:8} {now:6.2f}% {exch:6.2f}%  {units:>14,.0f} {wtxt:>14}  {cls[:70]}")
    print()
    for b, ts in buckets.items():
        if ts:
            print(f"  {b:8} {len(ts):3}  {', '.join(ts)}")
    print("\n  NOW: what the site shows (units set aside). EXCH: units counted, the paired class excluded, over the cover total.")
    print("  PAIRED changes; NO MATCH and NO UNITS stay as today. NO UNITS with a Form 3-only record is the Form 3 units gap.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
