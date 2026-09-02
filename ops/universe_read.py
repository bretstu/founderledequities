#!/usr/bin/env python3
"""Checkpoint two: read the full-universe results before anything ships.

    python3 ops/universe_read.py _staging/u-panel.csv _staging/u-history.csv \
        _staging/u-founders.csv ../founderledequities/sp500.csv

Every section is a question a skeptical reader would ask. Sections skip
themselves gracefully if a column is absent -- say so rather than crash.
"""
import csv
import sys
from collections import Counter


def _f(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def main(panel_p, hist_p, founders_p, prod_p) -> int:
    panel = list(csv.DictReader(open(panel_p, encoding="utf-8-sig")))
    prod = {r["ticker"]: r for r in
            csv.DictReader(open(prod_p, encoding="utf-8-sig"))}
    sp = set(prod)
    core = [r for r in panel if r["ticker"] in sp]
    new = [r for r in panel if r["ticker"] not in sp]
    print(f"== panel: {len(core)} S&P, {len(new)} new ==")

    def dist(rows, col="confidence"):
        c = Counter((r.get(col) or "?") for r in rows)
        n = max(1, len(rows))
        return ", ".join(f"{k} {v} ({100*v//n}%)" for k, v in
                         sorted(c.items(), key=lambda kv: -kv[1]))
    print(f"  confidence S&P: {dist(core)}")
    print(f"  confidence new: {dist(new)}")

    for label, rows in (("S&P", core), ("new", new)):
        probs = Counter()
        for r in rows:
            for p in (r.get("problems") or "").split("|"):
                if p.strip():
                    probs[p.strip()[:52]] += 1
        top = ", ".join(f"{k} x{v}" for k, v in probs.most_common(5))
        print(f"  problems {label}: {top or 'none'}")

    errs = [r for r in panel if (r.get("error") or "").strip()]
    print(f"\n== {len(errs)} error rows ==")
    for r in errs:
        print(f"  {r['ticker']:6} {(r.get('error') or '')[:88]}")

    # THE WRONG-PERSON DETECTOR: certification signer and matched owner
    # sharing not one name token is how WRB was caught. Zero is the pass.
    try:
        sys.path.insert(0, ".")
        from fle.names import normalize_name
        odd = []
        for r in panel:
            ceo, own = (r.get("ceo") or ""), (r.get("owner_name") or "")
            if not ceo or not own:
                continue
            a = {t for t in normalize_name(ceo) if len(t) > 1}
            b = {t for t in normalize_name(own) if len(t) > 1}
            if a and b and not (a & b):
                odd.append((r["ticker"], ceo, own))
        print(f"\n== surname census: {len(odd)} rows where cert and owner "
              f"share no name token ==")
        for t, c, o in odd[:12]:
            print(f"  {t:6} cert={c[:30]!r} owner={o[:30]!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"\n== surname census skipped: {exc} ==")

    # S&P DRIFT: the same company read by the new code vs what prod
    # serves today. Small drift = newer filings; a big move = a question.
    drifted = []
    key = "pct" if (panel and "pct" in panel[0]) else None
    pkey = "pct" if (prod and "pct" in next(iter(prod.values()))) else None
    if key and pkey:
        for r in core:
            a, b = _f(r.get(key)), _f(prod[r["ticker"]].get(pkey))
            if a is not None and b is not None and abs(a - b) > max(0.5, 0.25 * max(a, b)):
                drifted.append((r["ticker"], b, a))
        print(f"\n== S&P drift vs prod: {len(drifted)} companies moved "
              f">25% (and >0.5pt) ==")
        for t, b, a in sorted(drifted, key=lambda x: -abs(x[2] - x[1]))[:12]:
            print(f"  {t:6} prod {b:.3f}% -> new {a:.3f}%")
    else:
        print("\n== S&P drift skipped: no pct column to compare ==")

    # THE WALK'S VERDICT, per company
    hist_rows = list(csv.DictReader(open(hist_p, encoding="utf-8-sig")))
    if hist_rows and "matches_panel" in hist_rows[0]:
        last = {}
        for r in hist_rows:
            last[r["ticker"]] = r
        bad = [t for t, r in sorted(last.items())
               if (r.get("matches_panel") or "").upper() in ("FALSE", "0", "NO")]
        print(f"\n== walk: {len(last)} companies, {len(bad)} do not end on "
              f"the panel's figure ==")
        print("  " + ", ".join(bad[:40]) + (" ..." if len(bad) > 40 else ""))
    else:
        print("\n== walk section skipped: no matches_panel column ==")

    # FOUNDER RATES: the thesis, measured
    try:
        frows = list(csv.DictReader(open(founders_p, encoding="utf-8-sig")))
        fmap = {r["ticker"]: (r.get("founder") or "") for r in frows}
        for label, rows in (("S&P", core), ("new", new)):
            c = Counter(fmap.get(r["ticker"], "?") for r in rows)
            n = max(1, len(rows))
            print(f"\n== founders {label}: yes {c.get('yes',0)} "
                  f"({100*c.get('yes',0)//n}%), no {c.get('no',0)}, "
                  f"uncertain {c.get('uncertain',0)}, "
                  f"unknown {c.get('unknown',0)} ==")
    except FileNotFoundError:
        print("\n== founders section skipped: file not found ==")

    # THE LEADERBOARD SMELL TEST: top stakes are where a wrong number
    # embarrasses loudest -- eyeball the top 15
    key2 = "pct" if key else None
    if key2:
        ranked = sorted((r for r in panel if _f(r.get("pct")) is not None),
                        key=lambda r: -_f(r["pct"]))
        print("\n== top 15 stakes (open each form4_url before trusting) ==")
        for r in ranked[:15]:
            mark = "" if r["ticker"] in sp else "  [new]"
            print(f"  {r['ticker']:6} {_f(r['pct']):7.2f}%  "
                  f"{(r.get('ceo') or '')[:34]}{mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:5]))
