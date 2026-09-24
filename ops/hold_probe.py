#!/usr/bin/env python3
"""HOW THE STAKE IS HELD -- THE PROBE (2026-09-24). Read-only exploration,
no site output. Before building a "how the stake is held" section, measure
whether the filings can actually state one: for each named company, walk the
chief executive's Section 16 filings newest-first (the same cached documents
the walk reads), collect the NEWEST stated balance per line -- a line being
(share class, direct-or-indirect, the nature text's vehicle) -- and compare
the sum against the panel's verified share count.

    python3 ops/hold_probe.py META TSLA DELL ECHO UI
    python3 ops/hold_probe.py --top 10            # largest founder stakes by pct

The verdict per company:
  CLEAN      the lines sum to the panel's count within 0.5%
  EXPLAINED  they differ, but the register/exclusions cover the gap within 0.5%
  GAP        they differ and nothing on file explains it
  BARE       fewer than 2 lines: nothing to break down
Every line prints its as-of date and accession, so a stale vehicle is visible
as an old date, and the whole report is pasteable back into a conversation.
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from fle.edgar import EdgarClient                                    # noqa: E402
from fle.ledger import _parse, _t, _num, is_share_class, SECTION16, displace_amended  # noqa: E402
from ops.upc_census import person_filings, read                      # noqa: E402


def lines_for(client, cik, owner_cik, max_filings=60):
    """-> {key: (amount, as_of, accession)}: the newest stated balance per
    (class, D/I, nature) line across the person's filings, newest first.
    Within one filing the successive-balance rule from the census applies:
    a transaction row whose balance equals the previous row's balance plus
    or minus its own shares is the same line's next balance, not a new line."""
    best = {}
    docs = person_filings(client, cik, owner_cik)[:max_filings]
    for f in docs:
        root = _parse(client, int(cik), f)
        if root is None:
            continue
        when = f.get("reportDate") or f.get("filingDate") or ""
        acc = f.get("accessionNumber") or ""
        this = {}
        for tag in ("nonDerivativeTransaction", "nonDerivativeHolding"):
            for node in root.iter(tag):
                title = (_t(node, "securityTitle") or "").strip()
                if not title or not is_share_class(title):
                    continue
                amt = _num(node, "sharesOwnedFollowingTransaction")
                if amt is None:
                    continue
                di = _t(node, "directOrIndirectOwnership") or ""
                nat = (_t(node, "natureOfOwnership") or "").strip()
                base = (title[:48], di, nat[:60])
                shares = _num(node, "transactionShares") if tag == "nonDerivativeTransaction" else None
                prev = next((k for k in reversed(list(this)) if k[:3] == base), None)
                if prev is not None and shares is not None and (abs(this[prev] + shares - amt) < 1 or abs(this[prev] - shares - amt) < 1):
                    this[prev] = amt
                else:
                    this[base + (len(this),)] = amt
        for k, v in this.items():
            key = k[:3]                      # across filings, the newest statement of a line wins
            if key not in best:
                best[key] = (v, when, acc)
    return best


def num(x):
    try:
        return float(str(x).replace(",", ""))
    except Exception:
        return None


def main(argv):
    client = EdgarClient()
    panel = {r["ticker"].upper(): r for r in read(os.path.join(ROOT, "panel.csv"))}
    excl = {}
    xp = os.path.join(ROOT, "universe", "exclusions.csv")
    if os.path.exists(xp):
        for r in read(xp):
            excl.setdefault(r["ticker"].upper(), []).append(r)
    if argv and argv[0] == "--top":
        n = int(argv[1]) if len(argv) > 1 else 10
        founders = {r["ticker"].upper() for r in read(os.path.join(ROOT, "founders.csv")) if (r.get("founder") or "").lower() in ("1", "true", "yes", "y")}
        picks = sorted((r for t, r in panel.items() if t in founders and num(r.get("pct"))),
                       key=lambda r: -num(r.get("pct")))[:n]
        tks = [r["ticker"].upper() for r in picks]
    else:
        tks = [t.upper() for t in argv] or ["META", "TSLA", "DELL", "ECHO", "UI"]

    tallies = {"CLEAN": 0, "EXPLAINED": 0, "GAP": 0, "BARE": 0, "SKIP": 0}
    for tk in tks:
        r = panel.get(tk)
        if not r or not r.get("owner_cik"):
            print(f"\n== {tk}: not on the panel or no owner CIK ==")
            tallies["SKIP"] += 1
            continue
        want = num(r.get("shares"))
        lines = lines_for(client, r["cik"], r["owner_cik"])
        print(f"\n== {tk} · {r.get('ceo','')} · panel says {want:,.0f} shares ({r.get('pct','?')}%) ==")
        if len(lines) < 2:
            print("   BARE: fewer than two lines; nothing to break down")
            tallies["BARE"] += 1
            continue
        total = 0.0
        for (title, di, nat), (amt, when, acc) in sorted(lines.items(), key=lambda kv: -kv[1][0]):
            total += amt
            share = f"{amt/want*100:5.1f}%" if want else "    ?"
            vehicle = nat if nat else ("direct" if di == "D" else "indirect, nature unstated")
            print(f"   {amt:>15,.0f}  {share}  {title[:34]:<34}  {di or '?'}  {vehicle[:52]}  as of {when}  {acc}")
        ex_rows = excl.get(tk, [])
        ex_sum = sum(num(x.get("shares")) or 0 for x in ex_rows)
        gap = total - (want or 0)
        verdict = "CLEAN" if want and abs(gap) <= want * 0.005 else \
                  "EXPLAINED" if want and abs(gap - ex_sum) <= want * 0.005 else "GAP"
        tallies[verdict] += 1
        print(f"   sum {total:,.0f} vs panel {want:,.0f} -> {gap:+,.0f} ({(gap/want*100) if want else 0:+.2f}%)"
              + (f"; register excludes {ex_sum:,.0f} in {len(ex_rows)} row(s)" if ex_rows else "")
              + f"  => {verdict}")
    print("\n== the tally ==")
    for k, v in tallies.items():
        if v:
            print(f"   {k:<10}{v}")
    print("   CLEAN + EXPLAINED is the buildable share; GAP names the reconciliation work; BARE would simply not show the section.")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
