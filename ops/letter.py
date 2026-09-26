#!/usr/bin/env python3
"""The Monday tape: the week's letter (PLAN.md sections 5 and 5a).

    python3 ops/letter.py draft                    # weekly/letter-<today>.md and .html (the preview)
    python3 ops/letter.py draft --date 2026-09-21  # a named Monday
    python3 ops/letter.py render 2026-09-21        # re-render the .html and the archive page from the .md
    python3 ops/letter.py page 2026-09-21 public/  # the archive page, /tape/2026-09-21/, into a site folder
    python3 ops/letter.py send 2026-09-21 --test   # the rendered letter to LETTER_TEST_TO (or --to), and nobody else
    python3 ops/letter.py send 2026-09-21 --send   # the broadcast to the audience: a draft first, then the send

THE PIPELINE PREPARES; A PERSON SENDS. `draft` writes a markdown file a
person edits (any paragraph, any line) and a preview to open in a
browser. Nothing is mailed until `send` is run with --test or --send, and
--send re-renders from the markdown first so an edit is always what goes
out, then refuses if the footer still holds the postal placeholder.

WHAT THE LETTER IS. The same tape the site shows: founders only, the last
seven days, kinds in the tape's order (bought, discretionary, plan,
compensation), ranked by the stake's move within each. A weather line; a
two-line kicker (the largest open-market buy, the largest discretionary
sale); the largest of each kind in six columns; the amount on every row;
the stake after the trade sealed outside the S&P (a small "Pro" tag);
one button to /tape/; the copy rule; unsubscribe and the postal line. A
10b5-1 sale or a compensation filing is never featured.

THE LOOK IS OURS. Table-based HTML with inline styles, the site's paper
and ink, a serif headline (Georgia: mail clients do not load web fonts),
tested in Gmail, Apple Mail and Outlook before the first send.
"""
import argparse
import csv
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from fle import config as _config  # noqa: E402  (loads .env into the environment)

SITE = "https://founderledequities.com"
FROM = "Founder Led Equities <tape@founderledequities.com>"
COPY_RULE = "Every number here is computed from SEC filings; every company has a page at founderledequities.com."
POSTAL_PLACEHOLDER = "[postal address]"
# THE KINDS ARE THE PAGE'S (ops/kinds.py, 2026-09-15): the letter reads every
# filing by the founder, not purchases and sales only, and ranks by the move
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kinds  # noqa: E402
COMPENSATION = kinds.COMP_LABELS
KIND_WORD = kinds.KIND_WORD
KIND_ORDER = kinds.KIND_ORDER
KIND_COLOR = {"bought": "#1F6B3A", "disc": "#B23428", "sold": "#8C4A44", "plan": "#6E6A64", "comp": "#8C8880", "xfer": "#6E6A64"}

# the site's tokens
PAPER, INK, MUT, FAINT, LINE, LINE2 = "#F7F4EE", "#1A1A1A", "#5F5B55", "#8C8880", "#D6D1C7", "#E8E4DC"


# ---------------------------------------------------------------- helpers
def num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def money(v):
    if v is None:
        return ""
    a = abs(v)
    if a >= 1e9:
        return f"${v/1e9:.1f}B".replace(".0B", "B")
    if a >= 1e6:
        return f"${v/1e6:.1f}M".replace(".0M", "M")
    if a >= 1e3:
        return f"${v/1e3:.0f}K"
    return f"${v:,.0f}"


def pct(p, places=None):
    if p is None:
        return ""
    if places is None:
        places = 3 if abs(p) < 1 else 2
    return f"{p:.{places}f}%"


def stake_change(p):
    if p is None:
        return "stake change not stated"
    if abs(p) >= 100:
        return f"stake ×{1 + p/100:.1f}"
    return f"stake {p:+.2f}%" if abs(p) < 10 else f"stake {p:+.0f}%"


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def kind_of(e):
    return kinds.kind_of(e)


def manner_of(e, k=None):
    """The detail, capitalised: Open market, Pre-set plan, Plan not stated,
    Award granted, Gift."""
    d = kinds.detail_of(e)
    if kinds.kind_of(e) == "sold":
        return "Plan not stated"
    return d[:1].upper() + d[1:]


def nice_day(d):
    return dt.date.fromisoformat(d).strftime("%b %-d")


# ---------------------------------------------------------------- the week
def week_bounds(date):
    """(monday, friday) of the last complete week on or before `date`. EDGAR
    accepts no filings at the weekend, so a Saturday run has the whole week."""
    d = dt.date.fromisoformat(date)
    friday = d - dt.timedelta(days=(d.weekday() - 4) % 7)
    return (friday - dt.timedelta(days=4)).isoformat(), friday.isoformat()


def week_rows(root, until, days=None, founders_only=True):
    """The tape's rows for the week ending the last Friday on or before
    `until` (Monday to Friday, by filing date): every filing by a founder,
    every kind, pre-IPO rows out, with the kind, the amount, the stake
    after, whether the company is sealed, and the stake's move. Returns
    (rows, monday). `days` widens the window backwards from the Friday for
    a week that was skipped."""
    monday, friday = week_bounds(until)
    since = (dt.date.fromisoformat(friday) - dt.timedelta(days=days)).isoformat() if days else (dt.date.fromisoformat(monday) - dt.timedelta(days=1)).isoformat()
    events = read(os.path.join(root, "events.csv"))
    founders = {r["ticker"].upper(): r.get("founder", "") for r in read(os.path.join(root, "founders.csv"))}
    sp_files = sorted(f for f in os.listdir(os.path.join(root, "universe")) if f.startswith("sp500-") and f.endswith(".csv"))
    sp = {r["ticker"].upper() for r in read(os.path.join(root, "universe", sp_files[-1]))} if sp_files else set()
    rows = []
    for e in events:
        if not (since < e["filed"] <= friday) or kinds._pre(e):
            continue
        tk = e["ticker"].upper()
        if founders_only and founders.get(tk) != "yes":
            continue
        k = kind_of(e)
        m = kinds.move_of(e)
        pc = m[0] if m else None
        rows.append({
            "kind": k, "group": kinds.group_of(e), "tk": tk, "ceo": e["ceo"], "founder": founders.get(tk) == "yes",
            "sealed": tk not in sp, "value": num(e.get("value")) if (e.get("code") or "") in ("P", "S") else None,
            "flag": e.get("price_flag") or "", "after": num(e.get("pct_after")), "change": pc,
            "move": (abs(pc) if pc is not None else None), "manner": manner_of(e), "label": e.get("label") or "",
            "traded": e.get("traded") or e.get("filed"), "url": e.get("url") or "", "first": (e.get("first_buy") or "") == "1",
            "shares": (lambda sh, c, nc: (sh if c in ("P", "A", "M", "C") else -sh) if sh else (nc if nc else None))(abs(num(e.get("shares")) or 0), e.get("code") or "", num(e.get("net_change"))),
            "guarded": (e.get("code") or "") not in ("P", "S") and num(e.get("pct_after")) == 0 and num(e.get("pct_of_holding")) is not None,
        })
    return rows, monday


def weather(rows):
    """The tape's weather line, by kind, never by a figure."""
    who = lambda f: len({(r["tk"], r["ceo"]) for r in rows if f(r)})  # noqa: E731
    paid = lambda r: r["kind"] == "comp" and (r["label"] in ("award granted", "award granted, tax withheld", "options exercised", "options exercised, tax withheld", "exercise, part sold", "vested and sold"))  # noqa: E731
    first = sum(1 for r in rows if r["kind"] == "bought" and r["first"])
    parts = [f"**{who(lambda r: r['kind'] == 'bought')}** CEO{'s' if who(lambda r: r['kind'] == 'bought') != 1 else ''} bought"]
    if first:
        parts.append(f"**{first}** for the first time ever")
    parts += [f"**{who(lambda r: r['kind'] == 'disc')}** cut a stake", f"**{who(lambda r: r['kind'] == 'plan')}** sold on a plan",
              f"**{who(paid)}** paid in shares", f"**{who(lambda r: r['kind'] == 'xfer' and r['label'] == 'gift')}** gave shares away"]
    return " · ".join(parts)


def kicker(rows):
    """Two lines: the largest move of the stake, of any kind, and the largest
    open-market buy. A purchase is rare enough to earn its line whenever
    there is one; the move is the site's ranking."""
    out = []
    rows = [r for r in collapse(rows) if not r["guarded"]]
    moves = [r for r in rows if r["move"] is not None]
    if moves:
        m = max(moves, key=lambda r: r["move"])
        amt = " " + money(m["value"]) if m["value"] and not m["flag"] else ""
        did = {"bought": f"bought{amt} on the open market", "disc": f"sold{amt} at their own discretion", "plan": f"sold{amt} on a pre-set plan",
               "sold": f"sold{amt}, plan not stated"}.get(m["kind"], m["manner"].lower() + amt)
        out.append(f"Largest move: {m['ceo']}, {m['tk']}, {did} ({'stake in Pro' if m['sealed'] else stake_change(m['change'])}).")
    buys = [r for r in rows if r["kind"] == "bought" and r["value"] and not r["flag"]]
    if buys:
        b = max(buys, key=lambda r: r["value"])
        out.append(f"Largest open-market buy: {b['ceo']}, {b['tk']}, {money(b['value'])} "
                   f"({'stake in Pro' if b['sealed'] else stake_change(b['change'])}).")
    return out


def collapse(rows):
    """ONE ROW PER PERSON PER KIND. Four buys by one founder in a week are
    one line in a letter (the amounts summed, the count noted, the stake
    after the last one), not four lines that crowd out everyone else. The
    page can afford the rows; the letter cannot."""
    out, seen = [], {}
    for r in rows:
        key = (r["tk"], r["ceo"], r["kind"], r["label"] if r["kind"] in ("comp", "xfer") else "")
        if key in seen and not r["guarded"]:
            g = seen[key]
            g["n"] += 1
            if r["value"] is not None:
                g["value"] = (g["value"] or 0) + r["value"]
            if r["move"] is not None:
                g["move"] = (g["move"] or 0) + r["move"]
            if r["change"] is not None:
                g["change"] = (g["change"] or 0) + r["change"]
            if isinstance(r.get("shares"), (int, float)) and r["shares"]:
                g["shares"] = (g.get("shares") or 0) + r["shares"]
            if r["traded"] > g["traded"]:
                g["traded"], g["after"] = r["traded"], r["after"]
            g["first"] = g["first"] or r["first"]
            continue
        g = dict(r, n=1)
        seen[key] = g
        out.append(g)
    out.sort(key=lambda r: (KIND_ORDER[r["kind"]], -(r["move"] if r["move"] is not None else -1), r["traded"]))
    return out


def pick(rows, cap=12):
    """THE LARGEST MOVES OF THE WEEK, EVERY KIND, about a dozen rows, ranked
    by the move; every open-market buy is kept whatever its size (they are
    rare and the point); rows with no stated move follow, newest first.
    Sealed rows are not held back; guarded rows never make the table."""
    rows = [r for r in collapse(rows) if not r["guarded"]]
    buys = [r for r in rows if r["kind"] == "bought"]
    ranked = sorted([r for r in rows if r["move"] is not None and r not in buys], key=lambda r: -r["move"])
    rest = sorted([r for r in rows if r["move"] is None and r not in buys], key=lambda r: r["traded"], reverse=True)
    out = buys + ranked[:max(0, cap - len(buys))]
    out += rest[:max(0, cap - len(out))]
    out.sort(key=lambda r: (-(r["move"] if r["move"] is not None else -1), r["traded"]))
    return out


# ---------------------------------------------------------------- the markdown
def draft_markdown(root, date, days=None):
    """THE ISSUE'S SKELETON (settled 2026-09-20, after issue 1; six sections).
    The pipeline fills every number and leaves the writing to a person:

        # <title: the feature's claim>
        This week          two sentences: the counts; the largest move of any
                           stake, its kind named; plus a first-ever buy if there was one
        ## <the feature>   ~300 words, written by a person from the kit's brief
        ## Largest open-market buy and discretionary sale   by DOLLARS, other than the feature
        ## Top stake moves the five largest by SHARE OF THE HOLDING, any kind;
                           one bullet when a big non-decision missed the five; the link
        ## <the ranking>   three bullets from the site

    The score (log10 dollars + 2 x share of holding, +1 buy, +0.5 stake>5%)
    proposes the feature and is never mentioned in the letter."""
    rows, monday = week_rows(root, date, days)
    friday = week_bounds(date)[1]
    look = [r for r in rows if r["guarded"]]
    week = f"{nice_day(monday)} to {nice_day(friday)}"
    who_b = len({(r["tk"], r["ceo"]) for r in rows if r["kind"] == "bought"})
    who_c = len({(r["tk"], r["ceo"]) for r in rows if r["kind"] == "disc"})
    who_p = len({(r["tk"], r["ceo"]) for r in rows if r["kind"] == "plan"})
    rows_c = collapse(rows)
    decisions = [r for r in rows_c if r["kind"] in ("bought", "disc") and not r["guarded"]]
    import math as _m
    def score(r):
        v = r["value"] or 0
        return (_m.log10(v) if v > 0 else 0) + 2 * (r["move"] or 0) + (1 if r["kind"] == "bought" else 0) + (0.5 if (r["after"] or 0) >= 5 else 0)
    ranked = sorted(decisions, key=lambda r: -score(r))
    feature = ranked[0] if ranked else None
    by_dollars = sorted(decisions, key=lambda r: -(r["value"] or 0))
    top_buy = next((r for r in by_dollars if r["kind"] == "bought" and r is not feature), None)
    top_sale = next((r for r in by_dollars if r["kind"] == "disc" and r is not feature), None)
    movers = sorted([r for r in rows_c if r["move"] is not None and not r["guarded"]], key=lambda r: -(r["move"] or 0))[:5]
    big_other = sorted([r for r in rows_c if r["kind"] not in ("bought", "disc") and (r["value"] or 0) >= 50e6 and r not in movers], key=lambda r: -(r["value"] or 0))
    firsts = [r for r in rows_c if r["kind"] == "bought" and r.get("first")]

    def decision_par(r, label):
        verb = "bought" if r["kind"] == "bought" else "sold"
        amt = money(r["value"]) if r["value"] else "shares"
        mv = f"{r['move']:.2f}% of the holding" if r["move"] is not None else "the move unstated"
        return (f"**{label}.** *{r['ceo']} {verb} {amt} of {r['tk']}* {'on the open market' if r['kind'] == 'bought' else 'at their own discretion'}"
                f"{' across ' + str(r['n']) + ' filings' if r.get('n', 1) > 1 else ''}: {mv}. [one fact from the history: buys and sales in two years, plan or not] Owns {pct(r['after'])}.")
    def row(r):
        amt = money(r["value"]) if r["value"] and not r["flag"] else "—"
        mv = (f"{r['change']:+.2f}%" if r["change"] is not None else "—")
        return f"| {KIND_WORD[r['kind']]} | {r['tk']} | {r['ceo']} | {amt} | {mv} | {pct(r['after']) or '—'} |"

    title = (f"{feature['ceo'].split()[-1]} {'buys' if feature['kind'] == 'bought' else 'sells'} {money(feature['value']) if feature['value'] else 'shares'} of {feature['tk']}"
             if feature else f"This week: {who_b} CEO{'s' if who_b != 1 else ''} bought, {who_c} cut a stake")
    top = movers[0] if movers else None
    this_week = (f"{who_b} founder{'s' if who_b != 1 else ''} bought on the open market this week; {who_c} sold at their own discretion; {who_p} sold on plans set months ago.")
    if top:
        this_week += f" The largest move of any stake was {top['ceo']}'s: {top['move']:.1f}% of the {top['tk']} holding, {top['manner'].lower()}."
    for r in firsts:
        this_week += f" One first: {r['ceo']} bought {r['tk']} on the open market for the first time on record."
    lines = ["---", f"date: {date}", f"title: {title}", f"week: {week}", f"featured: {feature['tk'] if feature else ''}", "---", "",
             f"# {title}", "", f"*Founder Moves · the week of {week}*", "", this_week, ""]
    lines += [f"## [The feature: {feature['ceo'] + ' of ' + feature['tk'] if feature else 'no decision this week; the largest move from Top stake moves'}]", "",
              "[About 300 words, in your words, from the kit's brief: what the company does; what the person has done before with the stake; what the filings say that the Form 4 doesn't; what this move changed. The ticker on first mention. Numbers from the site only.]", "",
              f"![the stake, the last twelve months](https://founderledequities.com/og/{feature['tk'] if feature else 'TICKER'}.png)", ""]
    lines += ["## Largest open-market buy and discretionary sale", ""]
    if top_buy:
        lines += [decision_par(top_buy, "The largest buy"), ""]
    else:
        lines += ["**The largest buy.** No founder bought on the open market this week" + (" other than the feature." if feature and feature["kind"] == "bought" else "."), ""]
    if top_sale:
        lines += [decision_par(top_sale, "The largest sale"), ""]
    lines += ["## Top stake moves", "", "The five largest changes to a founder's stake this week, as a share of the holding, whatever the kind.", "",
              "| Kind | Company | CEO | Amount | Of holding | Stake |", "|---|---|---|---|---|---|"]
    lines += [row(r) for r in movers]
    lines += [""]
    if big_other:
        r = big_other[0]
        lines += [f"- **{r['ceo']} {r['manner'].lower()} {money(r['value'])} of {r['tk']}**: {r['label'] or r['manner']}, {abs(r['move'] or 0):.2f}% of the holding. Owns {pct(r['after'])}.", ""]
    lines += [f"[Every filing of the week, on the site.]({SITE}/tape/)", "",
              "## [The ranking: what it ranks]", "", "- [three bullets from the site's data, and the link to the screen]", ""]
    if look:
        lines += ["", "NEEDS A LOOK BEFORE THE SEND (not in the tables): " + "; ".join(f"{r['ceo']}, {r['tk']}: {r['manner'].lower()} took the position on record to zero" for r in look) + "."]
    return "\n".join(lines)


# ---------------------------------------------------------------- markdown -> letter
def parse(md):
    """The little markdown the letter uses: front matter, one # title, a
    subhead line, paragraphs, **bold**, [text](url), one table."""
    meta, body = {}, md
    if md.startswith("---"):
        end = md.index("\n---", 3)
        for l in md[3:end].strip().split("\n"):
            if ":" in l:
                k, v = l.split(":", 1)
                meta[k.strip()] = v.strip()
        body = md[end + 4:]
    blocks, table, para, items = [], [], [], []
    def flush():
        nonlocal para, table, items
        if table:
            blocks.append(("table", table)); table = []
        if items:
            blocks.append(("ul", items)); items = []
        if para:
            blocks.append(("p", " ".join(para))); para = []
    for l in body.split("\n"):
        s = l.rstrip()
        if s.startswith("|"):
            if para:
                blocks.append(("p", " ".join(para))); para = []
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                continue
            table.append(cells); continue
        if table:
            blocks.append(("table", table)); table = []
        if not s:
            if para:
                blocks.append(("p", " ".join(para))); para = []
            continue
        if s.startswith("- ") or s.startswith("* "):
            if para:
                blocks.append(("p", " ".join(para))); para = []
            items.append(s[2:].strip()); continue
        if items and not s.startswith(("- ", "* ")):
            blocks.append(("ul", items)); items = []
        if s.startswith("# "):
            flush(); blocks.append(("h1", s[2:].strip())); continue
        if s.startswith("## "):
            flush(); blocks.append(("h2", s[3:].strip())); continue
        m_img = re.fullmatch(r"!\[([^\]]*)\]\(([^)]+)\)", s.strip())
        if m_img:
            flush(); blocks.append(("img", (m_img.group(1), m_img.group(2)))); continue
        if s.strip() == "---members---":
            # a rule in old issues (the paid part, retired 2026-09-23):
            # rendered as a divider, everything below open to everyone
            flush(); blocks.append(("members", "")); continue
        para.append(s)
    flush()
    return meta, blocks


def inline(text, for_html=True):
    t = html.escape(text) if for_html else text
    if for_html:
        t = re.sub(r"\*\*(.+?)\*\*", r"<b style=\"color:%s\">\1</b>" % INK, t)
        t = re.sub(r"(?<![*\w])\*(?!\*)([^*\n]+?)\*(?!\*)", r"<i>\1</i>", t)
        t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" style="color:%s">\1</a>' % INK, t)
    else:
        t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
        t = re.sub(r"(?<![*\w])\*(?!\*)([^*\n]+?)\*(?!\*)", r"\1", t)
        t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", t)
    return t


def render(md, unsubscribe_url="{{{RESEND_UNSUBSCRIBE_URL}}}", postal=None):
    """-> (html, text, meta). The letter in the site's look."""
    meta, blocks = parse(md)
    postal = postal or os.environ.get("POSTAL_ADDRESS") or POSTAL_PLACEHOLDER
    date_line = dt.date.fromisoformat(meta.get("date", dt.date.today().isoformat())).strftime("%A, %B %-d, %Y")
    H, T = [], []
    subject = meta.get("title") or meta.get("subject") or "This week"
    H.append(f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{html.escape(subject)}</title></head>'
             f'<body style="margin:0;padding:0;background:#ECE9E2;">'
             f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#ECE9E2;"><tr><td align="center" style="padding:20px 10px;">'
             f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:{PAPER};font-family:Helvetica,Arial,sans-serif;color:{INK};">'
             f'<tr><td style="padding:28px 28px 0;">'
             f'<table role="presentation" width="100%"><tr><td style="font-family:Menlo,Consolas,monospace;font-size:10px;letter-spacing:.14em;color:{FAINT};">FOUNDER LED EQUITIES</td>'
             f'<td align="right" style="font-family:Menlo,Consolas,monospace;font-size:10px;color:{FAINT};">{date_line}</td></tr></table>')
    T.append(f"FOUNDER LED EQUITIES · {date_line}\n")
    first_p = True
    for kind, val in blocks:
        if kind == "h1":
            H.append(f'<h1 style="font-family:Georgia,\'Times New Roman\',serif;font-weight:normal;font-size:34px;line-height:1.1;margin:22px 0 6px;color:{INK};">{inline(val)}</h1>')
            T.append(val.upper() + "\n")
        elif kind == "h2":
            H.append(f'<h2 style="font-family:Georgia,\'Times New Roman\',serif;font-weight:normal;font-size:22px;line-height:1.2;margin:24px 0 8px;color:{INK};">{inline(val)}</h2>')
            T.append("\n" + val.upper() + "\n")
        elif kind == "img":
            alt, src = val
            H.append(f'<img src="{html.escape(src)}" alt="{html.escape(alt)}" width="544" style="display:block;width:100%;max-width:544px;height:auto;margin:6px 0 14px;border:1px solid {LINE2};">')
            T.append(f"[{alt}: {src}]\n")
        elif kind == "members":
            H.append(f'<div style="border-top:1px solid {LINE};margin:14px 0;"></div>')
        elif kind == "ul":
            H.append('<ul style="margin:0 0 14px 18px;padding:0;">' + "".join(f'<li style="font-size:14px;line-height:1.5;color:{INK};margin:0 0 6px;">{inline(x)}</li>' for x in val) + "</ul>")
            T.extend("  - " + inline(x, False) for x in val); T.append("")
        elif kind == "p":
            if first_p:
                H.append(f'<p style="font-size:14px;color:{MUT};margin:0 0 18px;">{inline(val)}</p>'
                         f'<div style="border-top:1px solid {INK};margin:0 0 16px;"></div>')
                first_p = False
            elif val.startswith("**"):
                H.append(f'<p style="font-size:14px;color:{MUT};margin:0 0 18px;">{inline(val)}</p>')
            elif val.startswith("[See all activity]"):
                m = re.search(r"\((.+?)\)", val)
                H.append(f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:10px 0 22px;"><tr><td style="background:{INK};">'
                         f'<a href="{html.escape(m.group(1))}" style="display:inline-block;padding:11px 22px;color:{PAPER};font-size:14px;font-weight:bold;text-decoration:none;">See all activity &rarr;</a></td></tr></table>')
            else:
                H.append(f'<p style="font-size:14px;line-height:1.5;color:{INK};margin:0 0 12px;">{inline(val)}</p>')
            T.append(inline(val, False) + "\n")
        elif kind == "table":
            head, body = val[0], val[1:]
            H.append('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin:6px 0 10px;">')
            H.append("<tr>" + "".join(
                f'<th align="{"right" if h in ("Amount","Change","New stake") else "left"}" style="font-size:11px;font-weight:bold;letter-spacing:.06em;text-transform:uppercase;color:{INK};padding:0 6px 8px 0;border-bottom:1px solid {INK};white-space:nowrap;">{html.escape(h)}</th>'
                for h in head) + "</tr>")
            for cells in body:
                k = {"Bought": "bought", "Discretionary": "disc", "Planned": "plan", "Plan": "plan", "Sold": "sold", "Compensation": "comp", "Transfer": "xfer"}.get(cells[0], "plan")
                col = INK
                tds = []
                for i, c in enumerate(cells):
                    h = head[i] if i < len(head) else ""
                    if i == 0:
                        tds.append(f'<td style="padding:8px 6px 8px 0;border-top:1px solid {LINE2};font-size:12px;font-weight:bold;color:{KIND_COLOR[k]};white-space:nowrap;">{html.escape(c)}</td>')

                    elif h in ("Amount", "Change", "New stake"):
                        tds.append(f'<td align="right" style="padding:8px 6px 8px 0;border-top:1px solid {LINE2};font-family:Menlo,Consolas,monospace;font-size:12px;color:{col};white-space:nowrap;">{html.escape(c)}</td>')
                    elif h == "Company":
                        tds.append(f'<td style="padding:8px 6px 8px 0;border-top:1px solid {LINE2};font-size:13px;font-weight:bold;color:{col};"><a href="{SITE}/company/{html.escape(c)}/" style="color:{col};text-decoration:none;">{html.escape(c)}</a></td>')
                    elif h == "Manner":
                        tds.append(f'<td style="padding:8px 0 8px 0;border-top:1px solid {LINE2};font-size:12px;color:{MUT};white-space:nowrap;">{html.escape(c)}</td>')
                    else:
                        tds.append(f'<td style="padding:8px 6px 8px 0;border-top:1px solid {LINE2};font-size:13px;color:{col};white-space:nowrap;">{html.escape(c)}</td>')
                H.append("<tr>" + "".join(tds) + "</tr>")
            H.append("</table>")
            widths = [max(len(r[i]) for r in val) for i in range(len(head))]
            for r in val:
                T.append("  ".join(c.ljust(widths[i]) for i, c in enumerate(r)))
            T.append("")
    unsub = html.escape(unsubscribe_url)
    H.append(f'<div style="border-top:1px solid {LINE};margin:8px 0 14px;"></div>'
             f'<p style="font-size:11px;line-height:1.5;color:{MUT};margin:0 0 10px;">{html.escape(COPY_RULE)} Nothing here is investment advice.</p>'
             f'<p style="font-size:11px;line-height:1.5;color:{MUT};margin:0 0 28px;">You asked for this on founderledequities.com &middot; '
             f'<a href="{unsub}" style="color:{MUT};">Unsubscribe</a> &middot; Founder Led Equities</p>'
             f'</td></tr></table></td></tr></table></body></html>')
    T.append(f"\n{COPY_RULE} Nothing here is investment advice.\n"
             f"You asked for this on founderledequities.com. Unsubscribe: {unsubscribe_url}\nFounder Led Equities\n")
    return "\n".join(H), "\n".join(T), meta


def archive_page(md, topnav, css_href="/site.css"):
    """The letter as a page of the site: /letter/<date>/ (2026-09-20; the
    old /tape/<date>/ address redirects there). The same blocks the email
    renders, in the site's shell; a ---members--- marker in an old issue
    renders as a divider (everything is open, 2026-09-23)."""
    meta, blocks = parse(md)
    body = []
    for kind, val in blocks:
        if kind == "members":
            body.append('<div class="lrule"></div>')   # old issues keep their divider; everything is open
            continue
        if kind == "h1":
            body.append(f'<h1 class="lt">{inline(val)}</h1>')
        elif kind == "h2":
            body.append(f'<h2 class="lh2">{inline(val)}</h2>')
        elif kind == "img":
            alt, src = val
            body.append(f'<figure class="lfig"><img src="{html.escape(src)}" alt="{html.escape(alt)}" loading="lazy"></figure>')
        elif kind == "ul":
            body.append('<ul class="lul">' + "".join(f"<li>{inline(x)}</li>" for x in val) + "</ul>")
        elif kind == "p":
            if val.startswith("[See all activity]"):
                body.append('<p><a class="exit" href="/tape/">All activity &rarr;</a></p>')
            else:
                body.append(f'<p class="lp">{inline(val)}</p>')
        elif kind == "table":
            head, rows = val[0], val[1:]
            body.append('<table class="ltable"><thead><tr>' + "".join(f'<th{" class=\"n\"" if h in ("Amount","Change","New stake","Stake","Shares") else ""}>{html.escape(h)}</th>' for h in head) + "</tr></thead><tbody>")
            for cells in rows:
                k = {"Bought": "bought", "Discretionary": "disc", "Planned": "plan", "Plan": "plan", "Sold": "sold", "Compensation": "comp", "Transfer": "xfer"}.get(cells[0], "")
                tds = []
                for i_, c in enumerate(cells):
                    h = head[i_] if i_ < len(head) else ""
                    if i_ == 0 and k:
                        tds.append(f'<td><span class="kind {k}">{html.escape(c)}</span></td>')
                    elif h in ("Amount", "Change", "New stake", "Stake", "Shares"):
                        tds.append(f'<td class="n">{html.escape(c)}</td>')
                    elif h == "Company" and re.fullmatch(r"[A-Z0-9.\-]{1,8}", c):
                        tds.append(f'<td><a class="pglink" href="/company/{html.escape(c)}/"><b>{html.escape(c)}</b></a></td>')
                    else:
                        tds.append(f'<td>{inline(c)}</td>')
                body.append("<tr>" + "".join(tds) + "</tr>")
            body.append("</tbody></table>")
    date = meta.get("date", "")
    title = meta.get("title") or meta.get("subject") or "This week"
    featured = (meta.get("featured") or "").strip().upper()
    og = f"{SITE}/og/{featured}.png" if featured else f"{SITE}/og.png"
    desc = meta.get("description") or f"The week of {meta.get('week','')}: who bought, who cut a stake, who sold on a plan. Founders first."

    try:
        nice = dt.date.fromisoformat(date).strftime("%B %-d, %Y") if date else ""
    except ValueError:
        nice = date
    kick_feat = f' · <a href="/company/{html.escape(featured)}/">{html.escape(featured)}</a>' if featured else ""
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)} · Founder Led Equities</title>'
            f'<meta name="description" content="{html.escape(desc[:300])}">'
            f'<link rel="canonical" href="{SITE}/letter/{date}/">'
            f'<meta property="og:title" content="{html.escape(title)}"><meta property="og:description" content="{html.escape(desc[:300])}">'
            f'<meta property="og:image" content="{og}"><meta name="twitter:card" content="summary_large_image">'
            f'<link rel="stylesheet" href="{css_href}">'
            f'<style>{LETTER_CSS}</style></head><body>'
            f'{topnav}<main class="letter"><div class="lcol"><div class="lkick"><a href="/letter/">Founder Moves</a> · {html.escape(nice)}{kick_feat}</div>'
            f'<div class="lfree">' + "\n".join(body) + "</div>" +
            f'<div class="lfoot">{html.escape(COPY_RULE)} Nothing here is investment advice. <a href="/letter/">Every issue &rarr;</a></div></div></main></body></html>')


LETTER_CSS = """
.letter{max-width:var(--max);margin:0 auto;padding:clamp(28px,4vw,52px) clamp(20px,3.5vw,48px) 72px}
.letter .lcol{max-width:720px}   /* ONE READING COLUMN (2026-09-20): text, image and tables the same width; the site's column holds the nav, the issue sits in its left 720px */
.letter .lkick{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);margin-bottom:14px}
.letter .lkick a{color:var(--mut);text-decoration:none}
.letter h1.lt{font-family:var(--disp);font-weight:500;letter-spacing:-.02em;line-height:1.08;font-size:clamp(30px,3.6vw,44px);margin:0 0 14px}
.letter h2.lh2{font-family:var(--disp);font-weight:500;letter-spacing:-.01em;font-size:clamp(21px,2.2vw,26px);margin:32px 0 10px}
.letter p.lp{font-size:16px;line-height:1.6;color:var(--ink);margin:0 0 14px}
.letter ul.lul{margin:0 0 16px 20px;padding:0}.letter ul.lul li{font-size:16px;line-height:1.6;margin:0 0 8px}
.letter figure.lfig{margin:16px 0 22px}.letter figure.lfig img{display:block;width:100%;height:auto;border:1px solid var(--line)}
.letter table.ltable{border-collapse:collapse;font-size:13.5px;margin:8px 0 18px;font-variant-numeric:tabular-nums;width:100%}
.letter table.ltable th{text-align:left;font-family:var(--ui);font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ink);padding:0 12px 8px 0;border-bottom:1px solid var(--ink)}
.letter table.ltable td{padding:8px 10px 8px 0;border-bottom:1px solid var(--line);vertical-align:top}
.letter table.ltable th.n,.letter table.ltable td.n{text-align:right;white-space:nowrap}
.letter table.ltable th:last-child,.letter table.ltable td:last-child{padding-right:0}
.letter .lrule{border-top:1px solid var(--line);margin:14px 0}
.letter .lfoot{border-top:1px solid var(--line);margin-top:40px;padding:16px 0 0;font-size:12.5px;color:var(--mut)}
.lindex{max-width:var(--max);margin:0 auto;padding:clamp(28px,4vw,52px) clamp(20px,3.5vw,48px) 72px}
.lindex .lcol{max-width:720px}
.lindex h1{font-family:var(--disp);font-weight:500;letter-spacing:-.02em;line-height:1.05;font-size:clamp(34px,4.6vw,56px);margin:0 0 8px}
.lindex .sub{font-size:15.5px;color:var(--mut);margin:0 0 22px;max-width:72ch}
.lindex .lsub{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 34px;font-size:14px}
.lindex .lsub label{color:var(--mut)}
.lindex .lsub input{font:inherit;font-size:14px;padding:8px 10px;border:1px solid var(--line);background:var(--bg);color:var(--ink);width:min(280px,100%)}
.lindex .lsub button{font:inherit;font-size:13px;font-weight:600;padding:9px 14px;border:1px solid var(--ink);background:var(--ink);color:var(--bg);cursor:pointer}
.lindex .lsub .lmsg{font-size:13px;color:var(--mut)}
.lindex .issues{border-top:1px solid var(--ink)}
.lindex .issue{display:grid;grid-template-columns:120px 1fr;gap:14px;padding:16px 0;border-bottom:1px solid var(--line);align-items:baseline}
.lindex .issue .d{font-family:var(--mono);font-size:12px;color:var(--faint)}
.lindex .issue a{font-family:var(--disp);font-size:22px;color:var(--ink);text-decoration:none}
.lindex .issue a:hover{text-decoration:underline}
.lindex .issue .w{font-size:13px;color:var(--mut);margin-top:2px}
"""


def index_page(issues, topnav, css_href="/site.css", signup_html=""):
    """/letter/: the issues as a list with a rule between them, newest first,
    and a quiet signup line at the top (the field and the button in the
    page's own type, no band). No day of the week anywhere: the letter is
    weekly, and the dates below say when it came."""
    rows = []
    for meta in issues:
        d = meta.get("date", "")
        try:
            nice = dt.date.fromisoformat(d).strftime("%b %-d, %Y")
        except ValueError:
            nice = d
        title = meta.get("title") or meta.get("subject") or "This week"
        feat = (meta.get("featured") or "").strip().upper()
        rows.append(f'<div class="issue"><div class="d">{html.escape(nice)}</div><div><a href="/letter/{html.escape(d)}/">{html.escape(title)}</a>'
                    f'<div class="w">{html.escape("the week of " + meta["week"] if meta.get("week") else "")}{(" · " + html.escape(feat)) if feat else ""}</div></div></div>')
    signup = ('<form class="lsub" id="lsub" onsubmit="return subscribeLetter(event)">'
              '<label for="lemail">Get it by email</label>'
              '<input type="email" id="lemail" placeholder="you@example.com" required autocomplete="email">'
              '<button type="submit">Subscribe</button><span class="lmsg" id="lmsg"></span></form>'
              '<script>async function subscribeLetter(ev){ev.preventDefault();const email=(document.getElementById("lemail").value||"").trim(),m=document.getElementById("lmsg"),btn=document.querySelector("#lsub button");'
              'if(!email||btn.disabled)return false;btn.disabled=true;btn.textContent="Sending…";'
              'try{const q=await fetch("/api/subscribe",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email})});const j=await q.json();'
              'm.textContent=j.message||"Check your inbox: one click confirms it.";if(j.ok){document.getElementById("lemail").disabled=true;btn.textContent="Sent";}else{btn.disabled=false;btn.textContent="Subscribe";}}'
              'catch(e){m.textContent="Something went wrong; write to hello@founderledequities.com.";btn.disabled=false;btn.textContent="Subscribe";}return false;}</script>')
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>Founder Moves, the letter · Founder Led Equities</title>'
            f'<meta name="description" content="Every issue of Founder Moves: what chief executives did with their own stakes each week. Free.">'
            f'<link rel="canonical" href="{SITE}/letter/"><link rel="stylesheet" href="{css_href}"><style>{LETTER_CSS}</style></head><body>'
            f'{topnav}<main class="lindex"><div class="lcol"><h1>Founder Moves</h1><p class="sub">What chief executives did with their own stakes this week.</p>'
            f'{signup}<div class="issues">' + "\n".join(rows) + "</div>"
            f'<div class="lfoot" style="border-top:1px solid var(--line);margin-top:40px;padding:16px 0 0;font-size:12.5px;color:var(--mut)">Nothing here is investment advice.</div></div></main></body></html>')


def resend(path, payload, key):
    """-> (status, body). The body is parsed as JSON when it is JSON, and
    returned as text otherwise, so an error is shown rather than swallowed."""
    req = urllib.request.Request(f"https://api.resend.com{path}", data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "User-Agent": "founderledequities-letter/1"}, method="POST")
    def body_of(raw):
        txt = raw.decode(errors="replace")
        try:
            return json.loads(txt) if txt.strip() else {}
        except ValueError:
            return {"raw": txt[:600]}
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, body_of(r.read())
    except urllib.error.HTTPError as e:
        return e.code, body_of(e.read())
    except urllib.error.URLError as e:
        return 0, {"raw": f"no connection: {e.reason}"}


def list_target():
    """Who a broadcast goes to, from .env: RESEND_SEGMENT_ID (a segment
    defined as every subscribed contact, so a new signup joins it by
    itself), or RESEND_AUDIENCE_ID. A list send never guesses. Resend's
    legacy "General" audience is an empty segment now; the account's
    contacts are addressed through a segment that means everyone."""
    seg = os.environ.get("RESEND_SEGMENT_ID", "").strip()
    if seg:
        return {"segment_id": seg}
    aud = os.environ.get("RESEND_AUDIENCE_ID", "").strip()
    if aud:
        return {"audience_id": aud}
    return {}


def paths(root, date):
    d = os.path.join(root, "weekly")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"letter-{date}.md"), os.path.join(d, f"letter-{date}.html")


def cmd_draft(a):
    date = a.date or dt.date.today().isoformat()
    md_p, html_p = paths(a.root, date)
    if os.path.exists(md_p) and not a.force:
        print(f"  {md_p} exists; edit it, or --force to redraft from the data")
    else:
        open(md_p, "w", encoding="utf-8").write(draft_markdown(a.root, date, a.days))
        print(f"  drafted {md_p}")
    return cmd_render(argparse.Namespace(root=a.root, date=date))


def cmd_render(a):
    md_p, html_p = paths(a.root, a.date)
    md = open(md_p, encoding="utf-8").read()
    h, t, meta = render(md, unsubscribe_url="#unsubscribe")
    open(html_p, "w", encoding="utf-8").write(h)
    print(f"  preview {html_p}  (open it in a browser)  subject: {meta.get('title') or meta.get('subject','')}")
    return 0


def mark_sent(root, date):
    """AN ISSUE IS AN ISSUE ONCE IT IS SENT (2026-09-20). The confirmed send
    stamps `sent: <today>` into the file's front matter; the publisher and
    the kit's voice folder take only stamped files. A draft the pipeline
    wrote and nobody sent never becomes a page."""
    md_p, _ = paths(root, date)
    md = open(md_p, encoding="utf-8").read()
    if re.search(r"^sent:", md, re.M):
        return
    stamp = f"sent: {dt.date.today().isoformat()}\n"
    if md.startswith("---"):
        end = md.index("\n---", 3)
        md = md[:end + 1] + stamp + md[end + 1:]
    else:
        md = f"---\n{stamp}---\n" + md
    open(md_p, "w", encoding="utf-8").write(md)
    print(f"  {md_p}: stamped as sent")


def is_sent(md_path):
    try:
        head = open(md_path, encoding="utf-8").read(2000)
    except OSError:
        return False
    return bool(re.search(r"^sent:\s*\S", head, re.M))


def _shell(root, out):
    sys.path.insert(0, HERE)
    import build_company_pages as bcp  # noqa: E402
    idx = open(os.path.join(root, "index.html"), encoding="utf-8").read()
    topnav = bcp.extract_topnav(idx)
    css = "/site.css"
    try:
        css_text = open(os.path.join(out, "site.css"), encoding="utf-8").read()
        import hashlib
        css = f"/site.css?v={hashlib.sha256(css_text.encode()).hexdigest()[:10]}"
    except OSError:
        pass
    return topnav, css


def write_issue(root, out, date, topnav, css):
    md_p, _ = paths(root, date)
    md = open(md_p, encoding="utf-8").read()
    d = os.path.join(out, "letter", date)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(archive_page(md, topnav, css))
    # the old address, /tape/<date>/, sends a reader on
    old = os.path.join(out, "tape", date)
    os.makedirs(old, exist_ok=True)
    open(os.path.join(old, "index.html"), "w", encoding="utf-8").write(
        f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=/letter/{date}/"><link rel="canonical" href="{SITE}/letter/{date}/"><a href="/letter/{date}/">/letter/{date}/</a>')
    return parse(md)[0]


def cmd_page(a):
    topnav, css = _shell(a.root, a.out)
    write_issue(a.root, a.out, a.date, topnav, css)
    print(f"  letter page {a.out}/letter/{a.date}/index.html")
    return 0


def cmd_publish(a):
    """Every issue in weekly/ as a page, and the index at /letter/."""
    import glob
    topnav, css = _shell(a.root, a.out)
    issues = []
    for p in sorted(glob.glob(os.path.join(a.root, "weekly", "letter-*.md"))):
        if not is_sent(p):
            continue      # a draft is not an issue
        date = os.path.basename(p)[len("letter-"):-len(".md")]
        try:
            issues.append(write_issue(a.root, a.out, date, topnav, css))
        except Exception as e:  # noqa: BLE001
            print(f"  letter {date}: not published ({e})")
    issues.sort(key=lambda m: m.get("date", ""), reverse=True)
    signup = ""
    d = os.path.join(a.out, "letter")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(index_page(issues, topnav, css, signup))
    with open(os.path.join(d, "issues.json"), "w", encoding="utf-8") as fh:
        json.dump([{"date": m.get("date", ""), "title": m.get("title") or m.get("subject", ""), "featured": m.get("featured", "")} for m in issues], fh)
    print(f"  letter: {len(issues)} issue(s) published at /letter/, index written")
    return 0


def cmd_send(a):
    key = os.environ.get("RESEND_API_KEY")
    if not key:
        print("RESEND_API_KEY is not set (.env)"); return 2
    md_p, html_p = paths(a.root, a.date)
    md = open(md_p, encoding="utf-8").read()
    postal = os.environ.get("POSTAL_ADDRESS")
    if a.test:
        to = a.to or os.environ.get("LETTER_TEST_TO")
        if not to:
            print("--to or LETTER_TEST_TO (.env) is needed for a test send"); return 2
        h, t, meta = render(md, unsubscribe_url=f"{SITE}/tape/#unsubscribe", postal=postal)
        status, body = resend("/emails", {"from": FROM, "to": [to], "subject": f"[test] {meta.get('title') or meta.get('subject') or 'This week'}",
                                          "html": h, "text": t}, key)
        print(f"  test send to {to}: {status} {body}")
        return 0 if status < 300 else 1
    if a.send:
        if not postal:
            print("refusing: POSTAL_ADDRESS is not set (.env); a list email must carry a postal line"); return 2
        h, t, meta = render(md, postal=postal)   # the unsubscribe placeholder Resend fills per recipient
        target = list_target()
        if not target:
            print("refusing: RESEND_SEGMENT_ID is not set (.env); create a segment meaning every subscribed contact on Resend's Audience page and put its id there")
            return 2
        payload = {"from": FROM, "subject": meta.get("title") or meta.get("subject") or "This week", "html": h, "text": t,
                   "name": f"Monday tape {a.date}", **target}
        status, body = resend("/broadcasts", payload, key)
        print(f"  broadcast draft: {status} {body}")
        if status >= 300 or not body.get("id"):
            return 1
        if not a.confirm:
            print(f"  drafted, not sent. Review it at https://resend.com/broadcasts/{body['id']} and press Send there,"
                  f" or run again with --send --confirm to send it from here.")
            return 0
        status, body2 = resend(f"/broadcasts/{body['id']}/send", {}, key)
        print(f"  sent: {status} {body2}")
        if status < 300:
            mark_sent(a.root, a.date)
        return 0 if status < 300 else 1
    print("send needs --test or --send"); return 2


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=ROOT)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draft"); d.add_argument("--date"); d.add_argument("--days", type=int, default=7); d.add_argument("--force", action="store_true")
    r = sub.add_parser("render"); r.add_argument("date")
    p = sub.add_parser("page"); p.add_argument("date"); p.add_argument("out")
    pb = sub.add_parser("publish"); pb.add_argument("out")
    s = sub.add_parser("send"); s.add_argument("date"); s.add_argument("--test", action="store_true"); s.add_argument("--send", action="store_true")
    s.add_argument("--confirm", action="store_true"); s.add_argument("--to")
    a = ap.parse_args()
    return {"draft": cmd_draft, "render": cmd_render, "page": cmd_page, "publish": cmd_publish, "send": cmd_send}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
