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


OPEN_TOP = 0    # keep equal to build_site_data.OPEN_TOP: the seal is the S&P and nothing else


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
        rows.append({"tk": tk, "ceo": r.get("ceo") or "", "co": r.get("company") or tk, "pct": pct, "val": val,
                     "out": float(r.get("outstanding") or 0), "f": founders.get(tk, ("", "")), "sealed": tk not in sp})
    # THE FRACTION FIRST (PLAN.md section 5): the board opens by share of
    # the company, the order the live render draws; the dollar view is the
    # toggle. The top OPEN_TOP by share are everyone's, as build_site_data
    # ranks them.
    # THE HOME PREVIEW (PLAN.md section 5, 2026-09-14): founders only, the
    # open set, by stake value, the same order as /companies/ at a
    # different depth (the share is one click on its header); a free
    # reader's first twenty rows carry full figures and the line beneath
    # says how many more match in Pro. (OPEN_TOP is 0: the seal is the S&P
    # and nothing else.)
    rows = [r for r in rows if r["f"][0] == "yes" and not r["sealed"]]
    rows.sort(key=lambda x: -x["val"])
    return rows[:n]


def badge(f):
    verdict, ev = f
    if verdict == "yes":
        return f'<span class="fb yes" title="{html.escape(ev[:300])}">FOUNDER</span>'
    if verdict == "uncertain":
        return '<span class="fb unc" title="founder language near the name, but the proxy sentence is ambiguous">FOUNDER?</span>'
    return ""


def last_trades(events_p, tickers):
    """Each company's most recent stake-moving trade, as the table shows it
    (bought/sold, planned/discretionary, the amount, the trade date)."""
    unchanged = {"exercise and sell", "exercise, part sold", "vested and sold", "convert and sell",
                 "sale, position unchanged", "purchase, position unchanged"}
    last = {}
    try:
        for r in csv.DictReader(open(events_p, encoding="utf-8-sig")):
            tk = (r.get("ticker") or "").upper()
            if tk not in tickers or r.get("code") not in ("P", "S") or (r.get("label") or "") in unchanged:
                continue
            if (r.get("pre_ipo") or "") in ("1", "true", "True"):
                continue
            key = (r.get("traded") or r.get("filed") or "", r.get("filed") or "")
            if tk not in last or key > last[tk][0]:
                last[tk] = (key, r)
    except OSError:
        pass
    return {tk: v[1] for tk, v in last.items()}


def rows_html(rows, last, outstanding, prices):
    """The first twenty rows of the table, as renderTable draws them (one
    list, two depths: this is the home page's depth). A sealed row keeps
    its name and blurred placeholders."""
    out = []
    for i, r in enumerate(rows):
        tk = r["tk"]
        lt = last.get(tk)
        mcap = outstanding.get(tk, 0) * prices.get(tk, 0)
        fd = "Yes" if r["f"][0] == "yes" else ""
        if r["sealed"]:
            own = '<span class="sealed" data-shape="0.000%" aria-label="in Pro" title="in Pro"></span>'
            val = '<span class="sealed" data-shape="$00.0M" aria-label="in Pro" title="in Pro"></span>'
        else:
            own = f"{r['pct']:.3f}%" if r["pct"] < 1 else f"{r['pct']:.2f}%"
            val = money(r["val"]) if r["val"] else ""
        if lt:
            code = lt.get("code")
            k = "bought" if code == "P" else ("plan" if (lt.get("plan") or "") == "plan" else "disc")
            word = {"bought": "Bought", "plan": "Planned", "disc": "Discretionary"}[k]
            when = html.escape(lt.get("traded") or lt.get("filed") or "")
            try:
                import datetime as _dt
                _d = _dt.date.fromisoformat(when)
                short = f"{['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][(_d.weekday() + 1) % 7]} {_d.month}/{_d.day}"
            except ValueError:
                short = when
            kind = f'<span class="kind {k}">{word}</span><span class="dt">{short}</span>'
            try:
                v = float(lt.get("value") or 0)
            except ValueError:
                v = 0
            amt = ('<span class="sealed" data-shape="$0.0M" aria-label="in Pro"></span>' if r["sealed"]
                   else (money(v) if v and not (lt.get("price_flag") or "") else '<span class="nopr"></span>'))
            ltd = f'<span class="ltd">{when}</span>'
        else:
            kind, amt, ltd = '<span class="nopr"></span>', '<span class="nopr"></span>', '<span class="nopr"></span>'
        out.append(
            f'<tr onclick="openCompany(\'{tk}\')" tabindex="0">'
            f'<td class="rk">{i + 1:02d}</td>'
            f'<td class="c-co"><div class="tk"><a href="/company/{tk}/" onclick="event.stopPropagation()">{tk}</a></div><div class="nm">{html.escape(r["co"])}</div></td>'
            f'<td class="ceo h-ceo"><span class="ceow"><span class="cn">{html.escape(r["ceo"])}</span></span></td>'
            f'<td class="c-fd">{fd}</td>'
            f'<td class="n num c-own">{own}</td>'
            f'<td class="n num">{val}</td>'
            f'<td class="n num c-mc">{money(mcap) if mcap else ""}</td>'
            f'<td class="n num c-r1"><span class="nopr"></span></td>'
            f'<td class="c-lt">{kind}</td><td class="n num c-amt">{amt}</td><td class="c-ltd">{ltd}</td>'
            f'</tr>')
    return "".join(out)


def main(panel_p, sp_p, prices_p, founders_p, index_out, events_p="events.csv"):
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
    # THREE NUMBERS (PLAN.md section 5): how many companies are still run
    # by a founder, how many chief executives own more than 5%, what those
    # founders hold. The share of all CEO wealth was a fourth that said the
    # same thing as the third.
    def stats(m):
        return (f'<div class="hstat"><div class="n hl">{m["led"]}</div><div class="k">Founder-led companies</div></div>'
                f'<div class="hstat"><div class="n">{m["above5"]:,}</div><div class="k">CEOs own more than 5%</div></div>'
                f'<div class="hstat"><div class="n">{money(m["led_value"])}</div><div class="k">Held by those founders</div></div>')
    page = page.replace('<div class="herostats" id="herostats"></div>',
                        f'<div class="herostats" id="herostats">{stats(p)}</div>', 1)
    prices = {}
    try:
        for r in csv.DictReader(open(prices_p, encoding="utf-8-sig")):
            prices[(r.get("ticker") or "").upper()] = float(r.get("close") or 0)
    except (OSError, ValueError):
        pass
    last = last_trades(events_p, {r["tk"] for r in rows})
    outstanding = {r["tk"]: r["out"] for r in rows}
    page = page.replace('<tbody id="tbody"></tbody>',
                        f'<tbody id="tbody">{rows_html(rows, last, outstanding, prices)}</tbody>', 1)
    # THE WEEK'S SENTENCE AND THE TAPE EXCERPT, STAMPED (2026-09-14): both
    # were drawn by the script from the filings feed, the one download the
    # page waits for, so they appeared two seconds after everything else.
    # The same rows the letter uses (ops/letter.py: founders, seven days
    # by filing date, the kinds in order) are written into the HTML; the
    # script redraws them, identically, when the feed arrives.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import letter as _letter
        import datetime as _dt
        wrows, _since = _letter.week_rows(os.path.dirname(os.path.abspath(events_p)) or ".", _dt.date.today().isoformat())
    except Exception:  # noqa: BLE001 - no events file: the script still draws
        wrows = []
    if wrows:
        who = lambda k: len({(r["tk"], r["ceo"]) for r in wrows if r["kind"] == k})
        b, d, pl = who("bought"), who("disc"), who("plan")
        sentence = (f'<b>Past seven days:</b> {b} founder{"" if b == 1 else "s"} bought. {d} sold without a plan. '
                    f'{pl} sale{" was" if pl == 1 else "s were"} already scheduled.')
        page = page.replace('<p class="thisweek" id="thisweek"></p>',
                            f'<p class="thisweek" id="thisweek"><a href="/tape/">{sentence} <span class="arr">&rarr;</span></a></p>', 1)
        word = {"bought": "Bought", "disc": "Discretionary", "plan": "Planned", "comp": "Compensation"}
        manner = {"bought": "Open market", "disc": "Open market", "plan": "Pre-set plan", "comp": "Compensation"}
        out = []
        shown = [r for r in wrows if r["kind"] != "comp"][:8]
        for r in shown:
            k = r["kind"]
            amt = "" if not r["value"] or r["flag"] else _letter.money(r["value"])
            stake = ('<span class="sealed" data-shape="0.00%" aria-label="in Pro"></span>' if r["sealed"]
                     else (_letter.pct(r["after"]) if r["after"] is not None else ""))
            out.append(f'<tr class="dayrow"><td class="kd"><span class="kind {k}">{word[k]}</span></td>'
                       f'<td class="co"><a class="pglink" href="/company/{html.escape(r["tk"])}/">{html.escape(r["tk"])}</a></td>'
                       f'<td class="ceo"><span class="cn">{html.escape(r["ceo"])}</span></td>'
                       f'<td class="n v">{amt}</td><td class="n st">{stake}</td><td class="mn">{manner[k]}</td>'
                       f'<td class="td"><span class="dt">{html.escape(r["traded"])}</span></td></tr>')
        table = ('<table class="tape"><colgroup><col class="tw-kd"><col class="tw-co"><col class="tw-ceo"><col class="tw-v"><col class="tw-st"><col class="tw-mn"><col class="tw-td"></colgroup>'
                 '<thead><tr><th>Kind</th><th>Company</th><th>CEO</th><th class="n">Amount</th><th class="n">New stake</th><th>Manner</th><th>Traded</th></tr></thead>'
                 '<tbody>' + "".join(out) + '</tbody></table>')
        page = page.replace('<div class="tapewrap" id="actwrap"></div>', f'<div class="tapewrap" id="actwrap">{table}</div>', 1)
        page = page.replace('<div class="actnote" id="actnote"></div>',
                            f'<div class="actnote" id="actnote">{len(shown)} of {len(wrows)} filings · compensation listed last</div>', 1)
    with open(index_out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"  stamped: {n['above5']} of {n['open']} in the strip, {len(rows)} table rows, "
          f"{n['led']} founder-led / {money(n['led_value'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:7]))
