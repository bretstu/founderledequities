#!/usr/bin/env python3
"""THE REGISTER, FROM THE DECISIONS (2026-09-19, phase two of the footnote reader).

    python3 ops/footnote_register.py            # write the reader's rows into universe/exclusions.csv
    python3 ops/footnote_register.py --dry-run  # show what would change

A line enters the register when a person has decided it: an `ok` verdict on
a reading whose label is DISCLAIMED. The row names the company, the class,
the direction and the VEHICLE (the line's own nature text), quotes the
footnote as its reason, links the filing as its source, and is marked
`decided: reader <date>`. Both walks then remove that one line; the page
shows the quote beside the number.

What never enters: a partial (counted whole until its fraction is known), an
unclear or economic reading, a line whose decision is `no` or `read`, and an
ANONYMOUS vehicle ("See footnote", "See note") where the person has more
than one such line in the class, since the register could not say which one
it means -- those are listed for a hand row.

Hand rows (no `decided` value) are kept exactly as they are. The reader's
rows are regenerated in full on every run, so a later `no` on a line removes
its row.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fle.exclusions import COLUMNS, DEFAULT  # noqa: E402
from fle.ledger import is_anonymous, vehicle_key  # noqa: E402

READS = os.path.join(ROOT, "universe", "footnote-reads.csv")
REVIEWED = os.path.join(ROOT, "universe", "footnote-reviewed.csv")


def _id(key: str) -> str:
    return "|".join(key.split("|")[:3])


def main(argv):
    dry = "--dry-run" in argv
    reg_p = os.path.join(ROOT, DEFAULT)
    panel = {r["ticker"]: r for r in csv.DictReader(open(os.path.join(ROOT, "panel.csv"), encoding="utf-8-sig"))}
    reads = list(csv.DictReader(open(READS, encoding="utf-8-sig"))) if os.path.exists(READS) else []
    reviewed = {}
    if os.path.exists(REVIEWED):
        for r in csv.DictReader(open(REVIEWED, encoding="utf-8-sig")):
            reviewed[r["key"]] = r                # the latest verdict per line wins (the file is appended)
    from footnote_review import decided
    dec = decided(reads, reviewed)                # by key, by id, or inherited from an identical footnote
    hand, first_seen = [], {}
    if os.path.exists(reg_p):
        for r in csv.DictReader(open(reg_p, encoding="utf-8-sig")):
            if not (r.get("decided") or "").strip():
                hand.append({c: r.get(c, "") for c in COLUMNS})
            else:
                # a reader row keeps the date it was first written, so the file only changes when a row does
                first_seen[(r["ticker"], r["security"].strip().lower(), r.get("vehicle", ""))] = r["decided"]

    # the lines a person decided are not the person's
    picked, skipped = {}, []
    by_owner_class = {}
    for r in reads:
        by_owner_class.setdefault((r["owner_cik"], r["security"].strip().lower(), r["direct"].upper()), []).append(r)
    for r in reads:
        d = dec.get(r["key"])
        if not d or d[0] != "ok" or r["label"] != "disclaimed":
            continue
        tk = r["ticker"].upper()
        if tk not in panel:
            continue
        vehicle = (r.get("nature") or "").strip()
        if len(vehicle_key(r["direct"], vehicle)[1]) < 4:
            # "I", "(2)", "Yes": a text that names nothing; it would match every such line
            skipped.append((tk, r["ceo"], vehicle, r["shares"], "a nature text too short to name a vehicle: needs a hand row keyed another way"))
            continue
        if is_anonymous(vehicle, r["direct"]):
            others = [x for x in by_owner_class[(r["owner_cik"], r["security"].strip().lower(), r["direct"].upper())]
                      if is_anonymous((x.get("nature") or ""), x["direct"]) and x["label"] != "disclaimed"]
            if others:
                skipped.append((tk, r["ceo"], vehicle, r["shares"], "an anonymous line beside others of the same class: needs a hand row"))
                continue
        k = (panel[tk]["cik"], r["security"].strip().lower(), r["direct"].upper(), vehicle_key(r["direct"], vehicle)[1])
        if k in picked:
            continue        # the same vehicle on another filing: one row
        picked[k] = {"cik": panel[tk]["cik"], "ticker": tk, "security": r["security"].strip(), "direct": r["direct"].upper(),
                     "reason": r["quote"].strip(), "source": r["url"].strip(), "shares": "", "owner_cik": "", "since": r["accession"],
                     "vehicle": vehicle,
                     "decided": first_seen.get((tk, r["security"].strip(), vehicle)) or first_seen.get((tk, r["security"].strip().lower(), vehicle)) or f"reader {dt.date.today().isoformat()}"}

    rows = hand + sorted(picked.values(), key=lambda x: (x["ticker"], x["security"], x["vehicle"]))
    print(f"  register: {len(hand)} hand row(s) kept, {len(picked)} reader row(s) from {len(reviewed)} decision(s)")
    if "--quiet" not in argv:
        for r in sorted(picked.values(), key=lambda x: x["ticker"]):
            print(f"    {r['ticker']:6} {r['security'][:22]:22} {r['direct']} {r['vehicle'][:44]:44} {r['reason'][:60]}")
    for tk, ceo, v, sh, why in sorted(set(skipped)):
        print(f"  SKIPPED {tk} {ceo}: {v!r} {sh} shares: {why}")
    if dry:
        return 0
    # WHAT CHANGED, FOR THE NEXT WALK (2026-09-20): the companies whose reader
    # rows differ from the file as it was are listed for the refresh, which
    # rewalks them that night whether or not they filed.
    before = {}
    if os.path.exists(reg_p):
        for r in csv.DictReader(open(reg_p, encoding="utf-8-sig")):
            if (r.get("decided") or "").strip():
                before[(r["ticker"], r["security"].strip().lower(), r.get("vehicle", ""))] = r["reason"]
    after = {(r["ticker"], r["security"].strip().lower(), r["vehicle"]): r["reason"] for r in picked.values()}
    changed = sorted({k[0] for k in set(before) ^ set(after)} | {k[0] for k in set(before) & set(after) if before[k] != after[k]})
    with open(reg_p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"  wrote {reg_p}: {len(rows)} row(s)")
    if changed:
        nxt = os.path.join(ROOT, "universe", "rewalk-next.txt")
        have = set(open(nxt, encoding="utf-8").read().split()) if os.path.exists(nxt) else set()
        open(nxt, "w", encoding="utf-8").write("\n".join(sorted(have | set(changed))) + "\n")
        print(f"  rewalk tonight: {', '.join(changed)} (universe/rewalk-next.txt)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
