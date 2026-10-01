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
import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
READS = os.path.join(ROOT, "universe", "footnote-reads.csv")
REVIEWED = os.path.join(ROOT, "universe", "footnote-reviewed.csv")


_SUFFIX = re.compile(r"\b(inc|incorporated|llc|l\.l\.c|corp|corporation|co|ltd|limited|lp|l\.p|the)\b\.?")
_PHRASES = ("no pecuniary interest", "disclaims beneficial ownership", "disclaim beneficial ownership",
            "except to the extent of", "pecuniary interest")


def vehicle_key(nature: str) -> str:
    """THE VEHICLE'S NAME, AS A NAME (2026-10-01): lower case, punctuation and
    corporate suffixes dropped, one space. 'By Chan Zuckerberg Biohub' and
    'By Chan Zuckerberg Biohub, Inc.' are one vehicle; 'Holdings IV' and
    'Holdings V' are not."""
    s = (nature or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = _SUFFIX.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def phrase_of(quote: str) -> str:
    """the operative words of a disclaimer, so a ruling is copied only to a
    footnote that says the same thing"""
    q = (quote or "").lower()
    return next((p for p in _PHRASES if p in q), "")


def decided(reads_rows, reviewed):
    """WHICH LINES ARE DECIDED (2026-09-20; by vehicle 2026-10-01). Three
    tiers. By the line's key or its filing-and-row id: a person ruled on this
    line. By the footnote's text: the reader copied an identical line, and
    the same words got the same ruling. By the vehicle: the same owner, the
    same vehicle name (suffixes aside), the same fresh label from the reader
    and the same operative phrase in the quote as a line a PERSON ruled on;
    a new filing that lists a known foundation with last month's disclaimer
    reworded is decided the moment it is read, and a new vehicle, a changed
    label or a changed disclaimer still asks. The reader reads every line
    either way; only the asking is skipped.
    -> {reads key: (verdict, note, source key)}"""
    by_key = {k: v for k, v in reviewed.items()}
    by_id = {"|".join(k.split("|")[:3]): v for k, v in reviewed.items()}
    by_content, by_vehicle = {}, {}
    for r in reads_rows:
        v = by_key.get(r["key"]) or by_id.get("|".join(r["key"].split("|")[:3]))
        if not v:
            continue
        if r.get("content"):
            by_content.setdefault((r["content"], r["label"]), (v, r["key"]))
        if "inherited" in (v.get("note") or ""):
            continue                      # only a person's own ruling seeds the vehicle tier
        vk = vehicle_key(r.get("nature"))
        if vk and r.get("direct", "").upper() == "I":
            by_vehicle.setdefault((r.get("owner_cik"), vk, r["label"], phrase_of(r.get("quote"))), (v, r["key"]))
    out = {}
    for r in reads_rows:
        v = by_key.get(r["key"]) or by_id.get("|".join(r["key"].split("|")[:3]))
        if v:
            out[r["key"]] = (v["verdict"], v.get("note", ""), r["key"])
            continue
        c = by_content.get((r.get("content"), r["label"]))
        if c:
            out[r["key"]] = (c[0]["verdict"], c[0].get("note", "") + " (inherited)", c[1])
            continue
        vk = vehicle_key(r.get("nature"))
        if vk and r.get("direct", "").upper() == "I":
            c = by_vehicle.get((r.get("owner_cik"), vk, r["label"], phrase_of(r.get("quote"))))
            if c:
                out[r["key"]] = (c[0]["verdict"], (c[0].get("note", "") + " (inherited by vehicle)").strip(), c[1])
    return out


def _migrate_reviewed():
    """An older reviewed file has no label column; give it one, so a verdict's
    label is kept from now on and old rows read as 'no label recorded'."""
    if not os.path.exists(REVIEWED):
        return
    rows = list(csv.reader(open(REVIEWED, encoding="utf-8-sig")))
    if rows and "label" not in rows[0]:
        out = [["key", "verdict", "note", "label"]] + [(r + ["", "", ""])[:4] for r in rows[1:]]
        with open(REVIEWED, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(out)


def golden():
    _migrate_reviewed()
    sys.path.insert(0, ROOT)
    from fle.edgar import EdgarClient
    from fle.ledger import _parse
    from fle.footnotes import lines_of, line_key, line_id, classify
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
    # VERDICTS ATTACH TO A FILING AND A ROW (2026-09-18), not to the footnote
    # hash: a structural change that alters which footnotes attach re-keys
    # the reading but not the line you ruled on. A verdict whose exact key
    # is gone is matched by its filing-and-row id, with a note that the
    # footnote text has changed since the ruling.
    by_id = {}
    for k, r in reads.items():
        by_id["|".join(k.split("|")[:3])] = r
    # the expected label from the verdict: ok -> the flagged label stands; no -> economic; read -> any
    client = EdgarClient()
    P = {r["ticker"]: r for r in csv.DictReader(open(os.path.join(ROOT, "panel.csv"), encoding="utf-8-sig"))}
    checked = flipped = unverified = 0
    cache = {}
    for k, v in reviewed.items():
        r = reads.get(k)
        changed = False
        if not r:
            r = by_id.get("|".join(k.split("|")[:3]))
            changed = r is not None
        if not r or v["verdict"] not in ("ok", "no"):
            continue
        if changed:
            print(f"  (footnotes changed since the ruling on {r['ticker']} {r['security'][:20]} {r['nature'][:30]}; comparing anyway)")
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
        want_id = "|".join(k.split("|")[:3])
        line = next((l for l in lines_of(root, acc) if line_key(r["owner_cik"], l) == k or line_id(r["owner_cik"], l) == want_id), None)
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
    # THE NEGATIVES (2026-09-18): every line of the previous accepted reading
    # against the current one. A prompt change that turns economic lines into
    # flags shows up here as a count and a list, before it reads anything new.
    prev_p = READS.replace(".csv", ".prev.csv")
    moved = 0
    if os.path.exists(prev_p):
        prev = {"|".join(r["key"].split("|")[:3]): r for r in csv.DictReader(open(prev_p, encoding="utf-8-sig"))}
        cur = {"|".join(r["key"].split("|")[:3]): r for r in reads.values()}
        changes = {}
        for i, r in cur.items():
            p = prev.get(i)
            if p and p["label"] != r["label"]:
                changes.setdefault((p["label"], r["label"]), []).append(r)
        for (a, b), rs in sorted(changes.items(), key=lambda kv: -len(kv[1])):
            print(f"  label change {a} -> {b}: {len(rs)} line(s)  e.g. " + "; ".join(f"{x['ticker']} {x['nature'][:24]}" for x in rs[:4]))
        # a line with a decision on file is settled, whichever way it moved; only undecided lines count as new
        decided = {"|".join(k.split("|")[:3]) for k in reviewed}
        newly = [x for (a, b), rs in changes.items() if a not in ("disclaimed", "partial") and b in ("disclaimed", "partial") for x in rs
                 if "|".join(x["key"].split("|")[:3]) not in decided]
        moved = len(newly)
        print(f"  negatives: {moved} line(s) newly flagged against the previous reading" + ("" if moved else "  (clean)"))
    return 1 if (flipped or moved) else 0


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
        _migrate_reviewed()
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
    allrows = list(csv.DictReader(open(READS, encoding="utf-8-sig")))
    rows = [r for r in allrows if r["label"] in ("disclaimed", "partial")]
    dec = decided(allrows, reviewed)
    if "--all" not in argv:
        rows = [r for r in rows if r["key"] not in dec]
    if "--summary" in argv:
        # THE NIGHTLY'S LINE (2026-09-20): how many need a person, written to
        # drafts/ and mailed when there are any. MAILED ON CHANGE (2026-10-01):
        # the watcher deploys during the day, so the mail goes only when the
        # set of lines waiting differs from the last mail; a question is asked
        # once. The mail also lists what was copied without asking, by vehicle,
        # so an inheritance is seen and can be overruled with --reviewed ... no.
        out = [f"# Footnotes to review · {dt.date.today().isoformat()}", ""]
        inherited = [(k, v) for k, v in dec.items() if "inherited by vehicle" in v[1]]
        for r in sorted(rows, key=lambda r: (r["ticker"], -float(r["shares"] or 0))):
            out.append(f"- {r['ticker']} {r['ceo']} [{r['label']}] {r['security'][:24]} {r['direct']} {r['nature'][:40]!r} {float(r['shares'] or 0):,.0f}")
            out.append(f"  \"{r['quote'][:240]}\"")
            out.append(f"  ok:  python3 ops/footnote_review.py --reviewed '{r['key']}' ok")
            out.append(f"  no:  python3 ops/footnote_review.py --reviewed '{r['key']}' no")
        if inherited:
            byk = {r["key"]: r for r in allrows}
            out += ["", f"# Copied without asking, by vehicle: {len(inherited)}", ""]
            for k, v in sorted(inherited):
                r = byk.get(k, {})
                out.append(f"- {r.get('ticker', '')} {r.get('nature', '')[:50]!r} {float(r.get('shares') or 0):,.0f} -> {v[0]} (from {v[2]})")
                out.append(f"  overrule: python3 ops/footnote_review.py --reviewed '{k}' no")
        os.makedirs(os.path.join(ROOT, "drafts"), exist_ok=True)
        open(os.path.join(ROOT, "drafts", "footnotes-to-review.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
        print(f"  footnotes: {len(rows)} line(s) to review" + (" (drafts/footnotes-to-review.md)" if rows else "")
              + (f", {len(inherited)} copied by vehicle" if inherited else ""))
        mailed_p = os.path.join(ROOT, "drafts", "footnotes-mailed.json")
        pending = sorted(r["key"] for r in rows) + sorted("~" + k for k, _v in inherited)
        last = []
        try:
            last = json.load(open(mailed_p, encoding="utf-8"))
        except Exception:  # noqa: BLE001 - no record yet
            last = []
        if rows and pending == last and "--force-mail" not in argv:
            print("  (not mailed: the same lines as last time)")
            rows = []
        if rows:
            json.dump(pending, open(mailed_p, "w", encoding="utf-8"))
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from live import send_mail
                to = os.environ.get("LIVE_TO") or ""
                if not to and os.path.exists(os.path.join(ROOT, ".env")):
                    for line in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
                        if line.startswith("LIVE_TO="):
                            to = line.split("=", 1)[1].strip().strip('"').strip("'")
                if to and send_mail(to, f"Footnotes to review: {len(rows)}", "\n".join(out)):
                    print(f"  mailed to {to}")
            except Exception as exc:  # noqa: BLE001
                print(f"  (not mailed: {exc})")
        return 0
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
        basis = f" · by {r['basis']}" if r.get("basis") else ""
        print(f"\n== {r['ticker']} · {r['ceo']} · {r['security']} {who} · {float(r['shares'] or 0):,.0f} shares · [{r['label']}{frac}{basis}] · footnotes {r.get('footnote_ids') or '-'}")
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
