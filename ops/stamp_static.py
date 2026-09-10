#!/usr/bin/env python3
"""Stamp tonight's numbers into the published home page.

    python3 ops/stamp_static.py panel.csv universe/sp500-<date>.csv prices.csv founders.csv public/index.html

THE HTML SHOULD SAY WHAT THE PAGE SAYS. The home page is an app: the file
ships with a placeholder hero ("20 of 500") and empty sections, and the
script fills them in once the data loads. Anything that reads the HTML
without running scripts -- a fetch tool, an assistant asked "what is this
site", a search engine's first pass, a reader in the second before the
data arrives -- saw the placeholder and empty sections. Now the deploy
writes the computed hero, the stat strip, and the top ten of the
leaderboard into index.html as real markup, in the same classes the
script uses. The script still redraws them on load; the two can no
longer disagree.

Only the source file is edited in public/; index.html in the repo keeps
its placeholder, so the harness and the sample paint are unchanged.
"""
import csv
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from og_image import money, numbers  # noqa: E402


def top_rows(panel_p, sp_p, prices_p, founders_p, n=10):
    sp = {r["ticker"].upper() for r in csv.DictReader(open(sp_p, encoding="utf-8-sig"))}
    prices = {}
    for r in csv.DictReader(open(prices_p, encoding="utf-8-sig")):
        try:
            prices[r["ticker"].upper()] = float(r["close"])
        except (ValueError, KeyError):
            pass
    founders = {}
    try:
        for r in csv.DictReader(open(founders_p, encoding="utf-8-sig")):
            founders[r["ticker"].upper()] = ((r.get("founder") or "").lower(), r.get("evidence") or "")
    except OSError:
        pass
    # EVERY COMPANY IN ITS PLACE. The stamped board is what a free reader
    # sees first: the true ranking over the whole panel, with a sealed
    # company's row carrying its name and a lock where the value would be.
    rows = []
    for r in csv.DictReader(open(panel_p, encoding="utf-8-sig")):
        tk = (r.get("ticker") or "").upper()
        try:
            pct = float(r.get("pct") or "")
            sh = float(r.get("shares") or 0)
        except ValueError:
            continue
        val = sh * prices[tk] if tk in prices else 0.0
        if not val:
            continue
        rows.append({"tk": tk, "ceo": r.get("ceo") or "", "pct": pct, "val": val,
                     "f": founders.get(tk, ("", "")), "sealed": tk not in sp})
    rows.sort(key=lambda x: -x["val"])
    return rows[:n]


def badge(f):
    verdict, ev = f
    if verdict == "yes":
        return f'<span class="fb yes" title="{html.escape(ev[:300])}">FOUNDER</span>'
    if verdict == "uncertain":
        return '<span class="fb unc" title="founder language near the name, but the proxy sentence is ambiguous">FOUNDER?</span>'
    return ""


def bars_html(rows):
    if not rows:
        return ""
    mx = max((r["val"] for r in rows if not r["sealed"]), default=0) or 1
    out = []
    for r in rows:
        link0 = (f'<span class="tk"><a class="pglink" href="/company/{r["tk"]}/" onclick="event.stopPropagation()" '
                 f'title="this company\'s own page">{r["tk"]}</a></span><span class="nm">{html.escape(r["ceo"])}</span>{badge(r["f"])}')
        if r["sealed"]:
            out.append(
                f'<div class="brow sealed" onclick="openDrawer(\'{r["tk"]}\')" role="button" tabindex="0">'
                f'<div class="btrack"><div class="blab out" style="--w:0%">{link0}</div></div>'
                f'<div class="bpct"><button class="lock" onclick="event.stopPropagation();openPro()" title="the stake\'s value is in Pro">Pro</button></div></div>')
            continue
        w = max(2.0, r["val"] / mx * 100)
        inside = w > 20
        link = (f'<span class="tk"><a class="pglink" href="/company/{r["tk"]}/" onclick="event.stopPropagation()" '
                f'title="this company\'s own page">{r["tk"]}</a></span><span class="nm">{html.escape(r["ceo"])}</span>{badge(r["f"])}')
        lab_in = f'<div class="blab">{link}</div>' if inside else ""
        lab_out = f'<div class="blab out" style="--w:{w:.1f}%">{link}</div>' if not inside else ""
        out.append(
            f'<div class="brow" onclick="openDrawer(\'{r["tk"]}\')" role="button" tabindex="0">'
            f'<div class="btrack"><div class="bfill" style="width:{w:.1f}%">{lab_in}</div>{lab_out}</div>'
            f'<div class="bpct">{money(r["val"])}<span class="b2">{r["pct"]:.2f}% of co.</span></div></div>')
    return "".join(out)


def main(panel_p, sp_p, prices_p, founders_p, index_out):
    n = numbers(panel_p, sp_p, prices_p, founders_p)
    # THE PRO NUMBERS RIDE ALONG. A subscriber's first paint used to be the
    # free hero (19 of 500), replaced seconds later by 199 of 2,135 once
    # /api/me and a 1.3MB universe file had arrived. Both sentences are
    # stamped; the page picks one before anything loads (see the tier
    # cookie in index.html), and the fetched data only confirms it.
    p = numbers(panel_p, sp_p, prices_p, founders_p, everyone=True)
    rows = top_rows(panel_p, sp_p, prices_p, founders_p)
    page = open(index_out, encoding="utf-8").read()
    # THE HEADLINE IS THE PURPOSE AND NEEDS NO STAMP. The numbers live in
    # the strip beneath it: the rarity first (19 of 500 for the free
    # reader, the bare count for a subscriber), then the founder facts.
    # Both strips are written; the function on / picks the Pro one.
    if '<h1 id="thesis">' not in page:
        raise SystemExit("stamp_static: the hero was not found in index.html")
    # sealed = every panel row outside the open set, measured or not, which
    # is what the page counts (masked rows stay in a free reader's list)
    rows_all = sum(1 for r in csv.DictReader(open(panel_p, encoding="utf-8-sig")) if (r.get("ticker") or "").strip())
    sealed = rows_all - n["open"]
    # THE STRIP IS THE SAME FOR EVERYONE: four aggregates over every
    # company, none of them a company's stake, all of them the size of
    # what the site covers. The "N of them are sealed · Go Pro" line is
    # gone; the nav button is the one call, and the locks on the sealed
    # rows sell in context.
    def stats(m):
        return (f'<div class="hstat"><div class="n hl">{m["above5"]:,}</div><div class="k">CEOs own more than 5%</div></div>'
                f'<div class="hstat"><div class="n">{m["led"]}</div><div class="k">Founder-led companies</div></div>'
                f'<div class="hstat"><div class="n">{money(m["led_value"])}</div><div class="k">Held by those founders</div></div>'
                f'<div class="hstat"><div class="n">{m["share"]}%</div><div class="k">Of all CEO wealth</div></div>')
    page = page.replace('<div class="herostats" id="herostats"></div>',
                        f'<div class="herostats" id="herostats">{stats(p)}</div>', 1)
    page = page.replace('<div class="bars" id="bars"></div>',
                        f'<div class="bars" id="bars">{bars_html(rows)}</div>', 1)
    with open(index_out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"  stamped: {n['above5']} of {n['open']} in the strip, {len(rows)} board rows, "
          f"{n['led']} founder-led / {money(n['led_value'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:6]))
