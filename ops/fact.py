#!/usr/bin/env python3
"""The sentence the site can say about one company, ready to paste.

    python3 ops/fact.py NVDA            # the reply: the stake now and a year ago, the record, the URL
    python3 ops/fact.py NVDA TSLA DELL  # several

THE PIPELINE SUGGESTS; A PERSON PUBLISHES. Nothing here posts anywhere.
Every line carries the company's URL, never the home page. Every figure is
the site's own number as of the file the nightly wrote. The day's lines
and the week's thread moved to ops/moves.py on 2026-09-15 (every kind,
ranked by the move of the stake); this file keeps the reply.
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


def year_ago(tk, asof):
    """', from 3.1% a year ago (sold −18%, compensation +4%)', from the
    record (ops/moves.py); '' when the record has no year or nothing moved."""
    try:
        sys.path.insert(0, HERE)
        import moves
        return moves.year_clause(moves.Data(ROOT), tk, asof or dt.date.today().isoformat())
    except Exception:  # noqa: BLE001 - no history file: the sentence stands without the year
        return ""


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
    s = f"{ceo} owns {pct(p)} of {co} ({tk}) as of the {nice(asof)} filing{year_ago(tk, asof)}, {who}. "
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


def main(argv):
    panel, founders, by = load()
    drafts = os.path.join(ROOT, "drafts")
    os.makedirs(drafts, exist_ok=True)
    if "--today" in argv or "--monday" in argv:
        print("  moved: python3 ops/moves.py today | week [DATE] | stakes [DATE]")
        return 2
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
