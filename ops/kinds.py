#!/usr/bin/env python3
"""THE KINDS OF A FILING, the Python copy of the page's shared functions
(index.html: tapeKind, tapeGroup, tapeDetail, evMove, evDim, actSorted,
tapeCounts, actRow). Decided 2026-09-15 (PLAN.md section 5): every filing
by the chief executive is a row on the tape and on the company page, one
taxonomy for both:

    bought   an open-market (or scheduled) purchase that moved the stake
    disc     a sale the person chose the day of (10b5-1 box unchecked)
    plan     a sale under a pre-set plan (box checked)
    sold     a sale filed before the form had the box (April 2023):
             badged Sold, detail "not stated"
    comp     shares the company gave or took back, and what was sold of
             them (codes A M F D X, and a P/S whose label says the position
             did not move the way a purchase or sale does)
    xfer     gift, conversion, the rest (G C I J L U W Z); pre-IPO rows too

This module exists for the stamped first paint (ops/stamp_static.py and
ops/build_company_pages.py write the tape's rows into the HTML so a
crawler sees what the script draws). tests/test_kinds.py runs the page's
JavaScript through node over every code, label and plan the pipeline
writes and holds this file to the same answers. ops/letter.py, ops/fact.py
and ops/live.py still read purchases and sales only (their own kind_of);
they move here next.
"""
import csv
import datetime as dt
import html
import os

COMP_LABELS = {"exercise and sell", "exercise, part sold", "vested and sold", "convert and sell",
               "sale, position unchanged", "purchase, position unchanged"}
COMP_CODES = {"A", "M", "F", "D", "X"}
KIND_ORDER = {"bought": 0, "disc": 1, "sold": 2, "plan": 3, "comp": 4, "xfer": 5}
KIND_WORD = {"bought": "Bought", "disc": "Discretionary", "sold": "Sold", "plan": "Planned",
             "comp": "Compensation", "xfer": "Transfer"}
GROUP_WORD = {"bought": "Bought", "sold": "Sold", "comp": "Compensation", "xfer": "Transfers"}
KIND_DETAIL = {"exercise and sell": "options cashed", "exercise, part sold": "options cashed, part kept",
               "vested and sold": "vest, part sold", "convert and sell": "units converted",
               "sale, position unchanged": "sale, stake unchanged", "purchase, position unchanged": "purchase, stake unchanged",
               "options exercised": "options exercised, held", "options exercised, tax withheld": "options exercised, tax withheld",
               "award granted": "award granted", "award granted, tax withheld": "award granted, tax withheld",
               "forfeited": "forfeited", "converted": "converted", "gift": "gift",
               "shares withheld for tax": "withheld for tax", "other transaction": "other transaction"}
TAPE_HEAD = ('<table class="tape"><colgroup><col class="tw-kd"><col class="tw-co"><col class="tw-ceo"><col class="tw-v">'
             '<col class="tw-ch"><col class="tw-st"><col class="tw-td"></colgroup>'
             '<thead><tr><th>Kind</th><th>Company</th><th>CEO</th><th class="n">Amount</th><th class="n">Change</th>'
             '<th class="n">New stake</th><th>Traded</th></tr></thead>')


def _pre(e):
    return str(e.get("pre_ipo") or "") in ("1", "true", "True")


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def kind_of(e):
    """The badge. e is an events.csv row (code, label, plan, pre_ipo)."""
    if _pre(e):
        return "xfer"
    code, label, plan = e.get("code") or "", e.get("label") or "", e.get("plan") or ""
    unchanged = code in ("P", "S") and label in COMP_LABELS
    if code == "P" and not unchanged:
        return "bought"
    if code == "S" and not unchanged:
        return "plan" if plan == "plan" else "disc" if plan == "discretionary" else "sold"
    if code in ("P", "S") or code in COMP_CODES:
        return "comp"
    return "xfer"


def group_of(e):
    """The chip: bought, sold, comp, xfer."""
    k = kind_of(e)
    return "sold" if k in ("disc", "plan", "sold") else k


def detail_of(e):
    """The grey word after the badge, the filing's label in the site's words."""
    if _pre(e):
        return "pre-IPO"
    k = kind_of(e)
    if k == "bought":
        return "pre-set plan" if (e.get("plan") or "") == "plan" else "open market"
    if k == "disc":
        return "open market"
    if k == "plan":
        return "pre-set plan"
    if k == "sold":
        return "not stated"
    return KIND_DETAIL.get(e.get("label") or "", "compensation" if k == "comp" else "other transaction")


def move_of(e):
    """The move as a share of the holding, or None when not stated. A
    sealed row (outside the S&P, for the stamped free first paint) carries
    no move, as the page's evMove returns null for a masked row. THE ONE
    GUARD: a filing with no purchase or sale that takes the position on
    record to zero is not ranked."""
    if e.get("sealed"):
        return None
    p = _num(e.get("pct_of_holding"))
    approx = False
    if p is None:
        p = _num(e.get("pct_approx"))
        approx = p is not None
    if p is None:
        return None
    if (e.get("code") or "") not in ("P", "S") and _num(e.get("pct_after")) == 0:
        return None
    return p, approx


def moved(e):
    m = move_of(e)
    return m is not None and abs(m[0]) >= 1


def dim(e):
    if e.get("sealed"):
        return False
    m = move_of(e)
    if m is not None:
        return abs(m[0]) < 1
    return (e.get("code") or "") in ("P", "S") and (e.get("label") or "") in COMP_LABELS and not _pre(e)


def stake_change(v, approx=False):
    """The page's stakeChange, without the word 'stake': '+12%', '−0.45%'."""
    a = "≈ " if approx else ""
    if v <= -100:
        return a + "sold out"
    if v >= 100:
        return a + f"×{1 + v / 100:.1f}"
    m = abs(v)
    if m < 0.005:
        return a + "<0.01%"
    digits = (1 if m < 10 else 0) if m >= 1 else 2
    return f"{a}{'+' if v >= 0 else '−'}{m:.{digits}f}%"


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


def _read(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def window_rows(root, until, days=7, founders_only=True):
    """Every filing by a chief executive filed in the window ending
    `until` (founders only by default), pre-IPO rows left out: the tape's
    rows, as the page's tapeWindow draws them."""
    since = (dt.date.fromisoformat(until) - dt.timedelta(days=days)).isoformat()
    events = _read(os.path.join(root, "events.csv"))
    founders = {r["ticker"].upper(): (r.get("founder") or "") for r in _read(os.path.join(root, "founders.csv"))}
    sp_files = sorted(f for f in os.listdir(os.path.join(root, "universe")) if f.startswith("sp500-") and f.endswith(".csv"))
    sp = {r["ticker"].upper() for r in _read(os.path.join(root, "universe", sp_files[-1]))} if sp_files else set()
    out = []
    for e in events:
        if _pre(e) or not (since < (e.get("filed") or "") <= until):
            continue
        tk = (e.get("ticker") or "").upper()
        if founders_only and founders.get(tk) != "yes":
            continue
        out.append(dict(e, tk=tk, sealed=tk not in sp))
    return out, since


def sorted_rows(rows):
    """The page's actSorted: kind groups in order, |move| descending within
    each; a row with no figure follows the ranked rows of its group, newest
    first. Stable passes, least significant key first."""
    out = list(rows)
    out.sort(key=lambda e: e.get("tk") or "")
    out.sort(key=lambda e: e.get("filed") or "", reverse=True)
    out.sort(key=lambda e: -abs(move_of(e)[0]) if move_of(e) is not None else 0)
    out.sort(key=lambda e: 0 if move_of(e) is not None else 1)
    out.sort(key=lambda e: KIND_ORDER[kind_of(e)])
    return out


def counts(rows):
    """The page's tapeCounts, for the weather line: by kind, never by a
    figure, so the line reads the same on both sides of the seal."""
    who = lambda f: len({(e.get("tk"), e.get("ceo")) for e in rows if f(e)})  # noqa: E731
    paid_in = lambda e: kind_of(e) == "comp" and ((e.get("code") or "") in ("A", "M") or (e.get("label") or "") in ("exercise, part sold", "vested and sold"))  # noqa: E731
    return {
        "bought": who(lambda e: kind_of(e) == "bought"),
        "first": sum(1 for e in rows if kind_of(e) == "bought" and str(e.get("first_buy") or "") == "1"),
        "disc": who(lambda e: kind_of(e) == "disc"),
        "plan": who(lambda e: kind_of(e) == "plan"),
        "paid": who(paid_in),
        "gave": who(lambda e: kind_of(e) == "xfer" and (e.get("label") or "") == "gift"),
        "n": len(rows),
    }


def weather(rows):
    c = counts(rows)
    parts = [f"<b>{c['bought']}</b> CEO{'' if c['bought'] == 1 else 's'} bought"]
    if c["first"]:
        parts.append(f"<b>{c['first']}</b> for the first time ever")
    parts += [f"<b>{c['disc']}</b> cut a stake", f"<b>{c['plan']}</b> sold on a plan", f"<b>{c['paid']}</b> paid in shares",
              f"<b>{c['gave']}</b> gave shares away"]
    return " · ".join(parts)


def row_html(e, co_of):
    """One stamped row, the page's actRow without the hovers and the doors:
    the badge and its detail, the company link, the CEO, the amount on a
    purchase or sale, the change and the stake after (sealed outside the
    S&P), the date. The script redraws it identically when the feed
    arrives."""
    k = kind_of(e)
    trade = (e.get("code") or "") in ("P", "S")
    detail = detail_of(e) if k in ("comp", "xfer", "sold") else ""
    sealed = e.get("sealed")
    val = _num(e.get("value"))
    amt = "" if not trade or not val or (e.get("price_flag") or "") else money(val)
    m = move_of(e)
    if sealed:
        change = '<span class="sealed" data-shape="−0.0%" aria-label="in Pro"></span>'
        stake = '<span class="sealed" data-shape="0.00%" aria-label="in Pro"></span>'
    else:
        change = (f'<span class="{"plus" if m[0] >= 0 else "minus"}">{stake_change(*m)}</span>' if m is not None
                  else ("unchanged" if trade and (e.get("label") or "") in COMP_LABELS else ""))
        after = _num(e.get("pct_after"))
        stake = pct(after) if after is not None else ""
    tk = e.get("tk") or (e.get("ticker") or "").upper()
    return (f'<tr class="dayrow{" dim" if dim(e) else ""}"><td class="kd"><span class="kind {k}">{KIND_WORD[k]}</span>'
            f'{"<span class=\"detail\">" + html.escape(detail) + "</span>" if detail else ""}</td>'
            f'<td class="co"><a class="pglink" href="/company/{html.escape(tk)}/">{html.escape(tk)}</a>'
            f'<span class="nm">{html.escape(co_of.get(tk, ""))}</span></td>'
            f'<td class="ceo"><span class="cn">{html.escape(e.get("ceo") or "")}</span></td>'
            f'<td class="n v">{amt}</td><td class="n ch">{change}</td><td class="n st">{stake}</td>'
            f'<td class="td"><span class="dt">{html.escape(e.get("traded") or e.get("filed") or "")}</span></td></tr>')


def table_html(rows, co_of, limit=None):
    shown = rows if limit is None else rows[:limit]
    return TAPE_HEAD + "<tbody>" + "".join(row_html(e, co_of) for e in shown) + "</tbody></table>"


def company_names(panel_p):
    out = {}
    try:
        for pr in csv.DictReader(open(panel_p, encoding="utf-8-sig")):
            out[(pr.get("ticker") or "").upper()] = pr.get("company") or ""
    except OSError:
        pass
    return out
