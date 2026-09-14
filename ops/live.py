#!/usr/bin/env python3
"""THE WATCHER (distribution): a chief executive's Form 4, the minute it lands.

    python3 ops/live.py           # one pass: read EDGAR's latest Form 4s, report the new ones
    python3 ops/live.py --loop    # every ten minutes until stopped

Every pass reads EDGAR's feed of the most recent Form 4s (one request),
keeps the filings whose issuer is a founder-led company in the universe
and whose reporting owner is that founder (both ids are in the panel),
and for each one not seen before reads the filing through the pipeline's
own parser, so the kind is the site's kind: an open-market purchase, a
discretionary sale, a sale under a pre-set plan, or compensation. Each
becomes a line in drafts/live-<day>.md with the time it landed; a
decision (a purchase or a discretionary sale) is also mailed to LIVE_TO
from .env, the same minute.

ONE CALCULATOR, RUN SOONER. The watcher does not compute ownership; the
walk runs one way, in the nightly and in ops/now.sh, with its checkpoint,
its exclusions and its verification. So when a founder's DECISION lands
(a purchase or a discretionary sale) the watcher runs ops/now.sh itself,
the whole pipeline, waits the ten minutes, reads the event the run
published, and mails the finished sentence with the stake after the
trade: the number the page now shows, because the page was just built
from it. A plan or a compensation filing is written down and mailed
without a run. One run at a time; decisions that land during a run are
carried into the next.

WHAT IT KEEPS: nothing worth keeping. The day's lines, deleted after
seven days; the ids of filings already seen, trimmed to a month. Neither
is in git. The nightly is the record and never depends on this.

EDGAR's feed shows the latest 100 Form 4s; in the evening rush that can
be less than five minutes of filings, so the timer runs every five and a
pass in which every entry is new is logged as an overflow (the nightly
catches whatever fell between). EDGAR takes filings 6 a.m. to 10 p.m.
Eastern on business days. The pipeline suggests; a person posts.
"""
import csv
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from fle import config as _config  # noqa: E402  (loads .env)
from fle.config import SETTINGS  # noqa: E402

FEED = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&owner=include&count=100&output=atom"
SITE = "https://founderledequities.com"
SEEN = os.path.join(ROOT, "weekly", "live-seen.txt")
OUT = os.path.join(ROOT, "drafts", "x-live.md")
COMPENSATION = {"exercise and sell", "exercise, part sold", "vested and sold", "convert and sell",
                "sale, position unchanged", "purchase, position unchanged"}


def money(v):
    if not v:
        return ""
    a = abs(v)
    if a >= 9.995e8:
        return f"${v/1e9:.1f}B".replace(".0B", "B")
    if a >= 9.995e5:
        return f"${v/1e6:.1f}M".replace(".0M", "M")
    if a >= 1e3:
        return f"${v/1e3:.0f}K"
    return f"${v:,.0f}"


def universe():
    """issuer cik -> the CEO's reporting cik, name, company, stake now, and
    whether the proxy names them a founder (founders.csv, the same file the
    site uses). EVERY CEO's filing runs the data, so a reader watching a
    hired chief executive is served the same minute; only a FOUNDER's
    decision reaches the owner's inbox and the X drafts."""
    founders = set()
    with open(os.path.join(ROOT, "founders.csv"), encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if (r.get("founder") or "").lower() == "yes":
                founders.add((r.get("ticker") or "").upper())
    out = {}
    with open(os.path.join(ROOT, "panel.csv"), encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                cik = int(r.get("cik") or 0)
            except ValueError:
                continue
            oc = (r.get("owner_cik") or "").strip().lstrip("0")
            tk = (r.get("ticker") or "").upper()
            if cik and oc:
                out[cik] = {"tk": tk, "owner": oc, "ceo": r.get("ceo") or "", "co": r.get("company") or "",
                            "pct": r.get("pct") or "", "asof": r.get("shares_as_of") or "", "founder": tk in founders}
    return out


def feed(client):
    """The latest Form 4s: accession -> {issuer cik, reporter ciks}. EDGAR
    lists each filing once per party, so the same accession appears for
    the issuer and for each reporting owner."""
    body = client.get(FEED, use_cache=False)
    root = ET.fromstring(body)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    acc_of = re.compile(r"/data/(\d+)/\d+/(\d{10}-\d{2}-\d{6})")
    filings = {}
    for e in root.findall("a:entry", ns):
        title = e.findtext("a:title", default="", namespaces=ns)
        link = (e.find("a:link", ns).get("href") if e.find("a:link", ns) is not None else "") or ""
        m = acc_of.search(link)
        if not m:
            continue
        cik, acc = int(m.group(1)), m.group(2)
        d = filings.setdefault(acc, {"issuer": None, "reporters": set(), "title": title})
        if "(Issuer)" in title:
            d["issuer"] = cik
        elif "(Reporting)" in title:
            d["reporters"].add(str(cik))
    return filings


def describe(client, uni, cik, acc):
    """The filing as the site's parser reads it: (kind, amount, label,
    traded date). No walk, no stake after (see the module note)."""
    from fle.events import build_events
    # the company's submissions feed must be fresh: drop the cached copy
    try:
        os.remove(client._cache_path(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    except OSError:
        pass
    u = uni[cik]
    since = (dt.date.today() - dt.timedelta(days=10)).isoformat()
    evs = build_events(client, cik, u["owner"], u["tk"], u["ceo"], since=since, max_filings=6, history=None)
    out = []
    for e in evs:
        if e.accession != acc or e.code not in ("P", "S"):
            continue
        if e.label in COMPENSATION or e.pre_registration:
            kind = "compensation"
        elif e.code == "P":
            kind = "bought"
        elif getattr(e, "plan", "") == "plan":
            kind = "planned"
        else:
            kind = "discretionary"
        out.append((kind, e.value, e.label, e.traded))
    return out


def send_mail(to, subject, text):
    key = os.environ.get("RESEND_API_KEY")
    if not key or not to:
        return False
    req = urllib.request.Request("https://api.resend.com/emails",
                                 data=json.dumps({"from": "Founder Led Equities <tape@founderledequities.com>", "to": [to],
                                                  "subject": subject, "text": text}).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status < 300
    except Exception:  # noqa: BLE001
        return False


def published_event(acc):
    """The event as the run just published it, from events.csv."""
    try:
        with open(os.path.join(ROOT, "events.csv"), encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("accession") == acc and r.get("code") in ("P", "S"):
                    return r
    except OSError:
        return None
    return None


def sentence(u, r):
    """The finished line, in the Monday thread's words, from the published event."""
    code = r.get("code")
    v = None
    try:
        v = float(r.get("value") or 0) if not (r.get("price_flag") or "") else None
    except ValueError:
        v = None
    amt = f" {money(v)}" if v else ""
    how = ("on the open market" if code == "P" else
           "under a pre-set plan" if (r.get("plan") or "") == "plan" else "at their own discretion")
    verb = "bought" if code == "P" else "sold"
    mv = ""
    try:
        ch = float(r.get("pct_of_holding") or "")
        if abs(ch) >= 0.05:
            mag = f"{abs(ch):.0f}%" if abs(ch) >= 10 else f"{abs(ch):.1f}%" if abs(ch) >= 1 else f"{abs(ch):.2f}%"
            mv = f", {'added ' + mag + ' to' if ch > 0 else 'sold ' + mag + ' of'} their stake"
    except ValueError:
        pass
    after = ""
    try:
        a = float(r.get("pct_after") or "")
        after = f" Now owns {a:.3f}%." if a < 1 else f" Now owns {a:.2f}%."
    except ValueError:
        pass
    return f"{u['ceo']} {verb}{amt} of {u['tk']} {how}{mv}.{after}\n{SITE}/company/{u['tk']}/"


def publish_and_mail(pending, uni):
    """ops/now.sh once for everything pending, then one mail per decision
    with the published number. Returns the lines to log."""
    import subprocess
    lock = os.path.join(ROOT, "weekly", "live-run.lock")
    if os.path.exists(lock) and time.time() - os.path.getmtime(lock) < 1800:
        return [f"  a run is in progress; {len(pending)} decision(s) wait for the next pass"], pending
    open(lock, "w").write(str(os.getpid()))
    tickers = ",".join(sorted({uni[cik]["tk"] for _, cik in pending}))
    try:
        r = subprocess.run(["bash", os.path.join(HERE, "now.sh"), tickers], cwd=ROOT, capture_output=True, text=True, timeout=1800)
        ok = r.returncode == 0
    except Exception as e:  # noqa: BLE001
        ok = False
        r = None
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass
    lines = []
    still = []
    if ok:
        # the nightly checks its own answer against these (fle.cli refresh logs "idempotence")
        with open(os.path.join(ROOT, "weekly", "live-published.txt"), "a", encoding="utf-8") as fh:
            fh.write("\n".join(sorted({uni[cik]["tk"] for _, cik in pending})) + "\n")
    for acc, cik in pending:
        u = uni[cik]
        ev = published_event(acc) if ok else None
        if ev is None:
            still.append((acc, cik))
            lines.append(f"  {u['tk']}: the run did not publish this filing yet; it waits for the next pass")
            continue
        text = sentence(u, ev)
        sent = u.get("founder") and send_mail(os.environ.get("LIVE_TO", ""), f"{u['ceo']} {'bought' if ev.get('code') == 'P' else 'sold'} {u['tk']}: the page is live", text)
        lines.append(f"- {dt.datetime.now().strftime('%H:%M')} published · {text.replace(chr(10), ' · ')}{'  ← mailed' if sent else '  (hired CEO: data only)' if not u.get('founder') else ''}")
    return lines, still


def one_pass(client, uni, seen):
    filings = feed(client)
    if seen and filings and all(acc not in seen for acc in filings) and len(filings) >= 40:
        print(f"  {dt.datetime.now().strftime('%H:%M')} the feed overflowed since the last pass "
              f"({len(filings)} filings, all new): some may have fallen between; the nightly catches them")
    new = []
    for acc, d in filings.items():
        if acc in seen or d["issuer"] not in uni:
            continue
        u = uni[d["issuer"]]
        if u["owner"] not in d["reporters"]:
            seen.add(acc)          # a director's or an officer's filing: not the CEO's
            continue
        new.append((acc, d["issuer"]))
    lines = []
    decisions = []
    now = dt.datetime.now().strftime("%H:%M")
    for acc, cik in new:
        u = uni[cik]
        try:
            parts = describe(client, uni, cik, acc)
        except Exception as e:  # noqa: BLE001
            parts = []
            lines.append(f"- {now} {u['tk']} · {u['ceo']} filed a Form 4 (could not read it: {str(e)[:60]}) · https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/")
        for kind, value, label, traded in parts:
            verb = {"bought": "bought", "discretionary": "sold at their own discretion",
                    "planned": "sold under a pre-set plan", "compensation": "compensation:"}[kind]
            amt = f" {money(value)}" if value else ""
            stake = (f" Stake as of the {u['asof']} filing: {float(u['pct']):.2f}%; the new figure lands with ops/now.sh."
                     if u["pct"] else "")
            line = (f"- {now} {u['tk']} · {u['ceo']} {verb}{amt}{' (' + label + ')' if kind == 'compensation' else ''}, traded {traded}.{stake}"
                    f"\n  {SITE}/company/{u['tk']}/ · filing https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/")
            lines.append(line)
            if kind in ("bought", "discretionary"):
                decisions.append((acc, cik))
            elif u.get("founder"):
                # a founder's plan or compensation: written down and mailed as it is; no run
                send_mail(os.environ.get("LIVE_TO", ""), f"{u['ceo']}: {kind} filing at {u['tk']}", line)
        seen.add(acc)
    return lines, decisions


def main(argv):
    from fle.edgar import EdgarClient
    client = EdgarClient()
    uni = universe()
    os.makedirs(os.path.dirname(SEEN), exist_ok=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    seen = set(open(SEEN, encoding="utf-8").read().split()) if os.path.exists(SEEN) else set()
    loop = "--loop" in argv
    while True:
        stamp = dt.date.today().isoformat()
        try:
            lines, decisions = one_pass(client, uni, seen)
        except Exception as e:  # noqa: BLE001 - EDGAR down, a torn feed: the next pass tries again
            print(f"  {dt.datetime.now().strftime('%H:%M')} pass failed ({str(e)[:80]}); the next one tries again")
            lines, decisions = [], []
        # decisions from this pass and any left waiting by an earlier one
        pend_p = os.path.join(ROOT, "weekly", "live-pending.txt")
        pending = list(decisions)
        if os.path.exists(pend_p):
            for ln in open(pend_p, encoding="utf-8").read().split():
                acc, cik = ln.split(":")
                if (acc, int(cik)) not in pending:
                    pending.append((acc, int(cik)))
        if pending and "--no-publish" not in argv:
            more, still = publish_and_mail(pending, uni)
            lines += more
            with open(pend_p, "w", encoding="utf-8") as fh:
                fh.write("\n".join(f"{a}:{c}" for a, c in still) + ("\n" if still else ""))
        out = os.path.join(os.path.dirname(OUT), f"live-{stamp}.md")
        if lines:
            new_file = not os.path.exists(out)
            with open(out, "a", encoding="utf-8") as fh:
                if new_file:
                    fh.write(f"# {stamp}: a founder's Form 4 the minute it landed · the pipeline suggests, you post\n\n")
                fh.write("\n".join(lines) + "\n")
            print("\n".join(lines))
        else:
            print(f"  {dt.datetime.now().strftime('%H:%M')} nothing new among the latest Form 4s")
        # what it keeps: a week of day files, a month of seen ids
        for f in os.listdir(os.path.dirname(OUT)):
            m = re.fullmatch(r"live-(\d{4}-\d{2}-\d{2})\.md", f)
            if m and m.group(1) < (dt.date.today() - dt.timedelta(days=7)).isoformat():
                os.remove(os.path.join(os.path.dirname(OUT), f))
        # an accession's middle is the filing year; older than last year's is not on any live feed
        with open(SEEN, "w", encoding="utf-8") as fh:
            fh.write("\n".join(sorted(seen)[-4000:]) + "\n")
        if not loop:
            return 0
        time.sleep(300)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
