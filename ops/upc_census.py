#!/usr/bin/env python3
"""THE FOUR FACTS THAT DECIDE A PARTNERSHIP REGISTER ROW (fle/partnerships.py,
2026-09-15), from structured fields only, never footnotes. Read-only.

    python3 ops/upc_census.py --founders        # founder-led companies with any unit row
    python3 ops/upc_census.py                   # every company on the panel
    python3 ops/upc_census.py OWL SYM RUM       # named tickers

For the chief executive's every Section 16 filing at the issuer (the same
cached documents the walk reads):
  1. UNITS: a Table II row whose security title names a partnership or LLC
     unit (the ledger's PARTNERSHIP_MARKER, widened), whose underlying
     security is a share class of the issuer, and which has no conversion
     price and no expiration date (an option has both; an RSU says so in
     its title). The newest statement of each unit title, with the filing
     that states it. Titles that say LTIP, restricted, performance,
     incentive or profits interest are compensation and are listed apart.
  2. COVER: how many classes the cover page tags (from the record's
     classes column, the cover's own XBRL contexts).
  3. PAIRED: the person's newest Table I holding of a class other than the
     first (title and amount; the paired voting stock of an Up-C).
  4. MATCH: whether any unit title's count equals the paired holding
     (within 2%): one paired share per unit is the design of the structure.
A row is printed only when fact 1 holds. keep = 2 (two or more), 3 and 4;
exclude = 1 without 4; read = the facts conflict, one filing to read. The
suggestion is a suggestion; the register row is the decision, and it
cites the filing printed here.
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

UNIT_TITLE = re.compile(PARTNERSHIP_MARKER.pattern + r"|\bLLC\s+units?\b|\bclass\s+[A-Z](-\d)?\s+(common\s+)?units?\b|\bOpCo\b|"
                        r"\bHoldings?\s+(partnership\s+)?units?\b|\bpartnership\s+(interest|units?)\b|\bcommon\s+units?\b|"
                        r"\bunits?\s+of\s+[A-Z][\w.,&' ]+(LLC|L\.P\.|LP|Holdings|Group)\b", re.I)
PAY_TITLE = re.compile(r"restricted|performance|phantom|deferred|dividend equivalent|stock unit|\bRSU|\bPSU|\bLTIP|incentive|profits? interest|appreciation|option|warrant|growth unit", re.I)


def read(p):
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def person_filings(client, issuer_cik, owner_cik):
    subs = client.submissions(int(issuer_cik))
    own = client.submissions(int(str(owner_cik).lstrip("0") or 0))
    accs = {f.get("accessionNumber") for f in own.get("_filings", [])}
    mine = [f for f in subs.get("_filings", []) if f.get("form") in SECTION16 and f.get("accessionNumber") in accs]
    return sorted(displace_amended(mine), key=lambda f: (f.get("reportDate") or f.get("filingDate") or ""), reverse=True)


def facts(client, row, cover_classes):
    """-> dict of the four facts for one company, or None when fact 1 does not hold."""
    tk, cik, oc = row["ticker"], row["cik"], row.get("owner_cik") or ""
    if not oc:
        return None
    units, pay, paired = {}, {}, {}
    docs = person_filings(client, cik, oc)
    for f in docs:
        root = _parse(client, int(cik), f)
        if root is None:
            continue
        when = f.get("reportDate") or f.get("filingDate") or ""
        acc = f.get("accessionNumber") or ""
        for tag in ("derivativeTransaction", "derivativeHolding"):
            for node in root.iter(tag):
                title = (_t(node, "securityTitle") or "").strip()
                if not title or not UNIT_TITLE.search(title):
                    continue
                under = (_t(node, "underlyingSecurityTitle") or "")
                if not is_share_class(under):
                    continue
                price = _num(node, "conversionOrExercisePrice")
                exp = (_t(node, "expirationDate") or "").strip()
                if price or exp:
                    continue                       # an option: a price or an expiry; a unit has neither
                amt = _num(node, "sharesOwnedFollowingTransaction")
                if amt is None:
                    continue
                bucket = pay if PAY_TITLE.search(title) else units
                # A TITLE'S ROWS ARE SUMMED WITHIN THE FILING THAT STATES IT
                # (2026-09-16): a founder's units sit in several vehicles, one
                # row each under one title; the first version took the first
                # row and called Medline, Rush Street and Solaris conflicts.
                # The paired side was already summed the same way. Newest
                # filing first, so the first filing to state a title is its
                # current statement and later filings do not add to it.
                t = title[:48]
                prev = bucket.get(t)
                if prev is None:
                    bucket[t] = (amt, when, acc)
                elif prev[2] == acc:
                    bucket[t] = (prev[0] + amt, when, acc)
        if not paired:
            for tag in ("nonDerivativeTransaction", "nonDerivativeHolding"):
                for node in root.iter(tag):
                    title = (_t(node, "securityTitle") or "").strip()
                    got = title_letter(title) if title and is_share_class(title) else None
                    if got and got[1] and got[1] != "A":
                        amt = _num(node, "sharesOwnedFollowingTransaction")
                        key = (title[:40], _t(node, "directOrIndirectOwnership") or "", (_t(node, "natureOfOwnership") or "")[:30])
                        if amt is not None and key not in paired:
                            paired[key] = (amt, when, acc)
    if not units:
        return None
    paired_total = sum(a for a, *_ in paired.values())
    paired_acc = next((acc for (_a, _w, acc) in paired.values()), "")
    match = [t for t, (a, w, acc) in units.items() if paired_total and abs(a - paired_total) / max(a, paired_total) < 0.02]
    same_filing = bool(match) and units[match[0]][2] == paired_acc
    two = len(cover_classes) >= 2
    if match and two and paired_total and same_filing:
        suggest = "keep"          # proved on one date, in one document
    elif match and two and paired_total:
        suggest = "read"          # the counts agree but from different filings: the words decide, a person reads
    elif not paired_total or (two and not match and paired_total < 0.5 * max(a for a, *_ in units.values())):
        suggest = "exclude"
    else:
        suggest = "read"
    return {"tk": tk, "units": units, "pay": pay, "paired": paired, "paired_total": paired_total, "cover": len(cover_classes) or 1,
            "match": match, "suggest": suggest, "filings": len(docs)}


def main(argv):
    founders_only = "--founders" in argv
    named = {a.upper() for a in argv if not a.startswith("--")}
    panel = read(os.path.join(ROOT, "panel.csv"))
    founders = {r["ticker"]: r.get("founder") for r in read(os.path.join(ROOT, "founders.csv"))}
    covers = {}
    for h in read(os.path.join(ROOT, "history.csv")):
        covers[h["ticker"]] = h.get("classes") or ""
    client = EdgarClient()
    print("companies whose chief executive's filings carry a partnership-unit row (structured fields only); the register decides, this prints the facts")
    print(f"  {'tk':6}{'founder':8}{'site':>8}{'cover':>6}{'paired (Table I)':>18}{'units (Table II)':>18}  suggest  detail")
    n = 0
    for r in panel:
        tk = r["ticker"]
        if named and tk not in named:
            continue
        if founders_only and founders.get(tk) != "yes":
            continue
        letters = {m.group(1) for m in re.finditer(r"Class([A-Z])", covers.get(tk, ""))}
        try:
            c = facts(client, r, letters)
        except Exception as exc:  # noqa: BLE001
            print(f"  {tk}: could not read: {exc}", file=sys.stderr)
            continue
        if not c:
            continue
        n += 1
        big = max(c["units"].values(), key=lambda x: x[0])
        pct = float(r.get("pct") or 0)
        print(f"  {tk:6}{str(founders.get(tk) == 'yes'):8}{pct:>7.2f}%{c['cover']:>6}{c['paired_total']:>18,.0f}{big[0]:>18,.0f}  {c['suggest']:7}  "
              f"{'match: ' + c['match'][0][:30] + '; ' if c['match'] else ''}"
              + "; ".join(f"{t[:34]} {a:,.0f} ({acc})" for t, (a, w, acc) in list(c["units"].items())[:2])
              + (f" | pay units: {', '.join(list(c['pay'])[:2])}" if c["pay"] else "")
              + (f" | paired: {list(c['paired'])[0][0]}" if c["paired"] else ""))
    print(f"  ({n} companies)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
