#!/usr/bin/env python3
"""WHICH COMPANIES ARE UP-Cs, FROM THE FILINGS, and what the site's rule
costs their founders (2026-09-15). Read-only: nothing is changed.

    python3 ops/upc_census.py            # every company on the panel
    python3 ops/upc_census.py --founders # founder-led only
    python3 ops/upc_census.py BX OWL     # named tickers

DO NOT TRUST THE PANEL'S FLAG. `partnership_units` is read from the newest
filing alone, so Schwarzman's 235M Blackstone units show as 1.4M. This
census reads EVERY Section 16 filing the chief executive has made at the
issuer (the same cached documents the walk reads) and looks at Table II
for the four signatures of an operating-partnership structure:

  1. a derivative whose title is a partnership or LLC unit (the ledger's
     own PARTNERSHIP_MARKER, widened: "LLC Units", "Class B Units",
     "OpCo", "Holdings Units", "exchangeable" in the title)
  2. a derivative whose underlying is the issuer's Class A and whose
     conversion price is nil or absent with no expiration (an exchange
     right, not an option)
  3. a Table I share class the cover page never lists (the paired voting
     stock of an up-C: MoonLake's Class C, Clear's Class B)
  4. footnote text: "exchangeable", "Up-C", "operating partnership",
     "paired", "one-for-one"

Then, per company, the NEWEST statement of each unit title (the last
filing that mentions it, the ledger's own rule) is summed into the
person's units, and the implication is stated: the units the site does
not count, against the shares it does, and the stake as the site shows it
against the stake with units counted 1:1 over the cover's count plus the
person's units (a floor: the true as-converted denominator also includes
other holders' units, which the 10-K text carries and this census does
not read).
"""
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from fle.edgar import EdgarClient                      # noqa: E402
from fle.ledger import (_parse, _t, _num, PARTNERSHIP_MARKER, is_share_class,   # noqa: E402
                        title_letter, SECTION16, displace_amended)

UNIT_TITLE = re.compile(PARTNERSHIP_MARKER.pattern + r"|\bLLC\s+units?\b|\bclass\s+[A-Z]\s+(common\s+)?units?\b|\bOpCo\b|\bHoldings?\s+units?\b|"
                        r"exchangeable|\bpartnership\s+(interest|units?)\b|\bunits?\s+of\s+[A-Z][\w.,& ]+(LLC|L\.P\.|LP|Holdings)\b", re.I)
PAY_TITLE = re.compile(r"restricted|performance|phantom|deferred|dividend equivalent|stock unit|\bRSU|\bPSU|appreciation|option|warrant|growth unit", re.I)
FOOT = re.compile(r"exchangeable|up-c\b|operating partnership|paired (share|stock)|one[- ]for[- ]one|redeem(able|ed) for (cash or )?(shares|Class A)", re.I)


def read(p):
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def person_filings(client, issuer_cik, owner_cik):
    subs = client.submissions(int(issuer_cik))
    own = client.submissions(int(str(owner_cik).lstrip("0") or 0))
    accs = {f.get("accessionNumber") for f in own.get("_filings", [])}
    mine = [f for f in subs.get("_filings", []) if f.get("form") in SECTION16 and f.get("accessionNumber") in accs]
    return sorted(displace_amended(mine), key=lambda f: (f.get("reportDate") or f.get("filingDate") or ""), reverse=True)


def census(client, row, cover_classes):
    """-> dict for one company, or None if nothing in the filings suggests the structure."""
    tk, cik, oc = row["ticker"], row["cik"], row.get("owner_cik") or ""
    if not oc:
        return None
    units = {}          # title -> (newest amount, date, direct/indirect, underlying, footnote hint)
    exch = 0
    foreign_class = set()
    foot_hits = 0
    n = 0
    for f in person_filings(client, cik, oc):
        root = _parse(client, int(cik), f)
        if root is None:
            continue
        n += 1
        when = f.get("reportDate") or f.get("filingDate") or ""
        foots = " ".join((x.text or "") for x in root.iter("footnote"))
        if FOOT.search(foots):
            foot_hits += 1
        for tag in ("derivativeTransaction", "derivativeHolding"):
            for node in root.iter(tag):
                title = (_t(node, "securityTitle") or "").strip()
                if not title or PAY_TITLE.search(title):
                    continue
                under = (_t(node, "underlyingSecurityTitle") or "")
                amt = _num(node, "sharesOwnedFollowingTransaction")
                price = _num(node, "conversionOrExercisePrice")
                exp = (_t(node, "expirationDate") or "").strip()
                is_unit = bool(UNIT_TITLE.search(title))
                is_exchange = (not is_unit) and is_share_class(under) and not price and not exp and not is_share_class(title)
                if is_unit or is_exchange:
                    if is_exchange:
                        exch += 1
                    key = title
                    if key not in units and amt is not None:   # newest first: the first mention is the current one
                        units[key] = (amt, when, _t(node, "directOrIndirectOwnership") or "", under[:30])
        for tag in ("nonDerivativeTransaction", "nonDerivativeHolding"):
            for node in root.iter(tag):
                title = (_t(node, "securityTitle") or "").strip()
                if title and is_share_class(title):
                    got = title_letter(title)
                    if got and got[1] and got[1] not in cover_classes:
                        foreign_class.add(title[:40])
    total_units = sum(a for a, *_ in units.values())
    if not units and not foreign_class and foot_hits < 2:
        return None
    return {"tk": tk, "units": units, "total_units": total_units, "exchange_rows": exch,
            "foreign_class": sorted(foreign_class), "foot_hits": foot_hits, "filings": n}


def facts_row(client, row, cover_classes):
    """THE THREE FACTS THAT DECIDE KEEP OR EXCLUDE (fle/partnerships.py):
    (1) the cover lists more than one class, (2) the person's Table I holds
    a class other than the first, (3) his Table II unit count equals that
    holding. All three -> keep (the ordinary rule is the proxy's number);
    otherwise -> exclude. Printed, never decided here."""
    c = census(client, row, cover_classes)
    if not c:
        return None
    tk, cik, oc = row["ticker"], row["cik"], row.get("owner_cik") or ""
    paired = {}
    for f in person_filings(client, cik, oc):
        root = _parse(client, int(cik), f)
        if root is None:
            continue
        for tag in ("nonDerivativeTransaction", "nonDerivativeHolding"):
            for node in root.iter(tag):
                title = (_t(node, "securityTitle") or "").strip()
                got = title_letter(title) if title and is_share_class(title) else None
                if got and got[1] and got[1] != "A":
                    amt = _num(node, "sharesOwnedFollowingTransaction")
                    key = (title[:40], _t(node, "directOrIndirectOwnership") or "", (_t(node, "natureOfOwnership") or "")[:30])
                    if amt is not None and key not in paired:
                        paired[key] = amt
        if paired:
            break     # newest first: the first filing that states the paired class is its current statement
    paired_total = sum(paired.values())
    two_classes = len(cover_classes) >= 2
    match = c["total_units"] > 0 and paired_total > 0 and abs(paired_total - c["total_units"]) / max(paired_total, c["total_units"]) < 0.02
    suggest = "keep" if (two_classes and paired_total and (match or not c["total_units"])) else "exclude"
    c.update(paired_total=paired_total, paired_titles=sorted({k[0] for k in paired}), two_classes=two_classes, match=match, suggest=suggest)
    return c


def main(argv):
    if "--facts" in argv:
        return main_facts([a for a in argv if a != "--facts"])
    founders_only = "--founders" in argv
    named = {a.upper() for a in argv if not a.startswith("--")}
    panel = read(os.path.join(ROOT, "panel.csv"))
    founders = {r["ticker"]: r.get("founder") for r in read(os.path.join(ROOT, "founders.csv"))}
    covers = {}
    for h in read(os.path.join(ROOT, "history.csv")):
        covers[h["ticker"]] = h.get("classes") or ""
    client = EdgarClient()
    out = []
    for r in panel:
        tk = r["ticker"]
        if named and tk not in named:
            continue
        if founders_only and founders.get(tk) != "yes":
            continue
        letters = {m.group(1) for m in re.finditer(r"Class([A-Z])", covers.get(tk, ""))}
        try:
            c = census(client, r, letters)
        except Exception as exc:  # noqa: BLE001
            print(f"  {tk}: could not read: {exc}", file=sys.stderr)
            continue
        if not c:
            continue
        shares = float(r.get("shares") or 0)
        out_ = float(r.get("outstanding") or 0)
        pct = float(r.get("pct") or 0)
        floor = (shares + c["total_units"]) / (out_ + c["total_units"]) * 100 if out_ else 0
        c.update(founder=founders.get(tk), pct=pct, shares=shares, conf=r.get("confidence"), floor=floor, panel_units=r.get("partnership_units") or "")
        out.append(c)
    out.sort(key=lambda c: (c["founder"] != "yes", -(c["total_units"])))
    print(f"{len(out)} companies whose chief executive's filings carry an operating-partnership signature "
          f"({sum(1 for c in out if c['founder'] == 'yes')} founder-led). Columns: the stake the site shows; the units the site does not count; "
          f"the stake with units counted 1:1 over the cover plus the person's units (a floor).")
    print(f"  {'tk':6}{'founder':8}{'site':>8}{'units':>14}{'floor':>8}  {'conf':7} {'signals':38} unit titles (newest statement)")
    for c in out:
        sig = f"units={len(c['units'])} exch={c['exchange_rows']} foreign={len(c['foreign_class'])} fn={c['foot_hits']}/{c['filings']}"
        titles = "; ".join(f"{t[:34]} {a:,.0f} ({d})" for t, (a, w, d, u) in list(c["units"].items())[:3])
        print(f"  {c['tk']:6}{str(c['founder'] == 'yes'):8}{c['pct']:>7.2f}%{c['total_units']:>14,.0f}{c['floor']:>7.1f}%  {str(c['conf']):7} {sig:38} {titles}"
              + (f" | Table I class not on cover: {c['foreign_class'][0]}" if c["foreign_class"] else ""))
    return 0


def main_facts(argv):
    founders_only = "--founders" in argv
    named = {a.upper() for a in argv if not a.startswith("--")}
    panel = read(os.path.join(ROOT, "panel.csv"))
    founders = {r["ticker"]: r.get("founder") for r in read(os.path.join(ROOT, "founders.csv"))}
    covers = {}
    for h in read(os.path.join(ROOT, "history.csv")):
        covers[h["ticker"]] = h.get("classes") or ""
    client = EdgarClient()
    print("the three facts per candidate (fle/partnerships.py): cover classes; the person's paired-class holding in Table I; his Table II units")
    print(f"  {'tk':6}{'founder':8}{'cover':>6}{'paired (Table I)':>18}{'units (Table II)':>18}{'match':>6}  suggest  paired class")
    for r in panel:
        tk = r["ticker"]
        if named and tk not in named:
            continue
        if founders_only and founders.get(tk) != "yes":
            continue
        letters = {m.group(1) for m in re.finditer(r"Class([A-Z])", covers.get(tk, ""))}
        try:
            c = facts_row(client, r, letters)
        except Exception as exc:  # noqa: BLE001
            print(f"  {tk}: could not read: {exc}", file=sys.stderr)
            continue
        if not c:
            continue
        print(f"  {tk:6}{str(founders.get(tk) == 'yes'):8}{len(letters) or 1:>6}{c['paired_total']:>18,.0f}{c['total_units']:>18,.0f}{str(c['match']):>6}  {c['suggest']:7}  {', '.join(c['paired_titles'])[:40]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
