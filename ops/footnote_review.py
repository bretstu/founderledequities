#!/usr/bin/env python3
"""THE REVIEW LIST (2026-09-18): every line the reader labelled disclaimed or
partial, with the filer's words and a register row ready to paste into
universe/exclusions.csv once a person has read the filing and agrees.
    python3 ops/footnote_review.py                    # everything not yet reviewed
    python3 ops/footnote_review.py --reviewed KEY ok   # mark a line reviewed (ok / no), so it is not shown again
    python3 ops/footnote_review.py --all              # reviewed ones too
NOTE: the register matches a class + direct/indirect today; a row for one
vehicle among several needs the vehicle column, which lands with phase two.
Until then a pasted row excludes the whole class, so read the line's
neighbours before pasting.
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
READS = os.path.join(ROOT, "universe", "footnote-reads.csv")
REVIEWED = os.path.join(ROOT, "universe", "footnote-reviewed.csv")


def main(argv):
    if "--reviewed" in argv:
        i = argv.index("--reviewed")
        key, verdict = argv[i + 1], (argv[i + 2] if len(argv) > i + 2 else "ok")
        new = not os.path.exists(REVIEWED)
        with open(REVIEWED, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["key", "verdict", "note"])
            w.writerow([key, verdict, " ".join(argv[i + 3:])])
        print(f"  marked {key}: {verdict}")
        return 0
    reviewed = {}
    if os.path.exists(REVIEWED):
        reviewed = {r["key"]: r for r in csv.DictReader(open(REVIEWED, encoding="utf-8-sig"))}
    if not os.path.exists(READS):
        print("  no readings yet: python3 ops/footnote_reads.py")
        return 0
    rows = [r for r in csv.DictReader(open(READS, encoding="utf-8-sig")) if r["label"] in ("disclaimed", "partial")]
    if "--all" not in argv:
        rows = [r for r in rows if r["key"] not in reviewed]
    if not rows:
        print("  nothing to review")
        return 0
    rows.sort(key=lambda r: (r["ticker"], -float(r["shares"] or 0)))
    ciks = {}
    pp = os.path.join(ROOT, "panel.csv")
    if os.path.exists(pp):
        ciks = {x["ticker"]: x["cik"] for x in csv.DictReader(open(pp, encoding="utf-8-sig"))}
    for r in rows:
        who = "held directly" if r["direct"] == "D" else f"by {r['nature']}"
        frac = f" · fraction {r['fraction']}" if r.get("fraction") else ""
        print(f"\n== {r['ticker']} · {r['ceo']} · {r['security']} {who} · {float(r['shares'] or 0):,.0f} shares · [{r['label']}{frac}]")
        print(f"   \"{r['quote']}\"")
        print(f"   {r['reason']}")
        print(f"   filing: {r['url']}   key: {r['key']}")
        reason = r["quote"].replace('"', "'")
        cik = ciks.get(r["ticker"], "<cik>")
        print(f"   register row (paste after reading): {cik},{r['ticker']},{r['security']},{r['direct']},\"{reason}\",{r['url']},,,")
    print(f"\n  {len(rows)} line(s). Mark one reviewed: python3 ops/footnote_review.py --reviewed <key> ok|no <note>")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
