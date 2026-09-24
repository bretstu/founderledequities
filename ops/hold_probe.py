#!/usr/bin/env python3
"""HOW THE STAKE IS HELD -- THE PROBE, THIRD PASS (2026-09-24). Read-only.

The first two passes rebuilt the breakdown from raw filings and re-fought
wars the nightly walk already wins (splits, spellings, staleness, the
register). This pass fights nothing: it RUNS THE LEDGER -- the same
build_ledger the nightly uses, same exclusions, same keying -- and prints
its final state: every (class, direct-or-indirect) group the newest filings
state, vehicle by vehicle, with the statement's date and accession. The sum
is led.total, the very number the pipeline reports, so the question "do
the vehicles tally to what we publish" is answered by construction; what
the eye is here to judge is the DECOMPOSITION -- whether the lines read
like a section the page could show.

    python3 ops/hold_probe.py META TSLA DELL ECHO UI NVDA ABNB PLTR
    python3 ops/hold_probe.py --top 15
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from fle.edgar import EdgarClient                    # noqa: E402
from fle.exclusions import read_exclusions           # noqa: E402
from fle.identity import peo_from_certification      # noqa: E402
from fle.ledger import build_ledger, closed_groups   # noqa: E402
from fle.outstanding import shares_outstanding       # noqa: E402


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def num(x):
    try:
        return float(str(x).replace(",", ""))
    except Exception:
        return None


def main(argv):
    client = EdgarClient()
    excl = read_exclusions(os.path.join(ROOT, "universe", "exclusions.csv"))
    panel = {r["ticker"].upper(): r for r in read("panel.csv")}
    if argv and argv[0] == "--top":
        n = int(argv[1]) if len(argv) > 1 else 10
        founders = {r["ticker"].upper() for r in read("founders.csv") if (r.get("founder") or "").lower() in ("1", "true", "yes", "y")}
        picks = sorted((r for t, r in panel.items() if t in founders and num(r.get("pct"))),
                       key=lambda r: -num(r.get("pct")))[:n]
        tks = [r["ticker"].upper() for r in picks]
    else:
        tks = [t.upper() for t in argv] or ["META", "TSLA", "DELL", "ECHO", "UI"]

    for tk in tks:
        r = panel.get(tk)
        if not r:
            print(f"\n== {tk}: not on the panel ==")
            continue
        want = num(r.get("shares"))
        cik = int(r["cik"])
        try:
            cert = peo_from_certification(client, cik)
            if not cert:
                print(f"\n== {tk}: no certification, skipped ==")
                continue
            out = shares_outstanding(client, cik)
            led = build_ledger(client, cik, owner_name=cert.name,
                               share_classes=out.classes if out.ok else 0,
                               class_members=out.per_class,
                               exclude=excl.for_issuer(cik))
        except Exception as e:
            print(f"\n== {tk}: walk failed: {e} ==")
            continue
        total = led.total          # a @property: groups_total over the groups, split-adjusted
        print(f"\n== {tk} · {r.get('ceo','')} · panel {want:,.0f} ({r.get('pct','?')}%) · ledger total {total:,.0f} "
              f"({'ties' if want and abs(total-want)<=max(1.0,(want)*0.001) else f'off by {total-(want or 0):+,.0f}'}) ==")
        closed = {k for k, _g, _c in closed_groups(led.groups, getattr(led, "retired", None) or {}, "")}
        groups = sorted(led.groups.items(), key=lambda kv: -kv[1].shares)
        open_sum = 0.0
        for key, g in groups:
            sec, di = key
            gone = key in closed
            if not gone:
                open_sum += g.shares
            print(f"   {sec}  ·  {di}  ·  {g.shares:,.0f} shares  ·  stated {g.as_of or g.filed}  ·  {g.accession}"
                  + ("  ·  CLOSED (not in the total)" if gone else ""))
            vs = g.vehicles()
            for veh, amt in sorted(vs.items(), key=lambda kv: -kv[1]):
                share = f"{amt/want*100:5.1f}%" if want and not gone else "    ·"
                name = veh if isinstance(veh, str) else " ".join(str(p) for p in veh if p)
                label = name or ("direct" if di == "D" else "indirect, unstated")
                print(f"        {amt:>15,.0f}  {share}  {label[:64]}")
        if abs(open_sum - total) > 1:
            print(f"   (open groups as filed sum {open_sum:,.0f}; the total {total:,.0f} is split-adjusted)")
        if led.partnership_units:
            print(f"   partnership units beside the classes: {led.partnership_units:,.0f}")
        if led.note:
            print(f"   note: {led.note}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
