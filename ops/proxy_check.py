#!/usr/bin/env python3
"""RUN THE PROXY CHECK (2026-09-18): for each company, the newest proxy's
row for the chief executive against the history on the record date. Writes
universe/proxy-checks.csv, which the grade reads into the panel's proxy
columns on the next walk. Nothing here changes a number.
    python3 ops/proxy_check.py                 # every company whose proxy is newer than its last check
    python3 ops/proxy_check.py --all           # every company
    python3 ops/proxy_check.py META,UAA        # just these, and print the reading
    python3 ops/proxy_check.py --limit 300     # at most N fetches (the nightly's budget)
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from fle.edgar import EdgarClient  # noqa: E402
from fle.proxy import fetch_proxy, read_proxy, ours_on, verdict, load_checks, write_checks  # noqa: E402

CHECKS = os.path.join(ROOT, "universe", "proxy-checks.csv")


def lines_of(client, cik, owner_cik, tk):
    """The lines we count today, for naming the one the proxy leaves out."""
    try:
        from fle.outstanding import shares_outstanding
        from fle.ledger import build_ledger
        out = shares_outstanding(client, cik)
        led = build_ledger(client, cik, owner_cik=owner_cik, share_classes=out.classes if out.ok else 0, class_members=out.per_class)
        out_lines = []
        for _k, g in led.groups.items():
            for v, b in g.vehicles().items():
                label = f"{g.security} {'held directly' if (v and v[0] == 'D') else 'by ' + str(v[1]) if v and len(v) > 1 else str(v)}"
                out_lines.append((label, float(b)))
        return out_lines
    except Exception:  # noqa: BLE001
        return []


def main(argv):
    only = None
    limit = None
    everyone = "--all" in argv
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    for a in argv:
        if not a.startswith("--") and not a.isdigit() and a != argv[0]:
            only = {t.strip().upper() for t in a.split(",")}
    client = EdgarClient()
    panel = list(csv.DictReader(open(os.path.join(ROOT, "panel.csv"), encoding="utf-8-sig")))
    hist = {}
    for h in csv.DictReader(open(os.path.join(ROOT, "history.csv"), encoding="utf-8-sig")):
        hist.setdefault(h["ticker"], []).append(h)
    checks = load_checks(CHECKS)
    done = 0
    for r in panel:
        tk = r["ticker"]
        if only and tk not in only:
            continue
        if limit and done >= limit:
            break
        prev = checks.get(tk)
        html_doc, f = fetch_proxy(client, int(r["cik"]))
        if not f:
            if only:
                print(f"  {tk}: no proxy on file")
            continue
        pdate = f.get("filingDate") or ""
        if prev and not everyone and not only and prev.get("proxy_date") == pdate:
            continue   # already checked this proxy
        done += 1
        read = read_proxy(html_doc, r["ceo"], pdate) if html_doc else None
        if read is None:
            checks[tk] = {"ticker": tk, "cik": r["cik"], "ceo": r["ceo"], "proxy_date": pdate, "level": "none", "sentence": "the proxy could not be fetched",
                          "url": f"https://www.sec.gov/Archives/edgar/data/{int(r['cik'])}/{(f.get('accessionNumber') or '').replace('-', '')}/"}
            continue
        ours, odate = ours_on(hist.get(tk, []), read.record_date or pdate)
        lines = []
        if read.shares is not None and ours is not None and abs(read.shares - ours) >= 0.0001 * max(ours, 1.0):
            lines = lines_of(client, int(r["cik"]), r["owner_cik"], tk)
        level, sentence = verdict(read, ours, lines)
        checks[tk] = {"ticker": tk, "cik": r["cik"], "ceo": r["ceo"], "proxy_date": pdate, "record_date": read.record_date,
                      "proxy_shares": "" if read.shares is None else f"{read.shares:.0f}", "proxy_options": "" if read.options is None else f"{read.options:.0f}",
                      "ours": "" if ours is None else f"{ours:.0f}", "ours_date": odate, "level": level, "sentence": sentence, "row": read.row[:300],
                      "url": f"https://www.sec.gov/Archives/edgar/data/{int(r['cik'])}/{(f.get('accessionNumber') or '').replace('-', '')}/{(f.get('primaryDocument') or '').split('/')[-1]}"}
        if only:
            print(f"  {tk} {r['ceo']}: [{level}] {sentence}")
            print(f"      proxy {pdate}, record date {read.record_date}, row: {read.row[:160]}")
            if read.options:
                print(f"      options within 60 days named for the person: {read.options:,.0f}")
    write_checks(CHECKS, checks)
    levels = {}
    for c in checks.values():
        levels[c.get("level", "none")] = levels.get(c.get("level", "none"), 0) + 1
    print(f"  proxy checks: {done} read this run; {len(checks)} on file: " + ", ".join(f"{k} {v}" for k, v in sorted(levels.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
