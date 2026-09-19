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
COPY_RULE = ("This letter is free and always will be. Members keep it that way, and get these moves "
             "by email as they are filed. $69 a year: founderledequities.com/pro/")
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
    rows, monday = week_rows(root, date, days)
    friday = week_bounds(date)[1]
    shown = pick(rows)
    sealed_n = sum(1 for r in shown if r["sealed"])
    look = [r for r in rows if r["guarded"]]
    week = f"{nice_day(monday)} to {nice_day(friday)}"
    who_b = len({(r["tk"], r["ceo"]) for r in rows if r["kind"] == "bought"})
    who_c = len({(r["tk"], r["ceo"]) for r in rows if r["kind"] == "disc"})
    lines = [
        "---",
        f"date: {date}",
        f"subject: This week's tape: {who_b} CEO{'s' if who_b != 1 else ''} bought, {who_c} cut a stake",
        f"week: {week}",
        "---",
        "",
        "# This week's tape.",
        "",
        f"Founders only · {week} · the largest moves of the stake, every kind",
        "",
        weather(rows),
        "",
    ]
    for k in kicker(rows):
        lines += [k, ""]          # each kicker line is its own paragraph
    lines += ["| Kind | Company | CEO | Amount | Change | New stake | Manner |", "|---|---|---|---|---|---|---|"]
    for r in shown:
        amount = money(r["value"]) if r["value"] and not r["flag"] else "—"
        change = "Pro" if r["sealed"] else (stake_change(r["change"]).replace("stake ", "") if r["change"] is not None else "—")
        stake = "Pro" if r["sealed"] else (pct(r["after"]) or "—")
        ceo = r["ceo"] + (" (first buy)" if r["first"] else "")
        manner = r["manner"] + (f" · {r['n']} filings" if r.get("n", 1) > 1 else "")
        lines.append(f"| {KIND_WORD[r['kind']]} | {r['tk']} | {ceo} | {amount} | {change} | {stake} | {manner} |")
    lines += [
        "",
        f"{len(rows)} filings this week · shown here: the largest moves of the stake, every open-market buy among them"
        + (f" · the change and the stake after are in Pro for the {sealed_n} from companies outside the S&P 500" if sealed_n else "") + ".",
        "",
        f"[Read the full tape]({SITE}/tape/)",
        "",
    ]
    if look:
        lines += ["NEEDS A LOOK BEFORE THE SEND (not in the table): " + "; ".join(f"{r['ceo']}, {r['tk']}: {r['manner'].lower()} took the position on record to zero" for r in look) + ".", ""]
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
    blocks, table, para = [], [], []
    def flush():
        nonlocal para, table
        if table:
            blocks.append(("table", table)); table = []
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
        if s.startswith("# "):
            flush(); blocks.append(("h1", s[2:].strip())); continue
        para.append(s)
    flush()
    return meta, blocks


def inline(text, for_html=True):
    t = html.escape(text) if for_html else text
    if for_html:
        t = re.sub(r"\*\*(.+?)\*\*", r"<b style=\"color:%s\">\1</b>" % INK, t)
        t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" style="color:%s">\1</a>' % INK, t)
    else:
        t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
        t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", t)
    return t


def render(md, unsubscribe_url="{{{RESEND_UNSUBSCRIBE_URL}}}", postal=None):
    """-> (html, text, meta). The letter in the site's look."""
    meta, blocks = parse(md)
    postal = postal or os.environ.get("POSTAL_ADDRESS") or POSTAL_PLACEHOLDER
    date_line = dt.date.fromisoformat(meta.get("date", dt.date.today().isoformat())).strftime("%A, %B %-d, %Y")
    H, T = [], []
    H.append(f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{html.escape(meta.get("subject","This week\'s tape"))}</title></head>'
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
        elif kind == "p":
            if first_p:
                H.append(f'<p style="font-size:14px;color:{MUT};margin:0 0 18px;">{inline(val)}</p>'
                         f'<div style="border-top:1px solid {INK};margin:0 0 16px;"></div>')
                first_p = False
            elif val.startswith("**"):
                H.append(f'<p style="font-size:14px;color:{MUT};margin:0 0 18px;">{inline(val)}</p>')
            elif val.startswith("[Read the full tape]"):
                m = re.search(r"\((.+?)\)", val)
                H.append(f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:10px 0 22px;"><tr><td style="background:{INK};">'
                         f'<a href="{html.escape(m.group(1))}" style="display:inline-block;padding:11px 22px;color:{PAPER};font-size:14px;font-weight:bold;text-decoration:none;">Read the full tape &rarr;</a></td></tr></table>')
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
                    elif h in ("New stake", "Change") and c == "Pro":
                        tds.append(f'<td align="right" style="padding:8px 6px 8px 0;border-top:1px solid {LINE2};"><a href="{SITE}/#pro" style="display:inline-block;font-size:9px;font-weight:bold;letter-spacing:.06em;color:{FAINT};border:1px solid {LINE};padding:1px 6px;text-decoration:none;">Pro</a></td>')
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
             f'<a href="{unsub}" style="color:{MUT};">Unsubscribe</a> &middot; Founder Led Equities, {html.escape(postal)}</p>'
             f'</td></tr></table></td></tr></table></body></html>')
    T.append(f"\n{COPY_RULE} Nothing here is investment advice.\n"
             f"You asked for this on founderledequities.com. Unsubscribe: {unsubscribe_url}\nFounder Led Equities, {postal}\n")
    return "\n".join(H), "\n".join(T), meta


def archive_page(md, topnav, css_href="/site.css"):
    """The letter as a page of the site: /tape/<date>/."""
    meta, blocks = parse(md)
    body = []
    for kind, val in blocks:
        if kind == "h1":
            body.append(f'<h1 style="font-family:var(--disp);font-weight:500;letter-spacing:-.02em;line-height:1.04;font-size:clamp(38px,5vw,60px);margin:0 0 10px">{inline(val)}</h1>')
        elif kind == "p":
            if val.startswith("[Read the full tape]"):
                body.append(f'<p><a class="gopro" href="/tape/" style="display:inline-block;text-decoration:none">This week\'s tape, live &rarr;</a></p>')
            else:
                body.append(f'<p style="font-size:15px;color:var(--mut);margin:0 0 14px;max-width:70ch">{inline(val)}</p>')
        elif kind == "table":
            head, rows = val[0], val[1:]
            body.append('<table class="tape"><thead><tr>' + "".join(f'<th{" class=\"n\"" if h in ("Amount","Change","New stake") else ""}>{html.escape(h)}</th>' for h in head) + "</tr></thead><tbody>")
            for cells in rows:
                k = {"Bought": "bought", "Discretionary": "disc", "Planned": "plan", "Plan": "plan", "Sold": "sold", "Compensation": "comp", "Transfer": "xfer"}.get(cells[0], "plan")
                tds = []
                for i, c in enumerate(cells):
                    h = head[i] if i < len(head) else ""
                    if i == 0:
                        tds.append(f'<td class="kd"><span class="kind {k}">{html.escape(c)}</span></td>')
                    elif h in ("New stake", "Change") and c == "Pro":
                        tds.append(f'<td class="n"><span class="sealed" data-shape="{"0.00%" if h == "New stake" else "−0.0%"}" aria-label="in Pro" title="in Pro"></span></td>')
                    elif h in ("Amount", "Change", "New stake"):
                        tds.append(f'<td class="n">{html.escape(c)}</td>')
                    elif h == "Company":
                        tds.append(f'<td class="co"><a class="pglink" href="/company/{html.escape(c)}/">{html.escape(c)}</a></td>')
                    elif h == "Manner":
                        tds.append(f'<td class="mn">{html.escape(c)}</td>')
                    else:
                        tds.append(f'<td class="ceo">{html.escape(c)}</td>')
                body.append('<tr class="dayrow">' + "".join(tds) + "</tr>")
            body.append("</tbody></table>")
    date = meta.get("date", "")
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(meta.get("subject","The tape"))} · Founder Led Equities</title>'
            f'<meta name="description" content="The Monday tape of {html.escape(meta.get("week",""))}: who bought, who cut a stake, who sold on a plan. Founders first.">'
            f'<link rel="canonical" href="{SITE}/tape/{date}/"><link rel="stylesheet" href="{css_href}">'
            f'<style>.letter{{max-width:1120px;margin:0 auto;padding:48px clamp(20px,3.5vw,48px) 60px}}.letter .tape{{max-width:860px}}</style></head><body>'
            f'{topnav}<div class="letter"><div style="font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);margin-bottom:14px">The Monday tape · {html.escape(dt.date.fromisoformat(date).strftime("%B %-d, %Y") if date else "")}</div>'
            + "\n".join(body) +
            f'<div class="tapefoot" style="border-top:1px solid var(--line);margin-top:40px;padding:16px 0 0;font-size:12.5px;color:var(--mut)">{html.escape(COPY_RULE)} · Nothing here is investment advice.</div>'
            f'</div></body></html>')


# ---------------------------------------------------------------- send
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
    print(f"  preview {html_p}  (open it in a browser)  subject: {meta.get('subject','')}")
    return 0


def cmd_page(a):
    md_p, _ = paths(a.root, a.date)
    md = open(md_p, encoding="utf-8").read()
    sys.path.insert(0, HERE)
    import build_company_pages as bcp  # noqa: E402
    idx = open(os.path.join(a.root, "index.html"), encoding="utf-8").read()
    topnav = bcp.extract_topnav(idx)
    css = "/site.css"
    try:
        css_text = open(os.path.join(a.out, "site.css"), encoding="utf-8").read()
        import hashlib
        css = f"/site.css?v={hashlib.sha256(css_text.encode()).hexdigest()[:10]}"
    except OSError:
        pass
    d = os.path.join(a.out, "tape", a.date)
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(archive_page(md, topnav, css))
    print(f"  archive page {d}/index.html")
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
        status, body = resend("/emails", {"from": FROM, "to": [to], "subject": f"[test] {meta.get('subject','This week\'s tape')}",
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
        payload = {"from": FROM, "subject": meta.get("subject", "This week's tape"), "html": h, "text": t,
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
        return 0 if status < 300 else 1
    print("send needs --test or --send"); return 2


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=ROOT)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draft"); d.add_argument("--date"); d.add_argument("--days", type=int, default=7); d.add_argument("--force", action="store_true")
    r = sub.add_parser("render"); r.add_argument("date")
    p = sub.add_parser("page"); p.add_argument("date"); p.add_argument("out")
    s = sub.add_parser("send"); s.add_argument("date"); s.add_argument("--test", action="store_true"); s.add_argument("--send", action="store_true")
    s.add_argument("--confirm", action="store_true"); s.add_argument("--to")
    a = ap.parse_args()
    return {"draft": cmd_draft, "render": cmd_render, "page": cmd_page, "send": cmd_send}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
