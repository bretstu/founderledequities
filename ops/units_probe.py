#!/usr/bin/env python3
"""THE UNITS-OUTSTANDING PROBE (2026-09-24). The exchanged-basis rule for a
founder whose economics sit in operating-partnership units with no paired
class (Blackstone, UWM, Carvana, the UPREITs) needs one number the cover
does not give: the UNITS OUTSTANDING. This asks the company's XBRL for it.

    python3 ops/units_probe.py                 # the census-excluded companies and every NO MATCH Up-C
    python3 ops/units_probe.py UWMC,CVNA,SLG   # a few

For each company it lists every XBRL fact whose name says units (or the
noncontrolling-interest percentage, which yields the same thing), with the
latest value and its date, so we see whether the number exists structurally
and under which tag. No model. One company-facts read per company.
"""
from __future__ import annotations

import csv
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fle.edgar import EdgarClient  # noqa: E402

UNIT_TAG = re.compile(r"unit|partnershipinterest|noncontrollinginterest.*(percent|ownership)|minorityinterestownership", re.I)
NOT_UNIT = re.compile(r"pershare|perunit|weightedaverage|dividend|distribution|compensation|restricted|incentive|fairvalue|carrying", re.I)


def latest(fact):
    """The newest instant value across units-of-measure of one XBRL fact."""
    best = None
    for uom, vals in (fact.get("units") or {}).items():
        for v in vals:
            if "val" not in v:
                continue
            key = (v.get("end") or v.get("instant") or "", v.get("filed") or "")
            if best is None or key > best[0]:
                best = (key, v["val"], uom, v.get("form", ""))
    return best


def main(argv):
    panel = {r["ticker"]: r for r in csv.DictReader(open(os.path.join(ROOT, "panel.csv"), encoding="utf-8-sig"))}
    sp = {r["ticker"]: r for r in csv.DictReader(open(os.path.join(ROOT, "universe", "sp500-2026-09-17.csv"), encoding="utf-8-sig"))} if os.path.exists(os.path.join(ROOT, "universe", "sp500-2026-09-17.csv")) else {}
    auto = list(csv.DictReader(open(os.path.join(ROOT, "universe", "partnerships-auto.csv"), encoding="utf-8-sig")))
    if argv:
        want = [t.strip().upper() for t in argv[0].split(",")]
    else:
        want = sorted({r["ticker"] for r in auto if (r.get("decision") or r.get(list(r.keys())[1]) or "").strip() == "exclude"})
    c = EdgarClient()
    found, missing = [], []
    for tk in want:
        row = panel.get(tk) or sp.get(tk) or next((r for r in auto if r["ticker"] == tk), None)
        cik = row.get("cik") if row else None
        if not cik:
            print(f"  {tk:6} no CIK on file"); missing.append(tk); continue
        try:
            facts = c.company_facts(int(cik))
        except Exception as e:  # noqa: BLE001
            print(f"  {tk:6} company facts: {e.__class__.__name__}"); missing.append(tk); continue
        hits = []
        for taxo, tags in (facts.get("facts") or {}).items():
            for name, fact in tags.items():
                if UNIT_TAG.search(name) and not NOT_UNIT.search(name):
                    b = latest(fact)
                    if b:
                        hits.append((f"{taxo}:{name}", b[1], b[2], b[0][0], b[3]))
        hits.sort(key=lambda h: -abs(h[1]) if isinstance(h[1], (int, float)) else 0)
        if hits:
            found.append(tk)
            print(f"\n  {tk:6} {(row.get('company') or row.get('name') or '')[:34]:34} {len(hits)} unit-like fact(s)")
            for name, val, uom, end, form in hits[:6]:
                sval = f"{val:,.0f}" if isinstance(val, (int, float)) and abs(val) >= 1 else f"{val}"
                print(f"        {name[:58]:58} {sval:>16} {uom:8} {end} {form}")
        else:
            missing.append(tk)
            print(f"\n  {tk:6} {(row.get('company') or row.get('name') or '')[:34]:34} no unit-like facts in XBRL")
    print(f"\n  units in XBRL for {len(found)} of {len(want)}: {', '.join(found)}")
    print(f"  nothing structured for {len(missing)}: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
