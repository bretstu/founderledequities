#!/usr/bin/env python3
"""The sentences the site can say, ready to paste (PLAN.md: distribution).

    python3 ops/fact.py NVDA            # the reply: the stake, the record, the URL
    python3 ops/fact.py NVDA TSLA DELL  # several
    python3 ops/fact.py --today         # drafts/x-today.md: today's decisions, one line each
    python3 ops/fact.py --monday DATE   # drafts/x-monday.md: the week as one thread

THE PIPELINE SUGGESTS; A PERSON PUBLISHES. Nothing here posts anywhere.
Every line carries the company's URL, never the home page: search and the
timeline both need the entity's address. Every figure is the site's own
number as of the file the nightly wrote.
"""
import csv
import datetime as dt
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITE = "https://founderledequities.com"
COMPENSATION = {"exercise and sell", "exercise, part sold", "vested and sold", "convert and sell",
                "sale, position unchanged", "purchase, position unchanged"}


def read(name):
    p = os.path.join(ROOT, name)
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def money(v):
    if v is None:
        return ""
    a = abs(v)
    if a >= 9.995e8:
        return f"${v/1e9:.1f}B".replace(".0B", "B")
    if a >= 9.995e5:
        return f"${v/1e6:.1f}M".replace(".0M", "M")
    if a >= 1e3:
        return f"${v/1e3:.0f}K"
    return f"${v:,.0f}"


def pct(p):
    return "" if p is None else (f"{p:.3f}%" if p < 1 else f"{p:.2f}%")


def nice(d):
    try:
        return dt.date.fromisoformat(d).strftime("%b %-d")
    except (ValueError, TypeError):
        return d or ""


def load():
    panel = {r["ticker"].upper(): r for r in read("panel.csv")}
    founders = {r["ticker"].upper(): (r.get("founder") or "").lower() for r in read("founders.csv")}
    events = read("events.csv")
    by = defaultdict(list)
    for e in events:
        if e.get("code") in ("P", "S"):
            by[e["ticker"].upper()].append(e)
    return panel, founders, by


def record(evs):
    """Since 2016: open-market buys, sales that moved the stake, the last decision."""
    buys = sells = 0
    last = None
    for e in evs:
        if (e.get("label") or "") in COMPENSATION or (e.get("pre_ipo") or "") in ("1", "true", "True"):
            continue
        if e["code"] == "P":
            buys += 1
        else:
            sells += 1
        k = (e.get("traded") or e.get("filed") or "", e.get("filed") or "")
        if last is None or k > last[0]:
            last = (k, e)
    return buys, sells, (last[1] if last else None)


def fact(tk, panel, founders, by):
    """The reply: the stake as of the filing, the record, the URL."""
    r = panel.get(tk)
    if not r:
        return f"{tk}: not in the file."
    ceo = r.get("ceo") or "the CEO"
    co = r.get("company") or tk
    p = num(r.get("pct"))
    asof = r.get("as_of") or r.get("asof") or r.get("shares_as_of") or ""
    buys, sells, last = record(by.get(tk, []))
    who = "a founder" if founders.get(tk) == "yes" else "hired"
    s = f"{ceo} owns {pct(p)} of {co} ({tk}) as of the {nice(asof)} filing, {who}. "
    s += f"Since 2016: {buys} open-market buy{'s' if buys != 1 else ''}, {sells} sale{'s' if sells != 1 else ''} that moved the stake."
    if last is not None:
        v = num(last.get("value")) if not (last.get("price_flag") or "") else None
        amt = f" {money(v)}" if v else ""
        kind = (f"bought{amt} on the open market" if last["code"] == "P"
                else f"sold{amt} on a pre-set plan" if (last.get("plan") or "") == "plan"
                else f"sold{amt} at their own discretion")
        s += f" Last: {kind}, {nice(last.get('traded') or last.get('filed'))}."
    s += f"\n{SITE}/company/{tk}/"
    return s


def today_lines(panel, founders, by, since):
    """One line per decision filed since `since`, notable ones marked."""
    out = []
    for tk, evs in by.items():
        for e in evs:
            filed = e.get("filed") or ""
            if filed <= since or (e.get("label") or "") in COMPENSATION or (e.get("pre_ipo") or "") in ("1", "true", "True"):
                continue
            if e["code"] == "S" and (e.get("plan") or "") == "plan":
                continue
            v = num(e.get("value")) if not (e.get("price_flag") or "") else None
            after = num(e.get("pct_after"))
            change = num(e.get("pct_of_holding"))
            first = (e.get("first_buy") or "") == "1"
            notable = []
            if first:
                notable.append("first buy ever")
            if e["code"] == "S" and v and v >= 10e6:
                notable.append("$10M+ at discretion")
            if change is not None and abs(change) >= 5:
                notable.append(f"stake {change:+.0f}%")
            r = panel.get(tk, {})
            who = "founder" if founders.get(tk) == "yes" else "hired CEO"
            verb = "bought" if e["code"] == "P" else "sold"
            how = "on the open market" if e["code"] == "P" else "at their own discretion"
            line = (f"- {tk} · {e.get('ceo') or r.get('ceo') or ''} ({who}) {verb}"
                    f"{' ' + money(v) if v else ''} {how}, {nice(e.get('traded') or filed)}."
                    f"{' Now owns ' + pct(after) + '.' if after is not None else ''}"
                    f"{'  ← ' + ', '.join(notable) if notable else ''}"
                    f"\n  {SITE}/company/{tk}/")
            out.append((bool(notable), v or 0, line))
    out.sort(key=lambda x: (-x[0], -x[1]))
    return [l for _, _, l in out]


def monday_thread(date, tease=False):
    """The week as one thread: the spoken sentence; every open-market buy
    and every discretionary sale, each with the amount, the stake's move
    and the stake after (the move is the edge; one number a week is the
    marketing, the record and the chart stay Pro); then any planned sale
    that moved the stake by 5% or more, labelled as planned; the link.
    --tease withholds the stake after for names outside the S&P."""
    sys.path.insert(0, HERE)
    import letter  # noqa: E402
    rows, since = letter.week_rows(ROOT, date)
    c = letter.collapse(rows)
    who = lambda k: len({(r["tk"], r["ceo"]) for r in rows if r["kind"] == k})
    b, d, p = who("bought"), who("disc"), who("plan")
    lines = [f"This week: {b} founder{'s' if b != 1 else ''} bought. {d} sold without a plan. "
             f"{p} sale{' was' if p == 1 else 's were'} already scheduled.", ""]
    def move(r):
        ch = r.get("change")
        if ch is None or abs(ch) < 0.05:
            return ""                      # a move too small to say is not said
        if abs(ch) >= 100:
            return f"stake ×{1 + ch/100:.1f}"
        return f"stake {ch:+.2f}%" if abs(ch) < 10 else f"stake {ch:+.1f}%"
    def stake_after(r):
        if r["after"] is None:
            return ""
        if tease and r["sealed"]:
            return " The stake after is in Pro."
        return f" Now owns {pct(r['after'])}."
    def line_for(r, planned=False):
        v = money(r["value"]) if r["value"] and not r["flag"] else ""
        n = f" across {r['n']} filings" if r.get("n", 1) > 1 else ""
        if r["kind"] == "bought":
            what = f"bought{' ' + v if v else ''} of {r['tk']} on the open market{n}"
        elif planned:
            what = f"sold{' ' + v if v else ''} of {r['tk']} under a plan set months ago{n}"
        else:
            what = f"sold{' ' + v if v else ''} of {r['tk']} at their own discretion{n}"
        mv = move(r)
        return f"{r['ceo']} {what}{' (' + mv + ')' if mv else ''}.{stake_after(r)}\n{SITE}/company/{r['tk']}/"
    for r in [x for x in c if x["kind"] == "bought"]:
        lines += [line_for(r), ""]
    for r in [x for x in c if x["kind"] == "disc"]:
        lines += [line_for(r), ""]
    big_plans = [x for x in c if x["kind"] == "plan" and x.get("change") is not None and abs(x["change"]) >= 5]
    if big_plans:
        lines += ["Planned, but large enough to note:", ""]
        for r in big_plans:
            lines += [line_for(r, planned=True), ""]
    lines.append(f"Every filing of the week, founders first, free: {SITE}/tape/")
    return "\n".join(lines) + "\n"


def main(argv):
    panel, founders, by = load()
    drafts = os.path.join(ROOT, "drafts")
    os.makedirs(drafts, exist_ok=True)
    if "--today" in argv:
        since = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        lines = today_lines(panel, founders, by, since)
        p = os.path.join(drafts, "x-today.md")
        head = f"# Today's decisions (filed after {since}) · pick one, write the sentence, post. The pipeline suggests; you publish.\n\n"
        open(p, "w", encoding="utf-8").write(head + ("\n".join(lines) + "\n" if lines else "(nothing filed)\n"))
        print(f"  {p}: {len(lines)} line(s)")
        return 0
    if "--monday" in argv:
        i = argv.index("--monday")
        date = argv[i + 1] if i + 1 < len(argv) else dt.date.today().isoformat()
        p = os.path.join(drafts, "x-monday.md")
        open(p, "w", encoding="utf-8").write(f"# The week of {date}, as one thread · paste, do not auto-post\n\n" + monday_thread(date, tease="--tease" in argv))
        print(f"  {p}")
        return 0
    tks = [a.upper() for a in argv if not a.startswith("-")]
    if not tks:
        print(__doc__)
        return 2
    for tk in tks:
        print(fact(tk, panel, founders, by))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
