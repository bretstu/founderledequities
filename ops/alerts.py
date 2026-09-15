#!/usr/bin/env python3
"""The nightly's half of the watches (PLAN.md section 5a).

    python3 ops/alerts.py            # post every decision filed since the last run
    python3 ops/alerts.py --dry-run  # say what would be posted, post nothing

After the events file is rebuilt, the filings that a watcher asked about
(an open-market purchase, or a sale made at the person's own discretion)
that were filed since the last run are posted to /api/watch/run with the
shared secret. The function on Cloudflare holds the watches and sends the
alerts; this script never sees an address. Plans, compensation, pre-IPO
catch-ups and cover pages are not posted: nobody asked for them.

The high-water mark (the newest filed date already posted) is kept in
weekly/alerts-last.txt so a rerun posts nothing twice; the function also
records each (watch, filing) it sent, so even a stale mark cannot double
a message.
"""
import csv
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from fle import config as _config  # noqa: E402  (loads .env)
sys.path.insert(0, HERE)
import kinds  # noqa: E402

COMPENSATION = kinds.COMP_LABELS  # the page's set (ops/kinds.py), one copy for every script
MARK = os.path.join(ROOT, "weekly", "alerts-last.txt")


def decisions(events_p, since):
    """Open-market purchases and discretionary sales filed after `since`."""
    out = []
    with open(events_p, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            filed = r.get("filed") or ""
            if filed <= since or r.get("code") not in ("P", "S"):
                continue
            if (r.get("label") or "") in COMPENSATION or (r.get("pre_ipo") or "") in ("1", "true", "True"):
                continue
            if r["code"] == "S" and (r.get("plan") or "") == "plan":
                continue
            try:
                value = float(r.get("value") or 0) or None
            except ValueError:
                value = None
            out.append({"tk": r["ticker"].upper(), "ceo": r.get("ceo") or "", "code": r["code"],
                        "value": value if not (r.get("price_flag") or "") else None,
                        "pct_after": r.get("pct_after") or "", "traded": r.get("traded") or "",
                        "filed": filed, "accession": r.get("accession") or f"{r['ticker']}:{filed}:{r['code']}",
                        "url": r.get("url") or ""})
    return out


def main(argv):
    dry = "--dry-run" in argv
    site = os.environ.get("SITE_URL", "https://founderledequities.com").rstrip("/")
    key = os.environ.get("ALERTS_KEY", "")
    since = ""
    if os.path.exists(MARK):
        since = open(MARK, encoding="utf-8").read().strip()
    if not since:
        # THE FIRST RUN STARTS A WEEK BACK, not in 2016: a watcher who signed
        # up today asked about what happens next, and the function's own
        # record of what it sent keeps even that week from repeating.
        import datetime as _dt
        since = (_dt.date.today() - _dt.timedelta(days=7)).isoformat()
    evs = decisions(os.path.join(ROOT, "events.csv"), since)
    if not evs:
        print(f"  alerts: nothing filed since {since or 'the start'}")
        return 0
    newest = max(e["filed"] for e in evs)
    print(f"  alerts: {len(evs)} decisions filed {since or 'ever'} < filed <= {newest} "
          f"({sum(1 for e in evs if e['code'] == 'P')} buys, {sum(1 for e in evs if e['code'] == 'S')} discretionary sales)")
    if dry:
        for e in evs[:12]:
            print(f"    {e['filed']} {e['tk']:6} {e['ceo']} {'bought' if e['code'] == 'P' else 'sold'} {e['value'] or ''}")
        return 0
    if not key:
        print("  alerts: ALERTS_KEY is not set (.env); nothing posted")
        return 2
    req = urllib.request.Request(f"{site}/api/watch/run", data=json.dumps({"key": key, "events": evs}).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "founderledequities-alerts/1"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        print(f"  alerts: refused: {e.code} {e.read().decode(errors='replace')[:200]}")
        return 1
    except urllib.error.URLError as e:
        print(f"  alerts: no connection: {e.reason}")
        return 1
    print(f"  alerts: {body.get('sent', 0)} email(s) to {body.get('watchers', 0)} watcher(s)")
    os.makedirs(os.path.dirname(MARK), exist_ok=True)
    open(MARK, "w", encoding="utf-8").write(newest + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
