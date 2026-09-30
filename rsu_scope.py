#!/usr/bin/env python3
"""Scope the RSU-in-Table-I pattern from the cached filings (2026-09-29).

    cd ~/projects/founderledequities && .venv/bin/python rsu_scope.py

Reads every cached Form 3/4/5 XML under .cache/ (FLE_CACHE if set), keeps the
ones whose reporting owner is a CEO in panel.csv, and counts Table I
acquisitions (code A, non-derivative) whose footnote calls the securities
restricted stock units. Those units are in the site's numerator today.
Writes rsu_scope.csv (one row per company) and prints a summary.
No network, no model.
"""
import csv, os, re, sys, collections
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.environ.get("FLE_CACHE", os.path.join(ROOT, ".cache"))

owners = {}   # owner_cik -> (ticker, ceo)
for r in csv.DictReader(open(os.path.join(ROOT, "panel.csv"), encoding="utf-8-sig")):
    if r.get("owner_cik"):
        owners[str(int(r["owner_cik"]))] = (r["ticker"], r["ceo"])
current = {tk: float(r["shares"]) for tk, r in ((r["ticker"], r) for r in csv.DictReader(open(os.path.join(ROOT, "panel.csv"), encoding="utf-8-sig"))) if r.get("shares")}

RSU = re.compile(r"restricted\s+stock\s+units?|\bRSUs?\b|performance\s+(?:stock|share)\s+units?|\bPSUs?\b", re.I)
SETTLE = re.compile(r"upon\s+(?:the\s+)?(?:vesting|settlement)|received\s+upon|issued\s+upon|settle(?:d|ment)\s+of|converted\s+into|net\s+settle|in\s+settlement", re.I)
RSA = re.compile(r"shares?\s+of\s+restricted\s+stock|restricted\s+shares?|restricted\s+stock\s+award", re.I)

def t(n, p):
    e = n.find(p); return (e.text or "").strip() if e is not None and e.text else ""

hits = collections.defaultdict(lambda: {"filings": 0, "unit_grants": 0, "units": 0.0, "rsa_grants": 0, "first": "", "last": ""})
scanned = 0
for name in os.listdir(CACHE):
    p = os.path.join(CACHE, name)
    try:
        with open(p, "rb") as fh:
            head = fh.read(4096)
        if b"<ownershipDocument" not in head:
            continue
        root = ET.parse(p).getroot()
    except Exception:
        continue
    scanned += 1
    ocs = [str(int(t(ro, "reportingOwnerId/rptOwnerCik") or 0)) for ro in root.findall("reportingOwner")]
    who = next((owners[o] for o in ocs if o in owners), None)
    if not who:
        continue
    tk = who[0]
    fn = {x.get("id"): (x.text or "") for x in root.findall("footnotes/footnote")}
    period = t(root, "periodOfReport")
    h = hits[tk]; h["filings"] += 1
    for x in root.findall("nonDerivativeTable/nonDerivativeTransaction"):
        if t(x, "transactionCoding/transactionCode") != "A":
            continue
        if t(x, "transactionAmounts/transactionAcquiredDisposedCode/value") != "A":
            continue
        notes = " ".join(fn.get(y.get("id"), "") for y in x.iter("footnoteId"))
        sh = float(t(x, "transactionAmounts/transactionShares/value") or 0)
        if RSU.search(notes) and not RSA.search(notes) and not SETTLE.search(notes):
            h["unit_grants"] += 1; h["units"] += sh
            h["first"] = min(h["first"] or period, period); h["last"] = max(h["last"], period)
        elif RSA.search(notes):
            h["rsa_grants"] += 1

rows = [(tk, v) for tk, v in hits.items() if v["unit_grants"]]
rows.sort(key=lambda kv: -kv[1]["units"])
with open(os.path.join(ROOT, "rsu_scope.csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["ticker", "ceo", "unit_grants_in_table1", "units_granted", "current_shares_shown", "units_as_pct_of_shown", "first", "last", "rsa_grants"])
    for tk, v in rows:
        cur = current.get(tk) or 0
        w.writerow([tk, owners.get(next((o for o, w2 in owners.items() if w2[0] == tk), ""), ("", ""))[1],
                    v["unit_grants"], int(v["units"]), int(cur), f"{100 * v['units'] / cur:.0f}%" if cur else "", v["first"], v["last"], v["rsa_grants"]])

print(f"scanned {scanned} cached ownership documents; {len(hits)} CEOs seen in them")
print(f"companies with RSU/PSU grants reported in Table I: {len(rows)} of {len(hits)}")
big = [tk for tk, v in rows if current.get(tk) and v["units"] / current[tk] >= 0.25]
print(f"  where the units granted are >= 25% of the shares shown today: {len(big)}")
print("  top 15 by units granted:")
for tk, v in rows[:15]:
    cur = current.get(tk) or 0
    print(f"    {tk:6s} grants={v['unit_grants']:2d} units={int(v['units']):>12,} shown={int(cur):>12,} ({100 * v['units'] / cur:.0f}% of shown)" if cur else f"    {tk:6s} grants={v['unit_grants']} units={int(v['units']):,}")
print("written: rsu_scope.csv")
