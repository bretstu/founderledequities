#!/usr/bin/env python3
"""The nightly's half of the watches (PLAN.md section 5a).

    python3 ops/alerts.py            # post every decision filed since the last run
    python3 ops/alerts.py --dry-run  # say what would be posted, post nothing
    python3 ops/alerts.py --test     # re-send the newest founder move to the live founder alert watchers

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


MIN_MOVE = 1.0   # per cent of the holding: the tape's "Moved the stake" chip, one definition for the site


def sentence(r, value):
    """What the mail says happened, in the tape's words (ops/kinds.py)."""
    tk, ceo, code = r["ticker"].upper(), r.get("ceo") or "", r.get("code") or ""
    amt = f" {kinds.money(value)} of" if value else ""
    plan = (r.get("plan") or "") == "plan"
    when = r.get("traded") or r.get("filed") or ""
    if code == "P":
        return f"{ceo} bought{amt} {tk} on the open market on {when}."
    if code == "S" and not plan:
        return f"{ceo} sold{amt} {tk} at their own discretion on {when}."
    if code == "S":
        return f"{ceo} sold{amt} {tk} under a pre-set plan on {when}."
    what = kinds.detail_of(r) or "a filing"
    try:
        mv = float(r.get("pct_of_holding") or 0)
    except ValueError:
        mv = 0.0
    return f"{ceo}: {what} moved the {tk} stake {mv:+.1f}% on {when}."


def founders_of(root=ROOT) -> set:
    """The founder-led tickers (founders.csv): the live alert's scope."""
    p = os.path.join(root, "founders.csv")
    if not os.path.exists(p):
        return set()
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return {(r.get("ticker") or "").upper() for r in csv.DictReader(fh) if (r.get("founder") or "").lower() == "yes"}


def decisions(events_p, since, founders=None):
    """WHAT A WATCH MAILS (2026-09-17): the stake moved. An open-market
    purchase or a discretionary sale of any size (the site's two decisions),
    or any other filing that moved the holding by MIN_MOVE per cent or more
    (a planned sale, a grant, a gift, an exercise). One definition, the same
    as the tape's "Moved the stake" chip and the site-wide founder mail;
    the About page states it. Pre-IPO filings and share-count restatements
    are not moves."""
    out = []
    founders = founders_of() if founders is None else founders
    with open(events_p, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            filed = r.get("filed") or ""
            code = r.get("code") or ""
            if filed <= since or not code:
                continue
            if (r.get("pre_ipo") or "") in ("1", "true", "True"):
                continue
            plan = (r.get("plan") or "") == "plan"
            comp = (r.get("label") or "") in COMPENSATION
            decision = code in ("P", "S") and not plan and not comp
            try:
                mv = abs(float(r.get("pct_of_holding") or 0))
            except ValueError:
                mv = 0.0
            if not decision and mv < MIN_MOVE:
                continue
            try:
                value = float(r.get("value") or 0) or None
            except ValueError:
                value = None
            value = value if not (r.get("price_flag") or "") else None
            out.append({"tk": r["ticker"].upper(), "ceo": r.get("ceo") or "", "code": code,
                        "value": value, "pct_after": r.get("pct_after") or "", "traded": r.get("traded") or "",
                        "filed": filed, "accession": r.get("accession") or f"{r['ticker']}:{filed}:{code}",
                        "url": r.get("url") or "", "kind": "decision" if decision else "move",
                        "founder": r["ticker"].upper() in founders,     # the live alert's scope (functions/api/watch/run.js)
                        "sentence": sentence(r, value)})
    return out


def post(site, key, evs):
    """POST the events to the run endpoint; -> (ok, body)."""
    req = urllib.request.Request(f"{site}/api/watch/run", data=json.dumps({"key": key, "events": evs}).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "founderledequities-alerts/1"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return True, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        print(f"  alerts: refused: {e.code} {e.read().decode(errors='replace')[:200]}")
    except urllib.error.URLError as e:
        print(f"  alerts: no connection: {e.reason}")
    return False, {}


def test_mail(site, key):
    """--test (2026-09-17): re-send the newest founder move on the tape to every
    live founder alert watcher, under a test accession so the sent-record
    does not stop it. What a subscriber gets, seen by the owner."""
    import time
    evs = [e for e in decisions(os.path.join(ROOT, "events.csv"), since="2000-01-01") if e["founder"]]
    if not evs:
        print("  alerts: no founder move on the tape to send")
        return 1
    e = max(evs, key=lambda x: x["filed"])
    e = dict(e, accession=f"test-{int(time.time())}-{e['accession']}", sentence=f"Test: {e['sentence']}")
    print(f"  alerts: test mail: {e['sentence']}")
    ok, body = post(site, key, [e])
    if ok:
        print(f"  alerts: {body.get('sent', 0)} email(s) to {body.get('watchers', 0)} watcher(s)")
    return 0 if ok else 1


def main(argv):
    dry = "--dry-run" in argv
    site = os.environ.get("SITE_URL", "https://founderledequities.com").rstrip("/")
    key = os.environ.get("ALERTS_KEY", "")
    since = ""
    if "--test" in argv:
        if not key:
            print("  alerts: ALERTS_KEY is not set (.env); nothing posted")
            return 2
        return test_mail(site, key)
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
    print(f"  alerts: {len(evs)} moves filed {since or 'ever'} < filed <= {newest} "
          f"({sum(1 for e in evs if e['kind'] == 'decision')} decisions, {sum(1 for e in evs if e['kind'] == 'move')} other moves of {MIN_MOVE:g}% or more)")
    if dry:
        for e in evs[:12]:
            print(f"    {e['filed']} {e['tk']:6} {e['ceo']} {'bought' if e['code'] == 'P' else 'sold'} {e['value'] or ''}")
        return 0
    if not key:
        print("  alerts: ALERTS_KEY is not set (.env); nothing posted")
        return 2
    ok, body = post(site, key, evs)
    if not ok:
        return 1
    print(f"  alerts: {body.get('sent', 0)} email(s) to {body.get('watchers', 0)} watcher(s)")
    os.makedirs(os.path.dirname(MARK), exist_ok=True)
    open(MARK, "w", encoding="utf-8").write(newest + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
