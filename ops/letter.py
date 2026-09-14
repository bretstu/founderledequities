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
COPY_RULE = ("S&P 500 current stakes and the last twelve months are open. "
             "The archive, every other $1B+ name, longer tape windows, and export are Pro.")
POSTAL_PLACEHOLDER = "[postal address]"
COMPENSATION = {"exercise and sell", "exercise, part sold", "vested and sold", "convert and sell",
                "sale, position unchanged", "purchase, position unchanged"}
KIND_WORD = {"bought": "Bought", "disc": "Discretionary", "plan": "Plan", "comp": "Compensation"}
KIND_ORDER = {"bought": 0, "disc": 1, "plan": 2, "comp": 3}
KIND_COLOR = {"bought": "#1F6B3A", "disc": "#B23428", "plan": "#6E6A64", "comp": "#8C8880"}

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
    if e["label"] in COMPENSATION:
        return "comp"
    if e["code"] == "P":
        return "bought"
    return "plan" if e["plan"] == "plan" else "disc"


def manner_of(e, k):
    if k in ("bought", "disc"):
        return "Open market"
    if k == "plan":
        return "10b5-1 plan"
    return {"exercise and sell": "Options cashed", "exercise, part sold": "Options cashed, part kept",
            "vested and sold": "Vest, part sold", "convert and sell": "Units converted",
            "sale, position unchanged": "Sale, stake unchanged",
            "purchase, position unchanged": "Purchase, stake unchanged"}.get(e["label"], "Compensation")


def nice_day(d):
    return dt.date.fromisoformat(d).strftime("%b %-d")


# ---------------------------------------------------------------- the week
def week_rows(root, until, days=7, founders_only=True):
    """The tape's rows for the window ending `until`: every purchase and
    sale filed in the window, founders only, with the kind, the amount,
    the stake after, whether the company is sealed, and the stake's move."""
    since = (dt.date.fromisoformat(until) - dt.timedelta(days=days)).isoformat()
    events = read(os.path.join(root, "events.csv"))
    panel = {r["ticker"].upper(): r for r in read(os.path.join(root, "panel.csv"))}
    founders = {r["ticker"].upper(): r.get("founder", "") for r in read(os.path.join(root, "founders.csv"))}
    sp_files = sorted(f for f in os.listdir(os.path.join(root, "universe")) if f.startswith("sp500-") and f.endswith(".csv"))
    sp = {r["ticker"].upper() for r in read(os.path.join(root, "universe", sp_files[-1]))} if sp_files else set()
    rows = []
    for e in events:
        if e["code"] not in ("P", "S") or not (since < e["filed"] <= until):
            continue
        tk = e["ticker"].upper()
        if founders_only and founders.get(tk) != "yes":
            continue
        k = kind_of(e)
        pc = num(e.get("pct_of_holding"))
        move = None if pc is None else (max(0.0, pc) if k == "bought" else max(0.0, -pc))
        rows.append({
            "kind": k, "tk": tk, "ceo": e["ceo"], "founder": founders.get(tk) == "yes",
            "sealed": tk not in sp, "value": num(e.get("value")), "flag": e.get("price_flag") or "",
            "after": num(e.get("pct_after")), "change": pc, "move": move if k != "comp" else None,
            "manner": manner_of(e, k), "traded": e.get("traded") or e.get("filed"),
            "url": e.get("url") or "", "first": (e.get("first_buy") or "") == "1",
            "company": panel.get(tk, {}).get("company", ""),
        })
    rows.sort(key=lambda r: (KIND_ORDER[r["kind"]], -(r["move"] if r["move"] is not None else -1), r["traded"]))
    return rows, since


def weather(rows):
    who = lambda k: len({(r["tk"], r["ceo"]) for r in rows if r["kind"] == k})
    comp = sum(1 for r in rows if r["kind"] == "comp")
    first = sum(1 for r in rows if r["kind"] == "bought" and r["first"])
    parts = [f"**{who('bought')}** CEO{'s' if who('bought') != 1 else ''} bought"]
    if first:
        parts.append(f"**{first}** for the first time ever")
    parts += [f"**{who('disc')}** cut a stake", f"**{who('plan')}** sold on a plan",
              f"**{comp}** compensation filing{'s' if comp != 1 else ''} did not move a stake"]
    return " · ".join(parts)


def kicker(rows):
    """Two lines: the largest open-market buy, the largest discretionary
    sale. Never a plan, never compensation."""
    out = []
    rows = collapse(rows)
    buys = [r for r in rows if r["kind"] == "bought" and r["value"] and not r["flag"]]
    if buys:
        b = max(buys, key=lambda r: r["value"])
        out.append(f"Largest open-market buy: {b['ceo']}, {b['tk']}, {money(b['value'])} "
                   f"({'stake in Pro' if b['sealed'] else stake_change(b['change'])}).")
    sales = [r for r in rows if r["kind"] == "disc" and r["value"] and not r["flag"]]
    if sales:
        s = max(sales, key=lambda r: r["value"])
        out.append(f"Largest discretionary sale: {s['ceo']}, {s['tk']}, {money(s['value'])} "
                   f"({'stake in Pro' if s['sealed'] else stake_change(s['change'])}).")
    return out


def collapse(rows):
    """ONE ROW PER PERSON PER KIND. Four buys by one founder in a week are
    one line in a letter (the amounts summed, the count noted, the stake
    after the last one), not four lines that crowd out everyone else. The
    page can afford the rows; the letter cannot."""
    out, seen = [], {}
    for r in rows:
        key = (r["tk"], r["ceo"], r["kind"])
        if key in seen:
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
    """The largest of each kind, about a dozen rows: every open-market buy
    first (they are rare and the point), then discretionary sales, then
    plans, then one compensation row. Sealed rows are not held back."""
    rows = collapse(rows)
    buys = [r for r in rows if r["kind"] == "bought"]
    disc = [r for r in rows if r["kind"] == "disc"]
    plan = [r for r in rows if r["kind"] == "plan"]
    comp = [r for r in rows if r["kind"] == "comp"][:1]
    out = buys[:cap]
    room = max(0, cap - len(out))
    out += disc[:max(2, room * 2 // 3)]
    room = max(0, cap - len(out))
    out += plan[:max(2, room)]
    out += comp
    return out


# ---------------------------------------------------------------- the markdown
def draft_markdown(root, date, days=7):
    rows, since = week_rows(root, date, days)
    shown = pick(rows)
    sealed_n = sum(1 for r in rows if r["sealed"] and r["kind"] != "comp")
    comp_n = sum(1 for r in rows if r["kind"] == "comp")
    week = f"{nice_day(since)} to {nice_day(date)}"
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
        f"Founders only · {week} · stake-moving trades first",
        "",
        weather(rows),
        "",
    ]
    for k in kicker(rows):
        lines.append(k)
    if kicker(rows):
        lines.append("")
    lines += ["| Kind | Company | CEO | Amount | New stake | Manner |", "|---|---|---|---|---|---|"]
    for r in shown:
        amount = "—" if r["kind"] == "comp" else (money(r["value"]) if r["value"] else "—")
        stake = "Pro" if r["sealed"] else (pct(r["after"]) or "—")
        ceo = r["ceo"] + (" (first buy)" if r["first"] else "")
        manner = r["manner"] + (f" · {r['n']} filings" if r.get("n", 1) > 1 else "")
        lines.append(f"| {KIND_WORD[r['kind']]} | {r['tk']} | {ceo} | {amount} | {stake} | {manner} |")
    lines += [
        "",
        f"{len(rows)} filings this week · shown here: the largest of each kind"
        + (f" · the stake after the trade is in Pro for the {sealed_n} from companies outside the S&P 500" if sealed_n else "")
        + (" · compensation listed last" if comp_n else "") + ".",
        "",
        f"[Read the full tape]({SITE}/tape/)",
        "",
    ]
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
                f'<th align="{"right" if h in ("Amount","New stake") else "left"}" style="font-size:11px;font-weight:bold;letter-spacing:.06em;text-transform:uppercase;color:{INK};padding:0 6px 8px 0;border-bottom:1px solid {INK};">{html.escape(h)}</th>'
                for h in head) + "</tr>")
            for cells in body:
                k = {"Bought": "bought", "Discretionary": "disc", "Plan": "plan", "Compensation": "comp"}.get(cells[0], "plan")
                dim = k == "comp"
                col = FAINT if dim else INK
                tds = []
                for i, c in enumerate(cells):
                    h = head[i] if i < len(head) else ""
                    if i == 0:
                        tds.append(f'<td style="padding:8px 6px 8px 0;border-top:1px solid {LINE2};font-size:12px;font-weight:bold;color:{KIND_COLOR[k]};white-space:nowrap;">{html.escape(c)}</td>')
                    elif h == "New stake" and c == "Pro":
                        tds.append(f'<td align="right" style="padding:8px 6px 8px 0;border-top:1px solid {LINE2};"><a href="{SITE}/#pro" style="display:inline-block;font-size:9px;font-weight:bold;letter-spacing:.06em;color:{FAINT};border:1px solid {LINE};padding:1px 6px;text-decoration:none;">Pro</a></td>')
                    elif h in ("Amount", "New stake"):
                        tds.append(f'<td align="right" style="padding:8px 6px 8px 0;border-top:1px solid {LINE2};font-family:Menlo,Consolas,monospace;font-size:12px;color:{col};white-space:nowrap;">{html.escape(c)}</td>')
                    elif h == "Company":
                        tds.append(f'<td style="padding:8px 6px 8px 0;border-top:1px solid {LINE2};font-size:13px;font-weight:bold;color:{col};"><a href="{SITE}/company/{html.escape(c)}/" style="color:{col};text-decoration:none;">{html.escape(c)}</a></td>')
                    elif h == "Manner":
                        tds.append(f'<td style="padding:8px 0 8px 0;border-top:1px solid {LINE2};font-size:12px;color:{MUT};white-space:nowrap;">{html.escape(c)}</td>')
                    else:
                        tds.append(f'<td style="padding:8px 6px 8px 0;border-top:1px solid {LINE2};font-size:13px;color:{col};">{html.escape(c)}</td>')
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
            body.append('<table class="tape"><thead><tr>' + "".join(f'<th{" class=\"n\"" if h in ("Amount","New stake") else ""}>{html.escape(h)}</th>' for h in head) + "</tr></thead><tbody>")
            for cells in rows:
                k = {"Bought": "bought", "Discretionary": "disc", "Plan": "plan", "Compensation": "comp"}.get(cells[0], "plan")
                tds = []
                for i, c in enumerate(cells):
                    h = head[i] if i < len(head) else ""
                    if i == 0:
                        tds.append(f'<td class="kd"><span class="kind {k}">{html.escape(c)}</span></td>')
                    elif h == "New stake" and c == "Pro":
                        tds.append('<td class="n st"><span class="sealed" data-shape="0.00%" aria-label="in Pro" title="in Pro"></span></td>')
                    elif h in ("Amount", "New stake"):
                        tds.append(f'<td class="n">{html.escape(c)}</td>')
                    elif h == "Company":
                        tds.append(f'<td class="co"><a class="pglink" href="/company/{html.escape(c)}/">{html.escape(c)}</a></td>')
                    elif h == "Manner":
                        tds.append(f'<td class="mn">{html.escape(c)}</td>')
                    else:
                        tds.append(f'<td class="ceo">{html.escape(c)}</td>')
                body.append(f'<tr class="dayrow{" dim" if k == "comp" else ""}">' + "".join(tds) + "</tr>")
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
    req = urllib.request.Request(f"https://api.resend.com{path}", data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


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
        payload = {"from": FROM, "subject": meta.get("subject", "This week's tape"), "html": h, "text": t,
                   "name": f"Monday tape {a.date}"}
        if os.environ.get("RESEND_AUDIENCE_ID"):
            payload["audience_id"] = os.environ["RESEND_AUDIENCE_ID"]
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
