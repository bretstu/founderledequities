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
import kinds  # noqa: E402
from og_image import money, numbers  # noqa: E402


def top_rows(panel_p, sp_p, prices_p, founders_p, n=10):
    # sp_p rides in the signature so every caller passes the same files
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
    # EVERY COMPANY IN ITS PLACE: the true ranking over the whole panel,
    # every row with its numbers (one tree, 2026-09-23).
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
                     "out": float(r.get("outstanding") or 0), "f": founders.get(tk, ("", ""))})
    # THE HOME PREVIEW (PLAN.md section 5, 2026-09-14): founders only, by
    # stake value, the same order as /companies/ at a different depth (the
    # share is one click on its header), every figure real.
    rows = [r for r in rows if r["f"][0] == "yes"]
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
    unchanged = kinds.COMP_LABELS  # the page's set (ops/kinds.py), one copy for every script
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
    """The first rows of the table, as renderTable draws them (one list,
    two depths: this is the home page's depth), every figure real."""
    out = []
    for i, r in enumerate(rows):
        tk = r["tk"]
        lt = last.get(tk)
        mcap = outstanding.get(tk, 0) * prices.get(tk, 0)
        fd = "Yes" if r["f"][0] == "yes" else ""
        own = f"{r['pct']:.3f}%" if r["pct"] < 1 else f"{r['pct']:.2f}%"
        val = money(r["val"]) if r["val"] else ""
        if lt:
            code = lt.get("code")
            pl = lt.get("plan") or ""
            k = "bought" if code == "P" else ("plan" if pl == "plan" else "disc" if pl == "discretionary" else "sold")
            word = {"bought": "Bought", "plan": "Planned", "disc": "Discretionary", "sold": "Sold"}[k]
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
            amt = money(v) if v and not (lt.get("price_flag") or "") else '<span class="nopr"></span>' 
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
    n = numbers(panel_p, sp_p, prices_p, founders_p)   # one universe (2026-09-23)
    rows = top_rows(panel_p, sp_p, prices_p, founders_p, n=3)
    page = open(index_out, encoding="utf-8").read()
    # THE HEADLINE IS THE PURPOSE AND NEEDS NO STAMP. The numbers live in
    # the strip beneath it.
    if '<h1 id="thesis">' not in page:
        raise SystemExit("stamp_static: the hero was not found in index.html")
    # THREE NUMBERS (PLAN.md section 5): how many companies are still run
    # by a founder, how many chief executives own more than 5%, what those
    # founders hold. The share of all CEO wealth was a fourth that said the
    # same thing as the third.
    def stats(m):
        return (f'<div class="hstat"><div class="n hl">{m["led"]}</div><div class="k">Founder-led companies</div></div>'
                f'<div class="hstat"><div class="n">{m["above5"]:,}</div><div class="k">CEOs own more than 5%</div></div>'
                f'<div class="hstat"><div class="n">{money(m["led_value"])}</div><div class="k">Held by those founders</div></div>'
                f'<div class="hstat"><div class="n">{m["open"]:,}</div><div class="k">Companies, computed nightly</div></div>')
    page = page.replace('<div class="herostats" id="herostats"></div>',
                        f'<div class="herostats" id="herostats">{stats(n)}</div>', 1)
    # THE THREE BIGGEST FOUNDER MOVES OF THE WEEK (2026-09-23): founders only,
    # ranked by the dollar value of the trade; a row that moved the stake says
    # by how much. Seven days, widened to 14 then 30 when
    # the week is quiet, so the section never publishes empty on a slow week.
    # Three rows (2026-09-24): the section is a proof of life, not the tape;
    # more of the page shows without a scroll.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import kinds as _kinds
        import datetime as _dt
        names = _kinds.company_names(panel_p)
        evdir = os.path.dirname(os.path.abspath(events_p)) or "."
        today = _dt.date.today().isoformat()
        wrows, days = [], 7
        for days in (7, 14, 30):
            wrows, _since = _kinds.window_rows(evdir, today, days=days, founders_only=True)
            if len(wrows) >= 3:
                break
    except Exception:  # noqa: BLE001 - no events file: the section says so
        wrows, days, names = [], 7, {}
        _kinds = None
    def fwrow(e):
        tk = e.get("tk") or ""
        filed = (e.get("filed") or "")[:10]
        try:
            day = _dt.date.fromisoformat(filed).strftime("%b %-d")
        except ValueError:
            day = filed
        label = (e.get("label") or "trade")
        v = None
        try:
            v = float(str(e.get("value")).replace(",", ""))
        except (TypeError, ValueError):
            pass
        mv = _kinds.move_of(e) if _kinds else None
        kind = _kinds.kind_of(e) if _kinds else ""
        cls = "sell" if kind in ("disc", "sold") else "buy" if kind == "bought" else ""
        who = e.get("ceo") or names.get(tk, tk)
        bits = [f"<b>{who}</b>: {label}"]
        if v:
            bits[-1] += f", <b>{money(v)}</b>"
        if mv is not None:
            bits.append(f"{abs(mv[0]):.1f}% of the stake")
        co = names.get(tk, "")
        if co and co != who:
            bits.append(co)
        return (f'<div class="fwrow"><span class="fwdate">{day}</span>'
                f'<a class="fwtk" href="/company/{tk}/">{tk}</a>'
                f'<span class="fwtxt">{" &middot; ".join(bits)}</span>'
                f'<span class="fwbadge {cls}">{label.upper()}</span></div>')
    if wrows:
        def _val(e):
            try:
                return float(str(e.get("value")).replace(",", ""))
            except (TypeError, ValueError):
                return 0.0
        wrows.sort(key=lambda e: -_val(e))
        rows5 = wrows[:3]
        fw = "".join(fwrow(e) for e in rows5)
    else:
        fw = '<div class="fwempty">A quiet week on the tape. <a href="/tape/">The full record</a> is a click away.</div>'
    page = page.replace('<div class="fwrows" id="fwrows"></div>', f'<div class="fwrows" id="fwrows">{fw}</div>', 1)
    # THE THREE LARGEST FOUNDER STAKES, BY VALUE: the cards are the home
    # page's authority flowing to the flagship pages.
    cards = []
    for r in rows[:3]:
        sub = f'{r["ceo"]}&rsquo;s stake, worth {money(r["val"])} at the latest close'
        cards.append(f'<a class="scard" href="/company/{r["tk"]}/">'
                     f'<div class="sck">{r["tk"]} &middot; {(r["co"] or r["tk"]).upper()}</div>'
                     f'<div class="scn">{r["pct"]:.2f}%</div>'
                     f'<div class="sct">{sub}</div></a>')
    page = page.replace('<div class="stakecards" id="stakecards"></div>',
                        f'<div class="stakecards" id="stakecards">{"".join(cards)}</div>', 1)
    page = page.replace('<span id="lednum"></span>', f'<span id="lednum">{n["led"]}</span>', 1)
    with open(index_out, "w", encoding="utf-8") as fh:
        fh.write(page)
    print(f"  stamped: {n['above5']} of {n['open']} in the strip, {len(rows5) if wrows else 0} week rows ({days}d window), "
          f"{len(cards)} stake cards, {n['led']} founder-led / {money(n['led_value'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:7]))
