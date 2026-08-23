#!/usr/bin/env python3
"""Compare two run outputs to validate the free-path router.

The router is only useful if it reaches the SAME answer the model would have.
This diffs two CSVs on common_shares and pct_comparable and reports any row
where they disagree.

    python compare.py baseline_always.csv routed_auto.csv
"""
from __future__ import annotations

import csv
import sys


def load(path: str) -> dict[str, dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["ticker"]: r for r in csv.DictReader(fh)}


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    a_path, b_path = sys.argv[1], sys.argv[2]
    a, b = load(a_path), load(b_path)

    tickers = sorted(set(a) | set(b))
    print(f"\n{'ticker':<8} {'baseline':>16} {'routed':>16}  {'route':<6} verdict")
    print("-" * 74)

    agree = disagree = missing = 0
    calls_saved = 0

    for t in tickers:
        ra, rb = a.get(t), b.get(t)
        if not ra or not rb:
            print(f"{t:<8} {'--':>16} {'--':>16}  {'':<6} only in one file")
            missing += 1
            continue

        sa, sb = num(ra.get("shares_13d3")), num(rb.get("shares_13d3"))
        route = {"free_path": "FREE", "llm_extraction": "LLM"}.get(
            rb.get("resolution", ""), "-"
        )
        if route == "FREE":
            calls_saved += 1

        if sa is None and sb is None:
            verdict = "both failed"
        elif sa is None or sb is None:
            verdict = "ONE FAILED"
            disagree += 1
        elif sa == sb:
            verdict = "match"
            agree += 1
        else:
            rel = abs(sa - sb) / max(abs(sa), 1)
            verdict = f"DIFFER by {rel:.2%}"
            disagree += 1

        fa = f"{sa:,.0f}" if sa is not None else "-"
        fb = f"{sb:,.0f}" if sb is not None else "-"
        print(f"{t:<8} {fa:>16} {fb:>16}  {route:<6} {verdict}")

    total = len(tickers)
    print("-" * 74)
    print(f"agree: {agree}/{total}   disagree: {disagree}   missing: {missing}")
    print(f"routed free (no API call): {calls_saved}/{total}")
    if disagree:
        print("\nAny DIFFER row means the router accepted a number the model "
              "would have adjusted. Inspect those before trusting free mode:")
        print("  python -m ceo_ownership.cli inspect --ticker <TICKER>")
    else:
        print("\nNo disagreements: the router matched the paid path on every row.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
