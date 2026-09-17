"""How the panel would regrade under the four-check evidence model
(2026-09-17 proposal), from panel.csv alone. Prints the crosstab of today's
grade against the proposed one, and the reasons that decide the proposed
grade, so the design can be judged before it is built.
    python3 grade_sizing.py [panel.csv]
"""
import csv
import datetime as dt
import re
import sys
from collections import Counter, defaultdict


def num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def days(a, b):
    try:
        return abs((dt.date.fromisoformat(a[:10]) - dt.date.fromisoformat(b[:10])).days)
    except (ValueError, TypeError):
        return None


def grade(r):
    """-> (grade, {check: (level, reason)})"""
    checks = {}
    flags = " | ".join(x for x in (r.get("problems", ""), r.get("cautions", "")) if x)
    sh = num(r.get("shares"))
    if r.get("pct") in ("", None) or sh is None:
        return "none", {}

    # 1. CHAIN: the flows against the holding
    m = re.search(r"leave ([\d,]+) unexplained against a holding of ([\d,]+)", flags)
    if m:
        res = float(m.group(1).replace(",", "")) / max(float(m.group(2).replace(",", "")), 1) * 100
        checks["chain"] = ("fail", f"{res:.0f}% of the holding is not explained by the flows") if res > 10 else ("warn", f"{res:.1f}% of the holding is not explained by the flows")
    elif "walk did not settle" in flags:
        checks["chain"] = ("fail", "the walk did not settle; the total is a floor")
    else:
        checks["chain"] = ("pass", "")

    # 2. STATEMENT: freshness and wholeness
    if "fewer lines" in flags or "does not reconcile" in flags:
        checks["statement"] = ("warn", "the newest filing states fewer lines than the one before it")
    else:
        checks["statement"] = ("pass", "")
    m = re.search(r"last stated (\d{4})-\d{2}-\d{2} \(([\d,]+) shares\)", flags)   # a retired class, closed: fine
    stale = re.search(r"only ever footnoted", flags)
    if stale:
        checks["statement"] = ("fail", "a line is known only from a footnote")

    # 3. CLASSES
    if re.search(r"absent from the cover page", flags) or "partnership units" in flags.lower() or "not issued stock" in flags:
        checks["classes"] = ("fail", "a class with shares that the cover page does not count")
    elif "convertible class counted" in flags or "a class the company retired" in flags or "letter" in flags:
        checks["classes"] = ("warn", "a convertible class counted at 1:1" if "convertible" in flags else "a retired class closed by the cover")
    else:
        checks["classes"] = ("pass", "")

    # 4. DENOMINATOR
    gap = days(r.get("shares_as_of", ""), r.get("outstanding_as_of", ""))
    out = num(r.get("outstanding"))
    if out is None or "no cover-page share count" in flags or (out and sh and sh > out):
        checks["denominator"] = ("fail", "no usable cover-page count" if not out else "the holding exceeds the count")
    elif gap is not None and gap > 365:
        checks["denominator"] = ("fail", f"the count is {gap} days from the holding")
    elif gap is not None and gap > 150:
        checks["denominator"] = ("warn", f"the count is {gap} days from the holding")
    else:
        checks["denominator"] = ("pass", "")

    levels = {lvl for lvl, _ in checks.values()}
    g = "low" if "fail" in levels else "medium" if "warn" in levels else "high"
    return g, checks


def main(path):
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    cross = Counter()
    why = defaultdict(Counter)
    movers = defaultdict(list)
    for r in rows:
        g, checks = grade(r)
        old = r.get("confidence") or "none"
        cross[(old, g)] += 1
        for c, (lvl, reason) in checks.items():
            if lvl != "pass":
                why[g][f"{c}: {lvl}"] += 1
        if old != g and g != "none":
            movers[(old, g)].append((r["ticker"], next((f"{c} {lvl}: {rs}" for c, (lvl, rs) in checks.items() if lvl == ("fail" if g == "low" else "warn")), "")))
    order = ["high", "medium", "low", "none"]
    print("today \\ proposed", *[f"{g:>8}" for g in order])
    for o in order:
        print(f"{o:16}", *[f"{cross[(o, g)]:>8}" for g in order])
    print("\nwhat decides the proposed grade (companies, by check and level):")
    for g in ("medium", "low"):
        for k, n in why[g].most_common():
            print(f"  {g:7} {k:22} {n}")
    print("\nmovers (up to 8 per cell):")
    for (o, g), lst in sorted(movers.items()):
        print(f"  {o} -> {g}: {len(lst)}")
        for tk, reason in lst[:8]:
            print(f"      {tk:6} {reason[:110]}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "panel.csv")
