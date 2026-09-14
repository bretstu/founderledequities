#!/usr/bin/env python3
"""THE WATCHER (distribution): a chief executive's Form 4, the minute it lands.

    python3 ops/live.py           # one pass: read EDGAR's latest Form 4s, report the new ones
    python3 ops/live.py --loop    # every ten minutes until stopped

Every pass reads EDGAR's feed of the most recent Form 4s (one request),
keeps the filings whose issuer is in the universe and whose reporting
owner is that company's chief executive (both ids are in the panel), and
for each one not seen before fetches the filing through the pipeline's
own parser, so the kind is the site's kind: an open-market purchase, a
discretionary sale, a sale under a pre-set plan, or compensation. Each
becomes a line in drafts/x-live.md with the time it landed; a decision
(a purchase or a discretionary sale) is also mailed to LIVE_TO from .env,
the same minute. The stake after the trade needs the walk, so the line
says the amount and the stake as of the previous filing; ops/now.sh (or
the nightly) brings the page up to date. The company URL is right at once.

EDGAR takes filings 6 a.m. to 10 p.m. Eastern on business days; most Form
4s land after the close. The pipeline suggests; a person posts.
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
    """issuer cik -> the founder-CEO's reporting cik, name, company, stake
    now. FOUNDERS ONLY: the proxy names them a founder (founders.csv), the
    same file the site uses; a hired chief executive's filing is not the
    watcher's business."""
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
            if cik and oc and tk in founders:
                out[cik] = {"tk": tk, "owner": oc, "ceo": r.get("ceo") or "", "co": r.get("company") or "",
                            "pct": r.get("pct") or "", "asof": r.get("shares_as_of") or ""}
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
    """The filing as the site sees it: (kind, amount, label, traded date,
    stake after, change in the holding). THE SAME CALCULATOR AS THE
    NIGHTLY: the company is walked with the pipeline's own `history`
    command into a scratch file, and the event is built against that walk,
    so the stake after the trade reported here is the number the nightly
    will publish, not a second estimate. The scratch file is discarded;
    the pipeline's own files are never touched."""
    import subprocess
    import tempfile
    from fle.events import build_events, load_history
    # the company's submissions feed must be fresh: drop the cached copy
    try:
        os.remove(client._cache_path(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    except OSError:
        pass
    u = uni[cik]
    history = None
    with tempfile.TemporaryDirectory() as td:
        hpath = os.path.join(td, "history.csv")
        r = subprocess.run([sys.executable, "-m", "fle.cli", "history", "--universe", os.path.join(ROOT, "panel.csv"),
                            "--tickers", u["tk"], "--out", hpath, "--workers", "1"],
                           cwd=ROOT, capture_output=True, text=True, timeout=600)
        if r.returncode == 0 and os.path.exists(hpath):
            history = load_history(hpath)
    since = (dt.date.today() - dt.timedelta(days=10)).isoformat()
    evs = build_events(client, cik, u["owner"], u["tk"], u["ceo"], since=since, max_filings=6, history=history)
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
        out.append((kind, e.value, e.label, e.traded, getattr(e, "pct_after", None), getattr(e, "pct_of_holding", None)))
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


def one_pass(client, uni, seen):
    filings = feed(client)
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
    now = dt.datetime.now().strftime("%H:%M")
    for acc, cik in new:
        u = uni[cik]
        try:
            parts = describe(client, uni, cik, acc)
        except Exception as e:  # noqa: BLE001
            parts = []
            lines.append(f"- {now} {u['tk']} · {u['ceo']} filed a Form 4 (could not read it: {str(e)[:60]}) · https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/")
        for kind, value, label, traded, after, change in parts:
            verb = {"bought": "bought", "discretionary": "sold at their own discretion",
                    "planned": "sold under a pre-set plan", "compensation": "compensation:"}[kind]
            amt = f" {money(value)}" if value else ""
            if after is not None:
                mv = ""
                if change is not None and abs(change) >= 0.05:
                    mag = f"{abs(change):.0f}%" if abs(change) >= 10 else f"{abs(change):.1f}%" if abs(change) >= 1 else f"{abs(change):.2f}%"
                    mv = f", {'added ' + mag + ' to' if change > 0 else 'sold ' + mag + ' of'} their stake"
                stake = f"{mv}. Now owns {after:.3f}%." if after < 1 else f"{mv}. Now owns {after:.2f}%."
            else:
                stake = f". Stake as of the {u['asof']} filing: {float(u['pct']):.2f}%." if u["pct"] else "."
            line = (f"- {now} {u['tk']} · {u['ceo']} {verb}{amt}{' (' + label + ')' if kind == 'compensation' else ''}, traded {traded}{stake}"
                    f"\n  {SITE}/company/{u['tk']}/ · filing https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/")
            lines.append(line)
            if kind in ("bought", "discretionary"):
                sent = send_mail(os.environ.get("LIVE_TO", ""), f"{u['ceo']} {'bought' if kind == 'bought' else 'sold'} {u['tk']} ({money(value) if value else 'amount unstated'})", line)
                if sent:
                    lines[-1] += "  ← mailed"
        seen.add(acc)
    return lines


def main(argv):
    from fle.edgar import EdgarClient
    client = EdgarClient()
    uni = universe()
    os.makedirs(os.path.dirname(SEEN), exist_ok=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    seen = set(open(SEEN, encoding="utf-8").read().split()) if os.path.exists(SEEN) else set()
    loop = "--loop" in argv
    while True:
        lines = one_pass(client, uni, seen)
        stamp = dt.date.today().isoformat()
        if lines:
            with open(OUT, "a", encoding="utf-8") as fh:
                if os.path.getsize(OUT) == 0:
                    fh.write("# Live: a CEO's Form 4 the minute it landed · the pipeline suggests, you post\n\n")
                fh.write(f"## {stamp}\n" + "\n".join(lines) + "\n\n")
            print("\n".join(lines))
        else:
            print(f"  {dt.datetime.now().strftime('%H:%M')} nothing new among the latest Form 4s")
        with open(SEEN, "w", encoding="utf-8") as fh:
            fh.write("\n".join(sorted(seen)[-5000:]) + "\n")
        if not loop:
            return 0
        time.sleep(600)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
