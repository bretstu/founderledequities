#!/usr/bin/env python3
"""One page per company, at its own address.

    python3 ops/build_company_pages.py panel.csv founders.csv prices.csv \\
        universe/sp500-<date>.csv public/

A PAGE IS SOMETHING A LINK CAN POINT AT AND A SEARCH ENGINE CAN FIND. The
drawer has neither property. This writes public/company/<TICKER>/index.html
for every company in the panel -- title, description and card tags baked in
so a shared link unfurls with the number and a query like "how much of
Tesla does the CEO own" has a page to land on -- plus /company.js, /site.css
and /sitemap.xml.

ONE SOURCE FOR THE RULES. company.js is not written by hand: every
declaration in index.html marked /*@shared*/ (the parsers, the formatters,
the chart, the honesty rules) is extracted here and the page's own logic
(assets/company-page.js) appended, so the two pages cannot drift. The
stylesheet is index.html's <style>, extracted the same way.

THE SEAL IS THE ONLY GATE, ON PAGES TOO. An S&P company's page carries its
numbers in the HTML. A sealed company's page carries the company, the CEO
and the founder verdict -- public already -- and no figure; company.js fills
the numbers in from /pro/ for a signed-in subscriber.
"""
import csv
import datetime
import hashlib
import html
import json
import os
import re
import sys

SITE = "https://founderledequities.com"


def extract_shared(index_html: str) -> str:
    """Every declaration that follows a /*@shared*/ marker, whole."""
    lines = index_html.split("\n")
    out = []
    i = 0
    n = 0
    while i < len(lines):
        if lines[i].strip() == "/*@shared*/":
            j = i + 1
            first = lines[j]
            block = [first]
            opens = first.count("{") - first.count("}")
            if opens == 0 and first.rstrip().endswith(("}", ";")):
                # complete on one line: function fInfo(tk){return ...}
                i = j + 1
                out.append(first); n += 1
                continue
            if opens > 0 or (first.rstrip().endswith("{")):
                # a braced body: through the line that closes it at column 0
                k = j + 1
                while k < len(lines) and not re.match(r"^\}[;)]?\s*$", lines[k]):
                    block.append(lines[k]); k += 1
                if k < len(lines):
                    block.append(lines[k])
                i = k + 1
            elif not first.rstrip().endswith(";"):
                # a multi-line expression: through the first line ending in ';'
                k = j + 1
                while k < len(lines) and not lines[k].rstrip().endswith(";"):
                    block.append(lines[k]); k += 1
                if k < len(lines):
                    block.append(lines[k])
                i = k + 1
            else:
                i = j + 1
            out.append("\n".join(block))
            n += 1
        else:
            i += 1
    if n < 20:
        raise SystemExit(f"only {n} shared declarations found in index.html; expected 20+")
    return "\n\n".join(out)


def extract_style(index_html: str) -> str:
    """Every <style> block in index.html, in order. There was one; the
    self-hosted fonts added a second ahead of it, the extractor took the
    first it found, and every company page shipped with four font-face
    rules for a stylesheet."""
    blocks = re.findall(r"<style>(.*?)</style>", index_html, re.S)
    if not blocks:
        raise SystemExit("no <style> in index.html")
    css = "\n".join(b.strip() for b in blocks)
    if ":root{" not in css:
        raise SystemExit("index.html's stylesheet has no :root block; refusing to publish a site.css without the tokens")
    return css


def extract_topnav(index_html: str) -> str:
    m = re.search(r'(<div class="top"><div class="wrap topin">.*?</div></div>)\n', index_html, re.S)
    if not m:
        raise SystemExit("no top nav in index.html")
    nav = m.group(1)
    # links become absolute, back to the home page's sections; the dev
    # toggle and Go Pro stay off a static page that has no modal
    nav = nav.replace('href="#', 'href="/#').replace('href="about.html"', 'href="/about.html"')
    nav = re.sub(r'\s*<button class="devtog".*?</button>', "", nav, flags=re.S)
    nav = re.sub(r'<button class="gopro" onclick="openPro\(\)">Go Pro</button>',
                 '<a class="gopro" href="/pro/" style="text-decoration:none">Go Pro</a>', nav)
    nav = nav.replace("onclick=\"window.scrollTo({top:0,behavior:'smooth'})\"", "onclick=\"location.href='/'\"")
    nav = nav.replace("onkeydown=\"if(event.key==='Enter')window.scrollTo({top:0,behavior:'smooth'})\"",
                      "onkeydown=\"if(event.key==='Enter')location.href='/'\"")
    return nav


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def money(v):
    for div, suf, dp in ((1e12, "T", 2), (1e9, "B", 1), (1e6, "M", 1)):
        if v < div * 0.9995:
            continue
        x = v / div
        s = f"{x:.0f}" if x >= 100 else f"{x:.{dp}f}"
        if float(s) >= 1000 and div < 1e12:
            continue
        # strip only a decimal's trailing zeros: "1.30" -> "1.3", never "370" -> "37"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return "$" + s + suf
    return f"${v:,.0f}"


def page_text(r, sp: bool, price):
    """Title and description: the number for an open company, none for a
    sealed one -- the HTML is public, and the seal is the product."""
    ceo, co, tk = r["ceo"] or "The chief executive", r["company"] or r["ticker"], r["ticker"]
    pct = num(r.get("pct"))
    if sp and pct is not None:
        title = f"{ceo} owns {pct:.2f}% of {co} ({tk}) · Founder Led Equities"
        sh = num(r.get("shares")) or 0
        val = f", worth {money(sh * price)} at the latest close" if price and sh else ""
        desc = (f"{ceo}, CEO of {co}, owns {pct:.2f}% of the company{val}: "
                f"{sh:,.0f} shares as of {r.get('shares_as_of') or 'the latest filing'}, "
                f"computed from SEC filings, never estimated. Every trade, every filing linked.")
    else:
        # THE QUESTION, VERBATIM. "How much of X does Y own" is what a
        # searcher types; the page carries it as its title and heading, the
        # public facts around it, and the honest partial answer.
        title = f"How much of {co} does {ceo} own? ({tk}) · Founder Led Equities"
        desc = (f"{ceo} is the chief executive of {co}. The stake, computed from SEC filings and never "
                f"estimated, the shares, the value and every trade are in Pro; the company's price, market cap "
                f"and the filings on record are here.")
    return title, desc[:300]


def poss(name: str) -> str:
    """Whose stake: "Elon Musk's", "Jabbok Schlacks'"."""
    return name + ("'" if name.lower().endswith("s") else "'s")


def compact(n: float) -> str:
    """1,120,000,000 -> 1.12B; 17,074,104 -> 17.1M; the page's own rule."""
    a = abs(n)
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            v = n / div
            return f"{v:.2f}{suf}" if v < 10 else f"{v:.1f}{suf}" if v < 100 else f"{v:.0f}{suf}"
    return f"{int(n):,}"


UNCHANGED = {"exercise and sell", "convert and sell", "sale, position unchanged", "purchase, position unchanged"}


def load_summaries(events_p, hist_p):
    """Per ticker, what a paragraph needs: the first and last points of the
    record, how many purchases and sales moved the stake, and the last one
    that did. Read once from the full files; the pages then say something
    no other page says, from data, without a word of prose being guessed."""
    ev = {}
    try:
        for r in csv.DictReader(open(events_p, encoding="utf-8-sig")):
            tk = (r.get("ticker") or "").upper()
            if not tk or r.get("code") not in ("P", "S"):
                continue
            if (r.get("label") or "") in UNCHANGED or (r.get("pre_ipo") or "") in ("1", "true", "True"):
                continue
            d = ev.setdefault(tk, {"buys": 0, "sells": 0, "last": None, "older": 0, "first": ""})
            d["buys" if r["code"] == "P" else "sells"] += 1
            fd = r.get("filed") or ""
            if not d["first"] or fd < d["first"]:
                d["first"] = fd
            key = (r.get("traded") or r.get("filed") or "", r.get("filed") or "")
            if d["last"] is None or key > d["last"][0]:
                d["last"] = (key, r)
    except OSError:
        pass
    # THE ARCHIVE (PLAN.md section 2): the trades filed more than a year
    # before the newest filing are the Pro record; a free page shows the
    # year and says how many older trades there are.
    newest = max((d["last"][0][1] for d in ev.values() if d["last"]), default="")
    if newest:
        import datetime as _dt
        year_ago = (_dt.date.fromisoformat(newest) - _dt.timedelta(days=366)).isoformat()
        try:
            for r in csv.DictReader(open(events_p, encoding="utf-8-sig")):
                tk = (r.get("ticker") or "").upper()
                if tk in ev and r.get("code") in ("P", "S") and (r.get("filed") or "") < year_ago:
                    ev[tk]["older"] += 1
        except OSError:
            pass
    hist = {}
    try:
        for r in csv.DictReader(open(hist_p, encoding="utf-8-sig")):
            tk = (r.get("ticker") or "").upper()
            pct = num(r.get("pct"))
            if not tk or pct is None or pct > 100:
                continue
            h = hist.setdefault(tk, {"first": None, "last": None})
            key = r.get("date") or ""
            if h["first"] is None or key < h["first"][0]:
                h["first"] = (key, pct)
            if h["last"] is None or key > h["last"][0]:
                h["last"] = (key, pct)
    except OSError:
        pass
    return ev, hist


def founder_quote(founder) -> str:
    """The proxy's own sentence, trimmed to whole sentences: public on every
    page (the badge's receipt), and the one thing that makes a sealed page
    say something a crawler can index."""
    ev = (founder or {}).get("ev") or ""
    ev = " ".join(ev.split())
    if len(ev) < 40:
        return ""
    i = ev.find(". ")
    if 0 < i < len(ev) - 60 and not ev[0].isupper():
        ev = ev[i + 2:]
    j = ev.rfind(".")
    if j > 40:
        ev = ev[:j + 1]
    return html.escape(ev[:400])


def price_line_svg(store, tk, years=5):
    """The stock's closes over the last years, as a small SVG line: public
    data, drawn statically so a sealed page shows something true and
    complete without the trade dots that belong to the record."""
    if not store:
        return ""
    try:
        with open(os.path.join(store, f"{tk}.csv"), encoding="utf-8", newline="") as fh:
            rd = csv.reader(fh); next(rd, None)
            pts = [(d, float(c)) for d, c in rd if d]
    except (OSError, ValueError):
        return ""
    if len(pts) < 20:
        return ""
    cut = (datetime.date.fromisoformat(pts[-1][0]) - datetime.timedelta(days=365 * years)).isoformat()
    pts = [p for p in pts if p[0] >= cut] or pts
    W, H, pad = 760, 220, 8
    lo, hi = min(c for _, c in pts), max(c for _, c in pts)
    span = (hi - lo) or 1.0
    xs = [pad + i * (W - 2 * pad) / (len(pts) - 1) for i in range(len(pts))]
    ys = [H - pad - (c - lo) / span * (H - 2 * pad) for _, c in pts]
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    first, last = pts[0], pts[-1]
    return (f'<div class="csec crec" data-nosnippet><div class="cshead"><h2>Price</h2>'
            f'<div class="sub">{html.escape(first[0][:4])} to {html.escape(last[0])}: ${first[1]:,.2f} to ${last[1]:,.2f}</div></div>'
            f'<svg class="pricesvg" viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img" aria-label="{html.escape(tk)} share price, last {years} years">'
            f'<path d="{d}" fill="none" stroke="var(--ink)" stroke-width="1.6" vector-effect="non-scaling-stroke"/></svg></div>')


def kicker_mcap(r, price) -> str:
    """The market cap beside the ticker, beside the name. Public data, so
    sealed pages carry it too."""
    out = num(r.get("outstanding"))
    return f" · {money(out * price)}" if (price and out) else ""


def static_body(payload, r, is_sp, price, price_date, ev, hist, founder, n_filings=0, ret_1y=None,
                last_filed="", scale=None, price_svg=""):
    """THE PAGE SAYS ITS NUMBERS IN HTML. A fetch without scripts (a
    crawler's first pass, an assistant, a reader in the second before the
    data arrives) read a name and a footer; the stake, the value, the
    record and the last trade all arrived by script. Now the answer band
    and a paragraph are written into the page; the script redraws over
    them. A sealed page gets the paragraph without the numbers."""
    co = html.escape(payload["co"]); ceo = html.escape(payload["ceo"] or "the chief executive")
    fsent = ""
    if founder and founder.get("f") == "yes":
        fsent = f" The company's proxy statement names {ceo} a founder."
    elif founder and founder.get("f") == "uncertain":
        fsent = f" The proxy's language on whether {ceo} founded the company is ambiguous."
    if not is_sp:
        q = founder_quote(founder)
        quote = f' <span class="cq">The proxy statement says: &ldquo;{q}&rdquo;</span>' if q else ""
        onrec = (f" {n_filings} Form 4 filings on record since 2016"
                 + (f", the most recent filed {html.escape(last_filed)}." if last_filed else ".")) if n_filings else ""
        out = num(r.get("outstanding"))
        def stat(k, v, cls=""):
            return f'<div class="cstat"><div class="k">{k}</div><div class="v {cls}">{v}</div></div>'
        # THE OPEN PAGE'S SHAPE, WITH THE SEALS ON THE FIGURES. The same four
        # cards; a blurred placeholder where the stake, the shares and the
        # worth would be (the numbers are not on the page), the cover page's
        # count shown. One line of prose. No box: the nav's button is the one.
        blur = lambda shape: f'<span class="sealed" data-shape="{shape}" aria-label="in Pro" onclick="openPro()" title="in Pro"></span>'
        cards = ('<div class="cband three">'
                 f'<div><h2 class="p"><span class="k">{ceo} owns</span>{blur("0.00%")}</h2></div>'
                 + stat("Shares held", blur("00,000,000"))
                 + stat("Worth", blur("$0.0B"))
                 + '</div>')
        co_s = co[:-1] if co.endswith(".") else co   # "Inc." takes no second period
        return (f'<h2 class="cq2">How much of {co} does {ceo} own?</h2>'
                f'<p class="cprose">{ceo} is the chief executive of {co_s}.{fsent}{onrec}</p>'
                + cards + price_svg)
    pct = num(r.get("pct")); sh = num(r.get("shares")); out = num(r.get("outstanding"))
    if pct is None or sh is None:
        return f'<p class="cprose">{ceo} is the chief executive of {co}.{fsent} The record could not settle on a figure; the reasons are on the row.</p>'
    val = f", worth about {money(sh * price)} at the {html.escape(price_date)} close" if price else ""
    pd = html.escape(price_date)
    # THE SAME BAND THE SCRIPT DRAWS, in the same words: the answer card,
    # then Value / Market cap / Shares held / 1Y return, each in a card,
    # and the fraction as the receipt line. The script redraws it on load.
    def stat(k, v, cls="", sub=""):
        return (f'<div class="cstat"><div class="k">{k}</div><div class="v {cls}">{v}</div>'
                + (f'<div class="s">{sub}</div>' if sub else "") + '</div>')
    r1 = ret_1y.get(payload["tk"]) if ret_1y else None
    # THREE CARDS (2026-09-14): the share, the shares, what they are worth.
    # Shares outstanding to the share was a second ledger above the chart;
    # it is a column of the trades table and in the kicker's market cap.
    band = ('<div class="cband three">'
            f'<div><h2 class="p"><span class="k">{ceo} owns</span>{pct:.2f}%</h2></div>'
            + stat("Shares held", f"{int(sh):,}")
            + stat("Worth", money(sh * price) if price else "&mdash;")
            + '</div>'
            )
    h = hist.get(payload["tk"]) or {}
    e = ev.get(payload["tk"]) or {}
    moved = ""
    if h.get("first") and h.get("last") and h["first"][0] < h["last"][0]:
        moved = f" The stake has moved from {h['first'][1]:.2f}% in {h['first'][0][:4]} to {h['last'][1]:.2f}% on {h['last'][0]}"
        if e:
            ns, nb = e.get("sells", 0), e.get("buys", 0)
            moved += f", across {ns} sale{'s' if ns != 1 else ''} and {nb} purchase{'s' if nb != 1 else ''} that moved it since 2016"
        moved += "."
    last = ""
    if e.get("last"):
        lr = e["last"][1]
        v = num(lr.get("value")); plan = (lr.get("plan") or "")
        kind = "purchase" if lr.get("code") == "P" else "sale"
        how = "planned " if plan == "plan" else "discretionary " if plan == "discretionary" else ""
        last = f" The last trade that moved it was a {how}{kind}{(' of ' + money(v)) if v else ''} on {html.escape(lr.get('traded') or lr.get('filed') or '')}."
    if out:
        prose = f'<p class="cprose">{ceo} owns {pct:.2f}% of {co}: {int(sh):,} of {int(out):,} shares{val}.{moved}{last}{fsent}</p>'
    else:
        prose = f'<p class="cprose">{ceo} owns {pct:.2f}% of {co}.{fsent}</p>'
    return band + prose


INDEX_CSS = ("""
.cidx{padding:32px 0 60px}.cidx h1{font-family:var(--disp);font-size:clamp(28px,4vw,44px);font-weight:650;letter-spacing:-.02em;margin:0 0 8px}
.cidx .sub{color:var(--mut);margin-bottom:18px}.cidx .letters{font-family:var(--mono);font-size:13px;display:flex;flex-wrap:wrap;gap:10px;margin-bottom:24px}.cidx .letters a{color:var(--blue);text-decoration:none}
.cidx section{margin-top:22px}.cidx h2{font-family:var(--mono);font-size:13px;color:var(--faint);letter-spacing:.14em;margin:0 0 8px}
.cidx ul{list-style:none;margin:0;padding:0;columns:3;column-gap:32px}.cidx li{break-inside:avoid;padding:4px 0;font-size:13.5px}
.cidx li a{font-family:var(--mono);font-weight:600;color:var(--blue);text-decoration:none}.cidx .co{color:var(--ink)}.cidx .ceo{color:var(--mut)}
.cidx .seal{font-family:var(--mono);font-size:10px;color:var(--faint);border:1px solid var(--line);border-radius:4px;padding:1px 5px;margin-left:4px}
@media(max-width:900px){.cidx ul{columns:2}}@media(max-width:560px){.cidx ul{columns:1}}
""")


def neighbours_html(tk, ranked, sp, k=5):
    """Five nearby founder-led companies by stake rank, open ones first, so
    every page has five incoming links and a reader has somewhere to go."""
    if tk not in ranked:
        return ""
    i = ranked.index(tk)
    cand = [t for t in ranked[max(0, i - 12): i + 13] if t != tk]
    cand.sort(key=lambda t: (t not in sp, abs(ranked.index(t) - i)))
    picks = cand[:k]
    if not picks:
        return ""
    items = "".join(f'<li><a href="/company/{html.escape(t)}/">{html.escape(t)}</a> <span>{html.escape(NAMES.get(t, ""))}</span></li>' for t in picks)
    return f'<div class="cmore"><div class="k">More founder-led companies</div><ul>{items}</ul></div>'


NAMES = {}


def companies_index(rows, founders, sp, out_dir, topnav, css_v):
    """/companies/: one plain HTML link per company, grouped by letter, so
    every page has an internal link a crawler can follow without scripts."""
    by = {}
    for r in rows:
        by.setdefault(r["tk"][0], []).append(r)
    parts = []
    for letter in sorted(by):
        items = []
        for r in sorted(by[letter], key=lambda x: x["tk"]):
            badge = ' <span class="fb yes">FOUNDER</span>' if (founders.get(r["tk"]) or {}).get("f") == "yes" else ""
            seal = "" if r["tk"] in sp else ' <span class="seal">Pro</span>'
            items.append(f'<li><a href="/company/{html.escape(r["tk"])}/">{html.escape(r["tk"])}</a> '
                         f'<span class="co">{html.escape(r["co"])}</span> <span class="ceo">{html.escape(r["ceo"])}</span>{badge}{seal}</li>')
        parts.append(f'<section><h2 id="{letter}">{letter}</h2><ul>{"".join(items)}</ul></section>')
    nav = " ".join(f'<a href="#{l}">{l}</a>' for l in sorted(by))
    n = f"{len(rows):,}"
    index_html_block = (f"<div class=\"cidx\"><div class=\"wrap\"><h2 style=\"font-family:var(--disp);font-weight:500;font-size:24px;letter-spacing:-.01em;color:var(--ink);margin:40px 0 6px\">Every company, A to Z</h2>"
                        f"<div class=\"sub\">{n} US public companies worth $1B or more, each with a page for what its chief executive owns. S&amp;P 500 current stakes are open; the rest is Pro.</div>"
                        f"<div class=\"letters\">{nav}</div>{''.join(parts)}</div></div>")
    # THE SCREENER IN FULL (PLAN.md section 5): the page is the template
    # companies.html (the table with its controls, the same block the home
    # page shows twenty rows of) with the A-Z index under it. Without the
    # template, the index alone.
    here = os.path.dirname(os.path.abspath(__file__))
    tpl_p = os.path.join(os.path.dirname(here), "companies.html")
    if os.path.exists(tpl_p):
        page = (open(tpl_p, encoding="utf-8").read()
                .replace("{{TOPNAV}}", topnav)
                .replace("{{INDEX_CSS}}", INDEX_CSS)
                .replace("{{INDEX}}", index_html_block)
                .replace('href="/site.css"', f'href="/site.css?v={css_v}"'))
        js_p = os.path.join(out_dir, "companies.js")
        if os.path.exists(js_p):
            import hashlib as _h
            v = _h.sha256(open(js_p, "rb").read()).hexdigest()[:10]
            page = page.replace('src="/companies.js"', f'src="/companies.js?v={v}"')
    else:
        page = ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n"
                "<title>Every company &mdash; Founder Led Equities</title>\n"
                f"<link rel=\"stylesheet\" href=\"/site.css?v={css_v}\"><style>{INDEX_CSS}</style></head><body>\n{topnav}\n"
                f"{index_html_block}</body></html>")
    os.makedirs(os.path.join(out_dir, "companies"), exist_ok=True)
    with open(os.path.join(out_dir, "companies", "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)


def card_tags(page: str, tk: str, og_dir: str | None) -> str:
    """Point the page's og:image and twitter:image at the company's own
    card when one was drawn (ops/company_cards.py), versioned by the
    card's hash so a redrawn card is a new URL to every unfurler's cache.
    Without a card the page keeps the site-wide og.png."""
    if not og_dir:
        return page
    from company_cards import card_version
    v = card_version(og_dir, tk)
    if not v:
        return page
    url = f"{SITE}/og/{tk}.png?v={v}"
    return (page.replace('<meta property="og:image" content="https://founderledequities.com/og.png">',
                         f'<meta property="og:image" content="{url}">')
                .replace('<meta name="twitter:image" content="https://founderledequities.com/og.png">',
                         f'<meta name="twitter:image" content="{url}">'))


def main(panel_p, founders_p, prices_p, sp_p, out_dir, events_p="events.csv", hist_p="history.csv",
         og_dir=None, prices_dir=None):
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    index_html = open(os.path.join(root, "index.html"), encoding="utf-8").read()
    template = open(os.path.join(root, "company.html"), encoding="utf-8").read()
    page_js = open(os.path.join(root, "assets", "company-page.js"), encoding="utf-8").read()

    shared = extract_shared(index_html)
    header = ('/* generated by ops/build_company_pages.py -- do not edit; the source is\n'
              '   index.html (the declarations marked @shared) and assets/company-page.js */\n'
              'let PANEL=[],HIST={},PRICES={},PRICES_ASOF="",FOUNDERS={},EVENTS=[];\n'
              'const state={pro:false,live:{}};\n')
    os.makedirs(out_dir, exist_ok=True)
    js_text = header + shared + "\n\n" + page_js
    css_text = extract_style(index_html)
    with open(os.path.join(out_dir, "company.js"), "w", encoding="utf-8") as fh:
        fh.write(js_text)
    with open(os.path.join(out_dir, "site.css"), "w", encoding="utf-8") as fh:
        fh.write(css_text)
    # A NEW SCRIPT IS A NEW ADDRESS. Browsers and the edge cache company.js
    # and site.css by name; a deploy that changed them was served stale
    # under the new HTML, and the page rendered unstyled. The pages point
    # at company.js?v=<hash> and site.css?v=<hash>, so a change is fetched.
    js_v = hashlib.sha256(js_text.encode("utf-8")).hexdigest()[:10]
    css_v = hashlib.sha256(css_text.encode("utf-8")).hexdigest()[:10]
    # THE TAPE AS A PAGE (PLAN.md section 5): /tape/ is the same block the
    # home page carries, built from the same shared declarations plus its
    # own script, with the Monday-tape signup beside it.
    tape_tpl_p = os.path.join(root, "tape.html")
    tape_js_p = os.path.join(root, "assets", "tape-page.js")
    if os.path.exists(tape_tpl_p) and os.path.exists(tape_js_p):
        tape_js = header + shared + "\n\n" + open(tape_js_p, encoding="utf-8").read()
        tape_v = hashlib.sha256(tape_js.encode("utf-8")).hexdigest()[:10]
        with open(os.path.join(out_dir, "tape.js"), "w", encoding="utf-8") as fh:
            fh.write(tape_js)
        tape_html = (open(tape_tpl_p, encoding="utf-8").read()
                     .replace("{{TOPNAV}}", extract_topnav(index_html))
                     .replace('href="/site.css"', f'href="/site.css?v={css_v}"')
                     .replace('src="/tape.js"', f'src="/tape.js?v={tape_v}"'))
        os.makedirs(os.path.join(out_dir, "tape"), exist_ok=True)
        with open(os.path.join(out_dir, "tape", "index.html"), "w", encoding="utf-8") as fh:
            fh.write(tape_html)
    # THE COMPANIES PAGE'S SCRIPT (PLAN.md section 5): the shared block
    # plus its own; the page itself is assembled in companies_index
    co_js_p = os.path.join(root, "assets", "companies-page.js")
    if os.path.exists(co_js_p):
        co_js = header + shared + "\n\n" + open(co_js_p, encoding="utf-8").read()
        with open(os.path.join(out_dir, "companies.js"), "w", encoding="utf-8") as fh:
            fh.write(co_js)
    # THE WATCHES PAGE: static shell, its own small script, the masthead
    w_tpl_p = os.path.join(root, "watches.html")
    w_js_p = os.path.join(root, "assets", "watches-page.js")
    if os.path.exists(w_tpl_p) and os.path.exists(w_js_p):
        w_js = open(w_js_p, encoding="utf-8").read()
        with open(os.path.join(out_dir, "watches.js"), "w", encoding="utf-8") as fh:
            fh.write(w_js)
        w_v = hashlib.sha256(w_js.encode("utf-8")).hexdigest()[:10]
        w_html = (open(w_tpl_p, encoding="utf-8").read()
                  .replace("{{TOPNAV}}", extract_topnav(index_html))
                  .replace('href="/site.css"', f'href="/site.css?v={css_v}"')
                  .replace('src="/watches.js"', f'src="/watches.js?v={w_v}"'))
        os.makedirs(os.path.join(out_dir, "watches"), exist_ok=True)
        with open(os.path.join(out_dir, "watches", "index.html"), "w", encoding="utf-8") as fh:
            fh.write(w_html)
    # THE PRO PAGE (PLAN.md section 5): static, the masthead from index.html
    pro_tpl_p = os.path.join(root, "pro.html")
    if os.path.exists(pro_tpl_p):
        pro_html = (open(pro_tpl_p, encoding="utf-8").read()
                    .replace("{{TOPNAV}}", extract_topnav(index_html))
                    .replace('href="/site.css"', f'href="/site.css?v={css_v}"'))
        os.makedirs(os.path.join(out_dir, "pro"), exist_ok=True)
        with open(os.path.join(out_dir, "pro", "index.html"), "w", encoding="utf-8") as fh:
            fh.write(pro_html)
    topnav = extract_topnav(index_html)

    sp = {r["ticker"].upper() for r in csv.DictReader(open(sp_p, encoding="utf-8-sig"))}
    prices, price_date = {}, ""
    try:
        for r in csv.DictReader(open(prices_p, encoding="utf-8-sig")):
            p = num(r.get("close"))
            if p:
                prices[r["ticker"].upper()] = p
                price_date = max(price_date, r.get("as_of") or r.get("date") or "")
    except OSError:
        pass
    founders = {}
    try:
        for r in csv.DictReader(open(founders_p, encoding="utf-8-sig")):
            founders[r["ticker"].upper()] = {"f": (r.get("founder") or "").lower(),
                                             "ev": r.get("evidence") or "", "src": r.get("source") or ""}
    except OSError:
        pass

    ev, hist = load_summaries(events_p, hist_p)
    # THE 1Y RETURN IS THE LIST'S: one function (build_site_data.one_year_returns),
    # one store, so the figure on a company page is the figure in the table.
    ret_1y = {}
    if prices_dir:
        from build_site_data import one_year_returns
        ret_1y = one_year_returns(prices_dir, [(r.get("ticker") or "").upper()
                                              for r in csv.DictReader(open(panel_p, encoding="utf-8-sig"))])
    # the founder-led companies ranked by stake value, for the neighbour links;
    # the names for those links; and per company, how many filings the
    # history walk saw (a count a sealed page may say)
    panel_rows = [r for r in csv.DictReader(open(panel_p, encoding="utf-8-sig"))
                  if re.match(r"^[A-Z0-9.\-]{1,8}$", (r.get("ticker") or "").upper())]
    ranked = sorted((r for r in panel_rows
                     if (founders.get((r.get("ticker") or "").upper()) or {}).get("f") == "yes"
                     and num(r.get("shares")) and prices.get((r.get("ticker") or "").upper())),
                    key=lambda r: -(num(r.get("shares")) * prices[(r.get("ticker") or "").upper()]))
    ranked = [(r.get("ticker") or "").upper() for r in ranked]
    NAMES.clear()
    NAMES.update({(r.get("ticker") or "").upper(): (r.get("company") or "") for r in panel_rows})
    filings, last_filed = {}, {}
    try:
        for r in csv.DictReader(open(hist_p, encoding="utf-8-sig")):
            t = (r.get("ticker") or "").upper()
            # filings by the person: every row that is not a cover page
            if t and not (r.get("form") or "").startswith(("10-", "20-", "40-")):
                filings[t] = filings.get(t, 0) + 1
                if (r.get("date") or "") > last_filed.get(t, ""):
                    last_filed[t] = r.get("date") or ""
    except OSError:
        pass
    # the scale a sealed page offers: in the free set, how many own more than 5%
    sp_rows = [r for r in panel_rows if (r.get("ticker") or "").upper() in sp and num(r.get("pct")) is not None]
    scale = (sum(1 for r in sp_rows if num(r.get("pct")) > 5), len(sp_rows)) if sp_rows else None
    urls = []
    lastmods = {}
    index_rows = []
    n_open = n_sealed = 0
    for r in panel_rows:
        tk = (r.get("ticker") or "").upper()
        if not tk or not re.match(r"^[A-Z0-9.\-]{1,8}$", tk):
            continue
        is_sp = tk in sp
        price = prices.get(tk)
        title, desc = page_text(r, is_sp, price)
        payload = {"tk": tk, "co": r.get("company") or tk, "ceo": r.get("ceo") or "", "sp": is_sp,
                   "founder": founders.get(tk)}
        e_sum = ev.get(tk) or {}
        if e_sum.get("older"):
            payload["older"] = e_sum["older"]        # trades before the free year: the archive, in Pro
            payload["since"] = (e_sum.get("first") or "")[:4]
        if is_sp:
            row = {k: r.get(k, "") for k in ("ticker", "company", "ceo", "pct", "shares", "outstanding",
                                             "shares_as_of", "confidence", "cik", "form4_url",
                                             "excluded_shares", "excluded_detail", "problems", "cautions",
                                             "operating_partnership", "stake_source")}
            if ret_1y and tk in ret_1y:
                row["ret_1y"] = f"{ret_1y[tk]:.4f}"
            payload["row"] = row
            n_open += 1
        else:
            n_sealed += 1
            # the cover page's count is public; the page shows it in its card
            payload["out"] = num(r.get("outstanding"))
            payload["oasof"] = r.get("outstanding_as_of") or ""
        if price:   # the close is public data; a sealed page carries it and no shares
            payload["price"] = price
            payload["price_date"] = price_date
        index_rows.append({"tk": tk, "co": payload["co"], "ceo": payload["ceo"]})
        body = static_body(payload, r, is_sp, price, price_date, ev, hist, founders.get(tk), filings.get(tk, 0), ret_1y,
                           last_filed=last_filed.get(tk, ""), scale=scale,
                           price_svg=(price_line_svg(prices_dir, tk) if not is_sp else ""))
        lastmods[tk] = (r.get("shares_as_of") or "")[:10]
        crumbs = json.dumps({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Founder Led Equities", "item": f"{SITE}/"},
            {"@type": "ListItem", "position": 2, "name": "Every company", "item": f"{SITE}/companies/"},
            {"@type": "ListItem", "position": 3, "name": payload["co"], "item": f"{SITE}/company/{tk}/"}]})
        page = (template
                .replace('<div id="cbody"></div>', '<div id="cbody">' + body + '</div>')
                .replace('<div id="cmore"></div>', '<div id="cmore">' + neighbours_html(tk, ranked, sp) + '</div>')
                .replace('</head>', f'<script type="application/ld+json">{crumbs}</script>\n</head>')
                .replace("{{TITLE}}", html.escape(title))
                .replace("{{DESCRIPTION}}", html.escape(desc))
                .replace("{{TICKER}}", html.escape(tk))
                .replace("{{MCAP}}", kicker_mcap(r, price))
                .replace("{{COMPANY}}", html.escape(payload["co"]))
                .replace("{{CEO}}", html.escape(payload["ceo"]))
                .replace("{{TOPNAV}}", topnav)
                .replace('href="/site.css"', f'href="/site.css?v={css_v}"')
                .replace('src="/company.js"', f'src="/company.js?v={js_v}"')
                .replace("{{COMPANY_JSON}}", json.dumps(payload).replace("</", "<\\/")))
        page = card_tags(page, tk, og_dir)
        # A SEALED PAGE IS A SEARCH RESULT AGAIN, now that it answers what it
        # can: the question as its heading, the chief executive, the founder
        # sentence, the filings on record, the price, the market cap, the
        # year's return, and the honest sentence about where the stake is.
        d = os.path.join(out_dir, "company", tk)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as fh:
            fh.write(page)
        urls.append(f"{SITE}/company/{tk}/")

    companies_index(index_rows, founders, sp, out_dir, topnav, css_v)
    urls.append("https://founderledequities.com/companies/")
    with open(os.path.join(out_dir, "sitemap.xml"), "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        today = datetime.date.today().isoformat()
        for u in [f"{SITE}/", f"{SITE}/tape/", f"{SITE}/pro/", f"{SITE}/about.html"] + urls:
            m = re.search(r"/company/([A-Z0-9.\-]+)/$", u)
            lm = (lastmods.get(m.group(1)) if m else "") or today
            fh.write(f"  <url><loc>{html.escape(u)}</loc><lastmod>{lm}</lastmod></url>\n")
        fh.write("</urlset>\n")
    with open(os.path.join(out_dir, "robots.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"User-agent: *\nAllow: /\nDisallow: /pro/\nDisallow: /api/\nSitemap: {SITE}/sitemap.xml\n")
    print(f"  company pages: {n_open} open, {n_sealed} sealed; company.js, site.css, sitemap.xml, robots.txt")
    return 0


if __name__ == "__main__":
    argv = list(sys.argv[1:])
    og_dir = None
    if "--og" in argv:
        i = argv.index("--og")
        og_dir = argv[i + 1]
        del argv[i:i + 2]
    prices_dir = None
    if "--prices" in argv:
        i = argv.index("--prices")
        prices_dir = argv[i + 1]
        del argv[i:i + 2]
        del argv[i:i + 2]
    raise SystemExit(main(*argv[:7], og_dir=og_dir, prices_dir=prices_dir))
