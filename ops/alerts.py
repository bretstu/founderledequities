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
import re
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


_SUFFIX = re.compile(r"[,\s]+(inc\.?|incorporated|corp\.?|corporation|co\.?|company|ltd\.?|limited|plc|l\.?p\.?|n\.?v\.?|s\.?a\.?|holdings?|group)\s*$", re.I)


def short_name(company: str, tk: str) -> str:
    """"Ouster, Inc." -> "Ouster"; the ticker when there is no name."""
    n = (company or "").strip()
    for _ in range(2):
        n = _SUFFIX.sub("", n).strip(" ,")
    return n or tk


def companies(root=ROOT) -> dict:
    p = os.path.join(root, "panel.csv")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return {(r.get("ticker") or "").upper(): r.get("company") or "" for r in csv.DictReader(fh)}


def sentence(r, value, name=None):
    """THE HEADLINE, in the tape's words (ops/kinds.py): the company by name,
    the kind as the site says it (on a plan, at their own discretion, on the
    open market; otherwise the tape's label). No date in it."""
    tk, ceo, code = r["ticker"].upper(), r.get("ceo") or "", r.get("code") or ""
    who = name or tk
    amt = f" {kinds.money(value)} of" if value else ""
    plan = (r.get("plan") or "") == "plan"
    if code == "P":
        return f"{ceo} bought{amt} {who} on the open market."
    if code == "S" and not plan:
        return f"{ceo} sold{amt} {who} at their own discretion."
    if code == "S":
        return f"{ceo} sold{amt} {who} on a plan."
    what = kinds.detail_of(r) or "a filing"
    mv = _num(r.get("pct_of_holding")) or 0.0
    return f"{ceo}\u2019s {who} stake {'rose' if mv > 0 else 'fell'} {abs(mv):.1f}%: {what}."


_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def long_day(iso: str) -> str:
    """2026-09-14 -> Monday, September 14"""
    import datetime as _dt
    try:
        d = _dt.date.fromisoformat((iso or "")[:10])
    except ValueError:
        return iso or ""
    return f"{d.strftime('%A')}, {_MONTHS[d.month - 1]} {d.day}"


def _did(r, code, plan, shares):
    """The verb phrase of the body's first sentence, by kind."""
    n = f"{shares:,.0f} shares" if shares else "shares"
    if code == "P":
        return f"bought {n}"
    if code == "S" and plan:
        return f"sold {n} under a plan set in advance"
    if code == "S":
        return f"sold {n} at their own discretion"
    what = (kinds.detail_of(r) or "").lower()
    if "award" in what or "granted" in what:
        return f"was granted {n}"
    if "withheld" in what:
        return f"had {n} withheld for tax"
    if "option" in what or "exercis" in what:
        return f"exercised options for {n}"
    if "gift" in what:
        return f"gave {n} away"
    if "convert" in what:
        return f"converted {n}"
    return f"{what or 'filed'}: {n}"


def mdy(iso: str) -> str:
    """2026-09-15 -> 09/15/2026"""
    try:
        y, m, d = (iso or "")[:10].split("-")
        return f"{m}/{d}/{y}"
    except ValueError:
        return iso or ""


def facts(r, value, founder: bool) -> list:
    """THE ALERT'S FACT LINES (2026-09-18): three questions, one line each,
    scannable on a phone among other alerts. What happened (the verb, the
    shares, the value when the filing states one, the kind); when
    (transaction and filing dates, numeric); what it did to the stake. A
    filing that restated the holding beyond its transaction gets a fourth
    line and no false before-and-after."""
    tk, code = r["ticker"].upper(), r.get("code") or ""
    plan = (r.get("plan") or "") == "plan"
    shares = abs(_num(r.get("shares")) or 0)
    what = (kinds.detail_of(r) or "").lower()
    if code == "P":
        verb, how = "Bought", "open market"
    elif code == "S":
        verb, how = "Sold", "pre-set plan" if plan else "own discretion"
    elif "award" in what or "granted" in what:
        verb, how = "Granted", ""
    elif "withheld" in what:
        verb, how = "Withheld", "for tax"
    elif "vest" in what:
        verb, how = "Vested", ""
    elif "option" in what or "exercis" in what:
        verb, how = "Exercised", "options"
    elif "gift" in what:
        verb, how = "Gave", "gift"
    elif "convert" in what:
        verb, how = "Converted", ""
    else:
        verb, how = "Filed", what
    bits = []
    if shares:
        bits.append(f"{shares:,.0f} shares")
    if value:
        bits.append(kinds.money(value))
    if how:
        bits.append(how)
    out = [(verb, " \u00b7 ".join(bits))]
    # THE DAY'S OTHER DISPOSITION (Red Cat): named on its own line, and the
    # transaction's share of the holding is the transaction's, not the day's
    also, also_detail = _num(r.get("also_shares")), (r.get("also_detail") or "").strip()
    if also and also_detail:
        out.append(("Also filed", f"{abs(also):,.0f} shares {also_detail}"))
    when, filed = mdy(r.get("traded") or r.get("filed")), mdy(r.get("filed"))
    out.append(("Transaction date", when))
    out.append(("Filing date", filed))
    after, before = _num(r.get("pct_after")), before_pct(r)
    mv = _num(r.get("pct_of_holding"))
    held_after, net = _num(r.get("holding_after")), _num(r.get("net_change"))
    if shares and held_after is not None and net is not None and (held_after - net) > 0:
        own = shares / (held_after - net) * 100 * (1 if code == "P" or (code not in ("S",) and (net or 0) > 0) else -1)
        mv_txt = f"{own:+.1f}% of the holding" + (" in all" if also and abs(also) >= 1 else "")
        if also and abs(also) >= 1 and mv is not None:
            mv_txt = f"{mv:+.1f}% of the holding in all"
    else:
        mv_txt = f"{mv:+.1f}% of the holding" if mv else ""
    f = lambda x: f"{x:.3f}%" if x < 1 else f"{x:.2f}%"  # noqa: E731
    res, held = _num(r.get("residue")), _num(r.get("holding_after"))
    if res and held and abs(res) / max(abs(held) + abs(res), 1.0) > 0.02:
        out.append(("Stake", f"now reads {f(after)}" if after is not None else "see the page"))
        out.append(("Note", "this filing restated the holding beyond the transaction; the page says why"))
        return out
    if after is not None and before is not None and abs(after - before) > 0.0005:
        arrow = f"{f(before)} \u2192 {f(after)}"
        out.append(("Stake", arrow + (f"  ({mv_txt})" if mv_txt else "")))
    elif after is not None:
        out.append(("Stake", f(after)))
    return out


def body(r, value, founder: bool):
    """THE BODY (2026-09-17): three sentences. The transaction (day, shares,
    value from the filing's own price); what it did to the holding (the
    move as a share of what they held, the stake before and after, by
    ticker); the filing date. "They": the record carries no pronoun."""
    tk, code = r["ticker"].upper(), r.get("code") or ""
    plan = (r.get("plan") or "") == "plan"
    shares = abs(_num(r.get("shares")) or 0)
    role = "founder and chief executive" if founder else "chief executive"
    first = f"On {long_day(r.get('traded') or r.get('filed'))}, {tk}\u2019s {role} {_did(r, code, plan, shares)}"
    first += f", about {kinds.money(value)} at the reported price." if value else "."
    mv = _num(r.get("pct_of_holding"))
    after, before = _num(r.get("pct_after")), before_pct(r)
    f = lambda x: f"{x:.3f}%" if x < 1 else f"{x:.2f}%"  # noqa: E731
    # A FILING THAT MOVED THE STAKE BEYOND ITS OWN TRANSACTION (2026-09-17,
    # EverCommerce: a $6K sale on a filing that restated the holding from
    # 4.09% to 2.83%). The residue is history's; when it is large against
    # the holding, the alert says so instead of pairing the sale with a
    # before-and-after it did not cause, and points at the page, where the
    # grade's sentence says why.
    res, held = _num(r.get("residue")), _num(r.get("holding_after"))
    if res and held and abs(res) / max(abs(held) + abs(res), 1.0) > 0.02:
        second = (f"The same filing restated the holding {'lower' if res < 0 else 'higher'} than the transaction explains; "
                  f"the stake now reads {f(after)} of {tk}, and the company page says why.") if after is not None else \
                 "The same filing restated the holding beyond what the transaction explains; the company page says why."
        third = f"Filed {long_day(r.get('filed'))}." if r.get("filed") else ""
        return " ".join(x for x in (first, second, third) if x)
    second = ""
    if mv is not None and mv != 0:
        second = f"That {'adds' if mv > 0 else 'is'} {abs(mv):.1f}% {'to' if mv > 0 else 'of'} what they held"
        if after is not None and before is not None and abs(after - before) > 0.0005:
            second += f"; their stake in {tk} goes from {f(before)} to {f(after)}."
        elif after is not None:
            second += f"; they now own {f(after)} of {tk}."
        else:
            second += "."
    elif after is not None:
        second = f"They now own {f(after)} of {tk}."
    third = f"Filed {long_day(r.get('filed'))}." if r.get("filed") else ""
    return " ".join(x for x in (first, second, third) if x)


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def before_pct(r):
    """The stake before this filing: the holding after less the net change, over the count."""
    after, net, out = _num(r.get("holding_after")), _num(r.get("net_change")), _num(r.get("outstanding"))
    if after is None or net is None or not out:
        return None
    return (after - net) / out * 100


def founders_of(root=ROOT) -> set:
    """The founder-led tickers (founders.csv): the live alert's scope."""
    p = os.path.join(root, "founders.csv")
    if not os.path.exists(p):
        return set()
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return {(r.get("ticker") or "").upper() for r in csv.DictReader(fh) if (r.get("founder") or "").lower() == "yes"}


def decisions(events_p, since, founders=None, names=None):
    """WHAT A WATCH MAILS (2026-09-17): the stake moved. An open-market
    purchase or a discretionary sale of any size (the site's two decisions),
    or any other filing that moved the holding by MIN_MOVE per cent or more
    (a planned sale, a grant, a gift, an exercise). One definition, the same
    as the tape's "Moved the stake" chip and the site-wide founder mail;
    the About page states it. Pre-IPO filings and share-count restatements
    are not moves."""
    out = []
    founders = founders_of() if founders is None else founders
    names = companies() if names is None else names
    with open(events_p, encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            filed = r.get("filed") or ""
            code = r.get("code") or ""
            # ON OR AFTER THE MARK (2026-09-17). The mark is a DATE, and the
            # comparison was strict: after the first run of a day, every
            # later filing of the same day read as already posted, and three
            # founder discretionary sales one evening went unmailed. The run
            # endpoint keeps the sent-record per watch and accession, so
            # re-posting a day's earlier events is harmless; skipping its
            # later ones was not.
            if filed < since or not code:
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
            tk = r["ticker"].upper()
            name = short_name(names.get(tk, ""), tk)
            b = before_pct(r)
            out.append({"tk": tk, "ceo": r.get("ceo") or "", "code": code, "company": name,
                        "value": value, "pct_after": r.get("pct_after") or "", "pct_before": f"{b:.2f}" if b is not None else "",
                        "shares": r.get("shares") or "", "move": r.get("pct_of_holding") or "",
                        # TWO PROMISES, ONE POST (2026-09-24). A per-company
                        # watch asked about that person: any trade, or any
                        # other move of 1%+. The site-wide founder stream
                        # promises only moves of 1% or more, so each event
                        # says whether it clears that bar and the run
                        # endpoint filters the FOUNDERS watches by it.
                        "move1": 1 if mv >= MIN_MOVE else 0,
                        "traded": r.get("traded") or "", "filed": filed,
                        "accession": r.get("accession") or f"{tk}:{filed}:{code}",
                        "url": r.get("url") or "", "kind": "decision" if decision else "move",
                        "founder": tk in founders,     # the live alert's scope (functions/api/watch/run.js)
                        "sentence": sentence(r, value, name),
                        "body": body(r, value, tk in founders),
                        "facts": facts(r, value, tk in founders)})
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
    print(f"  alerts: {len(evs)} moves filed {since or 'ever'} <= filed <= {newest} "
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
