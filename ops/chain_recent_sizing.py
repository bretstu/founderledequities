"""THE CHAIN, FILING TO FILING (2026-09-17). One person's filings in the
window, Form 3s excluded; each open step (history.csv's `unexplained`,
the ledger's per-filing residue in one split-adjusted basis) measured
against the position it moved from or to.
    python3 ops/chain_recent_sizing.py [--months 12] [--list]
"""
import csv, datetime as dt, sys
from collections import Counter, defaultdict

def num(v):
    try: return float(v) if v not in (None, "") else None
    except ValueError: return None

def main(argv):
    months = int(argv[argv.index("--months") + 1]) if "--months" in argv else 12
    since = (dt.date.today() - dt.timedelta(days=30 * months)).isoformat()
    panel = {r["ticker"]: r for r in csv.DictReader(open("panel.csv", encoding="utf-8-sig"))}
    by = defaultdict(list)
    for h in csv.DictReader(open("history.csv", encoding="utf-8-sig")):
        if h.get("date", "") >= since and (h.get("form") or "").startswith(("4", "5")):
            by[h["ticker"]].append(h)
    grades, ex = Counter(), defaultdict(list)
    for tk, p in panel.items():
        sh = num(p.get("shares"))
        if not sh or p.get("pct") in ("", None): continue
        owner = p.get("owner_cik") or ""
        rows = sorted((h for h in by.get(tk, []) if (h.get("owner_cik") or owner) == owner), key=lambda h: (h.get("date", ""), h.get("accession", "")))
        steps = []
        for h in rows:
            u = num(h.get("unexplained")) or 0.0
            if abs(u) < 1: continue
            after = abs(num(h.get("shares")) or 0.0); before = abs(after - u)
            steps.append((abs(u) / max(before, after, 1.0) * 100, h))
        worst = max((x for x, _ in steps), default=0.0)
        g = ("no filings in window" if not rows else "pass: every filing closed" if not steps
             else "pass: open steps under 1%" if worst < 1 else "warn: an open step of 1-10%" if worst < 10 else "fail: an open step over 10%")
        grades[g] += 1
        if steps: ex[g].append((tk, p.get("ceo", "")[:22], len(rows), len(steps), f"{worst:.1f}%", max(steps, key=lambda x: x[0])[1].get("date", "")))
    print(f"filings in the last {months} months, {len(panel)} companies:")
    for g, k in sorted(grades.items(), key=lambda kv: -kv[1]): print(f"  {k:5}  {g}")
    for g in ("fail: an open step over 10%", "warn: an open step of 1-10%"):
        lst = sorted(ex[g], key=lambda x: -float(x[4].rstrip("%")))
        print(f"\n{g}: {len(lst)}")
        for tk, ceo, n, k, worst, day in lst[: (60 if "--list" in argv else 12)]:
            print(f"    {tk:6} {ceo:23} filings {n:3}  open {k:3}  worst step {worst:>7} on {day}")

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
