#!/usr/bin/env python3
"""THE REVIEW LIST (2026-09-18): every line the reader labelled disclaimed or
partial, with the filer's words and a register row ready to paste into
universe/exclusions.csv once a person has read the filing and agrees.
    python3 ops/footnote_review.py                    # everything not yet reviewed
    python3 ops/footnote_review.py --reviewed KEY ok   # mark a line reviewed (ok / no), so it is not shown again
    python3 ops/footnote_review.py --all              # reviewed ones too
NOTE: the register matches a class + direct/indirect today; a row for one
vehicle among several needs the vehicle column, which lands with phase two.
Until then a pasted row excludes the whole class, so read the line's
neighbours before pasting.
"""
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
READS = os.path.join(ROOT, "universe", "footnote-reads.csv")
REVIEWED = os.path.join(ROOT, "universe", "footnote-reviewed.csv")


def golden():
    sys.path.insert(0, ROOT)
    from fle.edgar import EdgarClient
    from fle.ledger import _parse
    from fle.footnotes import lines_of, line_key, classify
    if not os.path.exists(REVIEWED) or not os.path.exists(READS):
        print("  nothing reviewed yet")
        return 0
    key_env = os.environ.get("ANTHROPIC_API_KEY") or ""
    if not key_env:
        for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
            if line.startswith("ANTHROPIC_API_KEY="):
                key_env = line.split("=", 1)[1].strip().strip('"').strip("'")
    reviewed = {r["key"]: r for r in csv.DictReader(open(REVIEWED, encoding="utf-8-sig"))}
    reads = {r["key"]: r for r in csv.DictReader(open(READS, encoding="utf-8-sig"))}
    # the expected label from the verdict: ok -> the flagged label stands; no -> economic; read -> any
    client = EdgarClient()
    P = {r["ticker"]: r for r in csv.DictReader(open(os.path.join(ROOT, "panel.csv"), encoding="utf-8-sig"))}
    checked = flipped = unverified = 0
    cache = {}
    for k, v in reviewed.items():
        r = reads.get(k)
        if not r or v["verdict"] not in ("ok", "no"):
            continue
        # ok: the label recorded when the verdict was given (a flag label when
        # the record predates that column); no: economic (unclear also accepted)
        recorded = (v.get("label") or "").strip()
        expect = (recorded or "flag") if v["verdict"] == "ok" else "economic"
        tk, acc = r["ticker"], r["accession"]
        cik = int(P[tk]["cik"]) if tk in P else None
        if cik is None:
            continue
        if (cik, acc) not in cache:
            f = {"accessionNumber": acc, "primaryDocument": "", "form": "4"}
            try:
                from fle.edgar import EdgarClient as _E  # noqa: F401
                subs = client.submissions(cik)
                f = next((x for x in subs.get("_filings", []) if x.get("accessionNumber") == acc), f)
                cache[(cik, acc)] = _parse(client, cik, f)
            except Exception:  # noqa: BLE001
                cache[(cik, acc)] = None
        root = cache[(cik, acc)]
        if root is None:
            continue
        line = next((l for l in lines_of(root, acc) if line_key(r["owner_cik"], l) == k), None)
        if line is None:
            continue
        got = classify(line, key_env)
        checked += 1
        if got["label"] == "none":
            unverified += 1
            print(f"  unverified {tk} {r['security'][:20]} {r['nature'][:30]}: the quote was not the footnote's words -- \"{got['quote'][:100]}\"")
            continue
        ok = ((expect == "flag" and got["label"] in ("disclaimed", "partial"))
              or got["label"] == expect
              or (expect == "economic" and got["label"] in ("economic", "unclear")))
        if not ok:
            flipped += 1
            print(f"  FLIPPED {tk} {r['security'][:20]} {r['nature'][:30]}: expected {expect}, read {got['label']} -- \"{got['quote'][:100]}\"")
    print(f"  golden set: {checked} reviewed line(s) re-read, {flipped} flipped, {unverified} unverified")
    return 1 if flipped else 0


def main(argv):
    if "--golden" in argv:
        # THE GOLDEN SET: every reviewed line re-read under the current prompt,
        # compared with the recorded verdict. A prompt change that flips a
        # settled reading fails here before it reads anything new.
        return golden()
    if "--reviewed" in argv:
        i = argv.index("--reviewed")
        key, verdict = argv[i + 1], (argv[i + 2] if len(argv) > i + 2 else "ok")
        label_now = ""
        if os.path.exists(READS):
            label_now = next((r["label"] for r in csv.DictReader(open(READS, encoding="utf-8-sig")) if r["key"] == key), "")
        new = not os.path.exists(REVIEWED)
        with open(REVIEWED, "a", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["key", "verdict", "note", "label"])
            w.writerow([key, verdict, " ".join(argv[i + 3:]), label_now])
        print(f"  marked {key}: {verdict}")
        return 0
    reviewed = {}
    if os.path.exists(REVIEWED):
        reviewed = {r["key"]: r for r in csv.DictReader(open(REVIEWED, encoding="utf-8-sig"))}
    if not os.path.exists(READS):
        print("  no readings yet: python3 ops/footnote_reads.py")
        return 0
    NAME_HINT = re.compile(r"foundation|charit|philanthrop|donor|biohub|non-?profit|for the benefit of|endowment", re.I)
    allrows = list(csv.DictReader(open(READS, encoding="utf-8-sig")))
    rows = [r for r in allrows if r["label"] in ("disclaimed", "partial")]
    # NAME ONLY (2026-09-18): a line the model left unclear whose vehicle's
    # NAME says foundation, charity, donor: not a reading, a reason to look
    for r in allrows:
        if r["label"] == "unclear" and NAME_HINT.search(r.get("nature") or ""):
            rows.append(dict(r, label="name only"))
    if "--all" not in argv:
        rows = [r for r in rows if r["key"] not in reviewed]
    if not rows:
        print("  nothing to review")
        return 0
    rows.sort(key=lambda r: (r["ticker"], r["label"] == "name only", -float(r["shares"] or 0)))
    ciks = {}
    pp = os.path.join(ROOT, "panel.csv")
    if os.path.exists(pp):
        ciks = {x["ticker"]: x["cik"] for x in csv.DictReader(open(pp, encoding="utf-8-sig"))}
    for r in rows:
        who = "held directly" if r["direct"] == "D" else f"by {r['nature']}"
        frac = f" · fraction {r['fraction']}" if r.get("fraction") else ""
        print(f"\n== {r['ticker']} · {r['ceo']} · {r['security']} {who} · {float(r['shares'] or 0):,.0f} shares · [{r['label']}{frac}]")
        print(f"   \"{r['quote']}\"")
        print(f"   {r['reason']}")
        print(f"   filing: {r['url']}   key: {r['key']}")
        reason = r["quote"].replace('"', "'")
        cik = ciks.get(r["ticker"], "<cik>")
        print(f"   register row (paste after reading): {cik},{r['ticker']},{r['security']},{r['direct']},\"{reason}\",{r['url']},,,")
    print(f"\n  {len(rows)} line(s). Mark one reviewed: python3 ops/footnote_review.py --reviewed <key> ok|no <note>")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
