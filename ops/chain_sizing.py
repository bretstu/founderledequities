"""WHY THE CHAIN DOES NOT CLOSE (2026-09-17). For every company whose flows
leave more than the threshold unexplained, the likely cause, from panel.csv
alone (the chain columns added the same day):
    exchange     an inflow and an outflow of the same size (an up-C IPO's units
                 becoming shares: a grant and a forfeiture that were neither)
    split        the opening or the flows cross a split the feed did not carry
    unread       the walk read fewer filings than the person has
    pre-window   the opening is the oldest filing read and the residual is
                 positive: shares arrived before the window in a way no
                 filing states
    outflow      the residual is negative: shares left through a code the
                 flows did not count, or a vehicle the holding no longer lists
    unknown      none of the above
    python3 ops/chain_sizing.py [panel.csv] [--pct 10] [--list]
"""
import csv
import sys
from collections import Counter, defaultdict


def num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def cause(r):
    sh = num(r.get("shares")) or 0
    res = num(r.get("flow_residual"))
    if res is None or not sh:
        return None, None
    share = abs(res) / sh * 100
    codes = {}
    for part in (r.get("codes") or "").split("|"):
        if "=" in part:
            c, rest = part.split("=", 1)
            n, moved = rest.split(":", 1)
            codes[c] = num(moved.replace(",", "")) or 0
    granted, surrendered = num(r.get("granted")) or 0, num(r.get("surrendered")) or 0
    other_in, other_out = num(r.get("other_in")) or 0, num(r.get("other_out")) or 0
    if granted and surrendered and abs(granted - surrendered) / max(granted, surrendered) < 0.02 and granted > 0.5 * sh:
        return "exchange", share
    if other_in and other_out and abs(other_in - other_out) / max(other_in, other_out) < 0.02 and other_in > 0.5 * sh:
        return "exchange", share
    if (r.get("splits") or "").strip() and "none" not in (r.get("splits") or "").lower():
        return "split", share
    if (r.get("split_note") or "").strip():
        return "split", share
    if (r.get("opening_source") or "") == "oldest filing read" and res > 0:
        return "pre-window", share
    if res < 0:
        return "outflow", share
    return "unknown", share


def main(argv):
    path = next((a for a in argv if not a.startswith("--")), "panel.csv")
    thr = float(argv[argv.index("--pct") + 1]) if "--pct" in argv else 10.0
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    if "flow_residual" not in rows[0]:
        print("panel.csv has no chain columns yet; they arrive with the next walk after v234")
        return 1
    by = Counter()
    ex = defaultdict(list)
    n = 0
    for r in rows:
        c, share = cause(r)
        if c is None or share < thr:
            continue
        n += 1
        by[c] += 1
        ex[c].append((r["ticker"], r.get("ceo", "")[:22], f"{share:.0f}%", r.get("opening_source") or "-", r.get("filings_read") or "-"))
    print(f"{n} of {len(rows)} companies leave more than {thr:g}% of the holding unexplained")
    for c, k in by.most_common():
        print(f"  {c:11} {k}")
        for tk, ceo, share, src, read in ex[c][: (40 if "--list" in argv else 5)]:
            print(f"      {tk:6} {ceo:23} residual {share:>5}  opening: {src:20} filings read: {read}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
