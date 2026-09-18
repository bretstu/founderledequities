#!/usr/bin/env python3
"""THE WATCHER (distribution): a chief executive's Form 4, the minute it lands.

    python3 ops/live.py           # one pass: read EDGAR's latest Form 4s, report the new ones
    python3 ops/live.py --show    # what is on the feed right now, and which are ours (proof)
    python3 ops/live.py --find 0001628280-26-061620 [...]   # where on the feed an accession sits, and its feed timestamp
    python3 ops/live.py --loop    # every five minutes until stopped

Every pass reads EDGAR's feed of the most recent Form 4s (one request),
keeps the filings whose issuer is a founder-led company in the universe
and whose reporting owner is that founder (both ids are in the panel),
and for each one not seen before reads the filing through the pipeline's
own parser, so the kind is the site's kind: an open-market purchase, a
discretionary sale, a sale under a pre-set plan, or compensation. Each
becomes a line in drafts/live-<day>.md with the time it landed, and
every one runs the targeted refresh so the page carries it within
minutes. WHAT IS MAILED to LIVE_TO from .env, once the run has published
the number, is what is worth a post:
  - a founder's open-market purchase or discretionary sale, any size;
  - any other filing by a founder that moved their holding by LIVE_MIN_MOVE
    percent or more (1, of the holding, not of the company: the tape's
    "Moved the stake" chip, and the rule a reader's own watch uses);
Everything else is written down and left for the tape. Hired chief
executives are not watched; the nightly carries their filings.

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

FEED = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=4&owner=include&count=100&output=atom&start={start}"
PAGES = 8   # 8 pages of 100 entries; about 20 Form 4s a page after the filter
SITE = "https://founderledequities.com"
SEEN = os.path.join(ROOT, "weekly", "live-seen.txt")
WAITING = os.path.join(ROOT, "weekly", "live-waiting.json")   # accession -> passes spent waiting for EDGAR's index


def _load_waiting():
    try:
        with open(WAITING, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_waiting(w):
    os.makedirs(os.path.dirname(WAITING), exist_ok=True)
    with open(WAITING, "w", encoding="utf-8") as fh:
        json.dump(w, fh)
sys.path.insert(0, HERE)
import kinds  # noqa: E402
OUT = os.path.join(ROOT, "drafts", "x-live.md")
COMPENSATION = kinds.COMP_LABELS  # the page's set (ops/kinds.py), one copy for every script


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
    now. FOUNDERS ONLY (founders.csv, the same file the site uses): a
    hired chief executive's filing waits for the nightly. The watcher's job
    is timely posts, and those are about founders."""
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
                            "pct": r.get("pct") or "", "asof": r.get("shares_as_of") or "", "founder": True}
    return out


def feed(client, start=0):
    """One page of the latest Form 4s: accession -> {issuer cik, reporter
    ciks}. EDGAR lists each filing once per party, so the same accession
    appears for the issuer and for each reporting owner: 100 entries is
    about 50 filings."""
    body = client.get(FEED.format(start=start), use_cache=False)
    root = ET.fromstring(body)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    acc_of = re.compile(r"/data/(\d+)/\d+/(\d{10}-\d{2}-\d{6})")
    filings = {}
    for e in root.findall("a:entry", ns):
        title = e.findtext("a:title", default="", namespaces=ns)
        # EDGAR's type=4 matches any form with a 4 in it (424B2 prospectuses,
        # fund filings); only Form 4 and its amendment are wanted
        if not (title.startswith("4 - ") or title.startswith("4/A - ")):
            continue
        link = (e.find("a:link", ns).get("href") if e.find("a:link", ns) is not None else "") or ""
        m = acc_of.search(link)
        if not m:
            continue
        cik, acc = int(m.group(1)), m.group(2)
        d = filings.setdefault(acc, {"issuer": None, "reporters": set(), "title": title,
                                     "updated": e.findtext("a:updated", default="", namespaces=ns), "page": start // 100})
        if "(Issuer)" in title:
            d["issuer"] = cik
        elif "(Reporting)" in title:
            d["reporters"].add(str(cik))
    return filings


class NotYetIndexed(Exception):
    """EDGAR's per-filer index has not caught up with its live feed."""


def describe(client, uni, cik, acc):
    """The filing as the site's parser reads it: (kind, amount, label,
    traded date). No walk, no stake after (see the module note).

    THE PARSER READS TWO INDEXES, the company's and the person's, and keeps
    the filings on both. Both must be fresh (their cached copies are
    dropped) and both must list this accession; EDGAR's indexes lag its
    live feed by minutes, so a filing not yet on one raises NotYetIndexed
    and the pass leaves it for the next."""
    from fle.events import build_events
    u = uni[cik]
    owner = int(str(u["owner"]).lstrip("0"))
    for c in (cik, owner):
        try:
            os.remove(client._cache_path(f"https://data.sec.gov/submissions/CIK{c:010d}.json"))
        except OSError:
            pass
    for c in (cik, owner):
        if not any(f.get("accessionNumber") == acc for f in client.submissions(c).get("_filings", [])):
            raise NotYetIndexed(f"CIK{c} does not list {acc} yet")
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


LAST_MAIL_ERROR = ""


def send_mail(to, subject, text, attachment=None):
    """One email through Resend. On failure the reason is kept in
    LAST_MAIL_ERROR and printed, never swallowed (2026-09-14: a silent
    False hid whatever Resend said). `attachment`: a (filename, bytes) to
    send along (the post card, 2026-09-18)."""
    global LAST_MAIL_ERROR
    key = os.environ.get("RESEND_API_KEY")
    if not key:
        LAST_MAIL_ERROR = "RESEND_API_KEY is not set in .env"
        return False
    if not to:
        LAST_MAIL_ERROR = "LIVE_TO is not set in .env"
        return False
    body = {"from": os.environ.get("LIVE_FROM", "Founder Led Equities <tape@founderledequities.com>"),
            "to": [to], "subject": subject, "text": text}
    if attachment:
        import base64
        body["attachments"] = [{"filename": attachment[0], "content": base64.b64encode(attachment[1]).decode()}]
    req = urllib.request.Request("https://api.resend.com/emails",
                                 data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "User-Agent": "founderledequities-live/1"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            LAST_MAIL_ERROR = ""
            return r.status < 300
    except urllib.error.HTTPError as e:
        LAST_MAIL_ERROR = f"Resend answered {e.code}: {e.read().decode(errors='replace')[:200]}"
    except Exception as e:  # noqa: BLE001
        LAST_MAIL_ERROR = f"{e.__class__.__name__}: {str(e)[:120]}"
    print(f"  mail failed: {LAST_MAIL_ERROR}")
    return False


def post_block(u, ev):
    """-> (text, (filename, png bytes) or None). The X post's three lines
    (ops/post_card.post_text) and the reply line, and the card drawn from
    the same event. Never fails the mail: a card that cannot be drawn is
    simply not attached."""
    try:
        sys.path.insert(0, HERE)
        import post_card
        kind = post_card.post_kind(ev)
        founder = bool(u.get("founder"))
        minutes = None
        before = ""
        try:
            h, n, o = float(ev.get("holding_after") or 0), float(ev.get("net_change") or 0), float(ev.get("outstanding") or 0)
            before = f"{(h - n) / o * 100:.4f}" if o else ""
        except ValueError:
            before = ""
        text = post_card.post_text(u["tk"], u.get("ceo") or "", founder, kind, ev.get("value") or "",
                                   ev.get("pct_of_holding") or "", ev.get("pct_after") or "", minutes, pct_before=before)
        # THE LINK IS THE CARD (2026-09-18): the page's own OG image is the
        # compact card with this trade on it, so the post is text plus the
        # link and X draws the card; nothing to attach
        block = ("POST (paste as is; the link renders the card)\n"
                 + "-" * 40 + "\n" + text + f"\nhttps://founderledequities.com/company/{u['tk']}/\n" + "-" * 40)
        return block, None
    except Exception as e:  # noqa: BLE001
        print(f"  post block skipped for {u['tk']}: {e.__class__.__name__}: {str(e)[:80]}")
        return "", None


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
    a = None
    try:
        a = float(r.get("pct_after") or "")
        after = f" Now owns {a:.3f}%." if a < 1 else f" Now owns {a:.2f}%."
    except ValueError:
        pass
    # THE FILING DOES NOT EXPLAIN THE WHOLE CHANGE: the per-filing move is
    # blank when the walk could not attribute the day to this sale alone
    # (a share-count restatement, a vehicle change). Then the stakes before
    # and after are said, with the caveat, so the post is checked first.
    caveat = ""
    if not mv and a is not None and u.get("pct"):
        try:
            b = float(u["pct"])
            if b > 0 and abs(a - b) / b >= 0.02:
                caveat = (f" The same filing restated the holding {'lower' if a < b else 'higher'} than the "
                          f"{'sale' if code == 'S' else 'purchase'} explains: {b:.2f}% before, {a:.2f}% after. Read the record before posting.")
        except ValueError:
            pass
    return f"{u['ceo']} {verb}{amt} of {u['tk']} {how}{mv}.{after}{caveat}\n{SITE}/company/{u['tk']}/"


def worth_a_post(u, r):
    """The mail rule, from the published event. Returns the reason, or ''."""
    code = r.get("code")
    plan = (r.get("plan") or "") == "plan"
    comp = (r.get("label") or "") in COMPENSATION or (r.get("pre_ipo") or "") in ("1", "true", "True")
    try:
        v = float(r.get("value") or 0) if not (r.get("price_flag") or "") else 0.0
    except ValueError:
        v = 0.0
    try:
        ch = abs(float(r.get("pct_of_holding") or 0))
    except ValueError:
        ch = 0.0
    if not (r.get("pct_of_holding") or "").strip():
        # the walk left the move blank: judge by the stake before and after
        try:
            b, a = float(u.get("pct") or 0), float(r.get("pct_after") or 0)
            if b > 0 and a > 0:
                ch = abs(a - b) / b * 100
        except ValueError:
            pass
    # ONE DEFINITION OF A MOVE (2026-09-17): a decision of any size, or any
    # other filing that moved the holding by one per cent or more, the same
    # as the tape's chip and the per-company watch (ops/alerts.py)
    min_move = float(os.environ.get("LIVE_MIN_MOVE", "1"))
    decision = code in ("P", "S") and not plan and not comp
    if not u.get("founder"):
        return ""
    if decision:
        return "founder's open-market buy" if code == "P" else "founder's discretionary sale"
    # THE KIND IS THE PAGE'S (ops/kinds.py, 2026-09-15): an award, a gift or
    # an exercise that moved the holding is named for what it is, not
    # "compensation" for everything that was not a plan
    what = "plan" if plan else kinds.detail_of(r)
    if ch >= min_move:
        return f"{what} that moved the holding {ch:.1f}%"
    return ""


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
        why = worth_a_post(u, ev)
        # THE POST, READY (2026-09-18): the three lines in the site's words and
        # the card as an attachment, so the owner's copy is the whole workflow:
        # paste, attach, post, reply with the link
        post, card = post_block(u, ev)
        if post:
            text = text + "\n\n" + post
        sent = bool(why) and send_mail(os.environ.get("LIVE_TO", ""),
                                       f"{u['ceo']} {'bought' if ev.get('code') == 'P' else 'sold'} {u['tk']}: the page is live ({why})", text,
                                       attachment=card)
        lines.append(f"- {dt.datetime.now().strftime('%H:%M')} published · {text.replace(chr(10), ' · ')}"
                     + (f"  ← mailed: {why}" if sent
                        else f"  ← WORTH A POST ({why}) BUT THE MAIL FAILED: {LAST_MAIL_ERROR}" if why
                        else "  (not a post: a small plan or compensation)"))
    return lines, still


def known_accessions():
    """What the site already carries: every accession in events.csv. A feed
    entry for one of these is not news, whatever the watcher's memory says
    (EDGAR re-lists filings from time to time with the same accession; three
    of Friday's filings reappeared on Tuesday morning and were mailed as
    new, 2026-09-15)."""
    out = set()
    try:
        with open(os.path.join(ROOT, "events.csv"), encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                a = r.get("accession")
                if a:
                    out.add(a)
    except OSError:
        pass
    return out


def one_pass(client, uni, seen):
    # READ BACK TO THE LAST PASS'S FRONTIER. In the evening rush more than
    # fifty Form 4s can land in five minutes, so one page is not enough:
    # pages are read, newest first, until one holds a filing already seen
    # (proof nothing fell between) or PAGES are exhausted (logged as an
    # overflow; the nightly catches whatever fell between). Every filing is
    # remembered, ours or not, so the frontier is real.
    filings = {}
    reached = not seen
    for i in range(PAGES):
        page = feed(client, start=i * 100)
        if not page:
            break
        filings.update(page)
        if any(acc in seen for acc in page):
            reached = True
            break
    if not reached:
        print(f"  {dt.datetime.now().strftime('%H:%M')} the feed overflowed since the last pass "
              f"({len(filings)} filings read, none seen before): some may have fallen between; the nightly catches them")
    new = []
    known = None
    lines = []
    for acc, d in filings.items():
        if acc in seen:
            continue
        if d["issuer"] not in uni or uni[d["issuer"]]["owner"] not in d["reporters"]:
            seen.add(acc)          # not a founder's own filing: remembered, never reported
            continue
        if known is None:
            known = known_accessions()
        if acc in known:
            # THE EVIDENCE, KEPT: which page it sat on and the feed's own stamp.
            # A fresh stamp on an early page is EDGAR re-disseminating; an old
            # stamp on a deep page is the watcher paging too far.
            lines.append(f"- {dt.datetime.now().strftime('%H:%M')} {uni[d['issuer']]['tk']} · {acc} is already on the site (filed earlier); "
                         f"it reappeared on feed page {d.get('page')} with feed stamp {d.get('updated') or '?'} · nothing to do")
            seen.add(acc)
            continue
        new.append((acc, d["issuer"]))
    decisions = []
    now = dt.datetime.now().strftime("%H:%M")
    for acc, cik in new:
        u = uni[cik]
        filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/"
        try:
            parts = describe(client, uni, cik, acc)
        except NotYetIndexed as e:
            # not seen: the next pass tries again; after an hour of passes it is said out loud
            waiting = _load_waiting()
            waits = waiting.get(acc, 0) + 1
            waiting[acc] = waits
            _save_waiting(waiting)
            print(f"  {now} {u['tk']} · {u['ceo']} filed {acc}; EDGAR's index has not listed it yet ({e}); waiting (pass {waits})")
            if waits >= 12:
                lines.append(f"- {now} {u['tk']} · {u['ceo']} filed a Form 4 an hour ago that EDGAR's index still does not list; the nightly will carry it · {filing_url}")
                seen.add(acc)
            continue
        except Exception as e:  # noqa: BLE001
            parts = []
            lines.append(f"- {now} {u['tk']} · {u['ceo']} filed a Form 4 (could not read it: {str(e)[:60]}) · {filing_url}")
        if not parts:
            # A FOUNDER'S FILING IS NEVER SILENT: no purchase or sale in it
            # (an exercise held, a gift, a grant) is still a line
            lines.append(f"- {now} {u['tk']} · {u['ceo']} filed a Form 4 with no purchase or sale in it (an exercise, a gift or a grant; the page carries it after the nightly) · {filing_url}")
        for kind, value, label, traded in parts:
            verb = {"bought": "bought", "discretionary": "sold at their own discretion",
                    "planned": "sold under a pre-set plan", "compensation": "compensation:"}[kind]
            amt = f" {money(value)}" if value else ""
            stake = (f" Stake as of the {u['asof']} filing: {float(u['pct']):.2f}%; the new figure lands with ops/now.sh."
                     if u["pct"] else "")
            line = (f"- {now} {u['tk']} · {u['ceo']} {verb}{amt}{' (' + label + ')' if kind == 'compensation' else ''}, traded {traded}.{stake}"
                    f"\n  {SITE}/company/{u['tk']}/ · filing https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/")
            lines.append(line)
            decisions.append((acc, cik))    # every CEO filing runs the data; the mail rule comes after
        seen.add(acc)
    return lines, decisions


def main(argv):
    from fle.edgar import EdgarClient
    if "--test-mail" in argv:
        # THE MAIL PATH, PROVED: one sample through the same function and
        # address the real alerts use. Nothing else runs.
        to = os.environ.get("LIVE_TO", "")
        ok = send_mail(to, "Founder Led Equities: the watcher's mail path works",
                       "This is the watcher's test. A founder's decision arrives here the same way, with the sentence and the page's address.\n"
                       f"{SITE}/tape/")
        print(f"  test mail to {to or '(LIVE_TO unset)'}: {'sent' if ok else 'FAILED: ' + LAST_MAIL_ERROR}")
        return 0 if ok else 1
    if "--find" in argv:
        # DIAGNOSIS: for each accession, the page of the feed it is on and the
        # feed's own <updated> stamp for it. An old filing with a fresh stamp
        # on page 0 was re-disseminated by EDGAR; an old filing with its
        # original stamp on page 7 means the watcher paged too far back.
        client = EdgarClient()
        want = {a for a in argv[argv.index("--find") + 1:] if re.match(r"\d{10}-\d{2}-\d{6}$", a)}
        ns = {"a": "http://www.w3.org/2005/Atom"}
        acc_of = re.compile(r"/data/(\d+)/\d+/(\d{10}-\d{2}-\d{6})")
        found = {}
        for i in range(PAGES):
            body = client.get(FEED.format(start=i * 100), use_cache=False)
            root = ET.fromstring(body)
            for e in root.findall("a:entry", ns):
                link = (e.find("a:link", ns).get("href") if e.find("a:link", ns) is not None else "") or ""
                m = acc_of.search(link)
                if m and m.group(2) in want:
                    found.setdefault(m.group(2), []).append((i, e.findtext("a:updated", default="", namespaces=ns), e.findtext("a:title", default="", namespaces=ns)))
        for a in sorted(want):
            if a in found:
                for pg, upd, title in found[a]:
                    print(f"  {a}  page {pg}  feed stamp {upd}  {title[:60]}")
            else:
                print(f"  {a}  not on the first {PAGES} pages of the feed now")
        return 0
    if "--show" in argv:
        client = EdgarClient()
        uni = universe()
        seen = set(open(SEEN, encoding="utf-8").read().split()) if os.path.exists(SEEN) else set()
        # THE PROOF: the feed as it stands, every entry, ours marked. A
        # founder's filing shows as "FOUNDER"; a filing by another insider at
        # a company in the universe as "other insider"; the rest as "-".
        filings = feed(client, 0)
        by_cik = {}
        with open(os.path.join(ROOT, "panel.csv"), encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                try:
                    by_cik[int(r.get("cik") or 0)] = r["ticker"].upper()
                except ValueError:
                    pass
        print(f"  {len(filings)} Form 4 filings on EDGAR's feed right now (the latest 100 accepted)")
        ours = 0
        for acc, d in sorted(filings.items(), key=lambda kv: kv[0], reverse=True):
            iss = d["issuer"]
            if iss in uni:
                tag = "FOUNDER  " if uni[iss]["owner"] in d["reporters"] else "other insider"
                name = f"{uni[iss]['tk']} · {uni[iss]['ceo'] if tag.startswith('FOUNDER') else d['title'][4:]}"
                ours += 1
            elif iss in by_cik:
                tag, name, ours = "in universe", f"{by_cik[iss]} · {d['title'][4:]}", ours + 1
            else:
                tag, name = "-", d["title"][4:]
            print(f"  {acc}  {tag:<13} {name[:70]}{'  (seen)' if acc in seen else ''}")
        print(f"  {ours} of them at companies in the universe")
        return 0

    # ONE PASS AT A TIME. The timer and a run by hand must never overlap:
    # two passes reading the same memory would both report a filing and
    # then overwrite each other's memory (2026-09-14, 17:04).
    import fcntl
    os.makedirs(os.path.join(ROOT, "weekly"), exist_ok=True)
    guard = open(os.path.join(ROOT, "weekly", "live-pass.lock"), "w")
    try:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(f"  {dt.datetime.now().strftime('%H:%M')} another pass is running; this one steps aside")
        return 0
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
            fh.write("\n".join(sorted(seen)[-8000:]) + "\n")
        if not loop:
            return 0
        time.sleep(300)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
