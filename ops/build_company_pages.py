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

EVERY PAGE CARRIES ITS NUMBERS IN THE HTML (the tiers left 2026-09-23):
the stake, the shares, the worth and the KPI cards are baked in; company.js
fills the record, the trades and the prices in from the one data tree.
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
    # links become absolute, back to the home page's sections; the search
    # box and its /search.js ride along, the same on every built page
    nav = nav.replace('href="#', 'href="/#').replace('href="about.html"', 'href="/about.html"')
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


_SUFFIX = re.compile(r"[,\s]+(?:INCORPORATED|INC\.?|CORPORATION|CORP\.?|CO\.?|COMPANY|LTD\.?|LIMITED|PLC|L\.?P\.?|LLC|N\.?V\.?|S\.?A\.?|/DE/?|/MD/?|/NEW/?)\s*$", re.I)
_INITIALISM = re.compile(r"^(?:[B-DF-HJ-NP-TV-Z&]{2,4}|[A-Z]{1,3}\d[A-Z0-9]*)$")   # PVH, KBR, HNI, 3M: no vowel, cannot be a word


def display_name(co: str) -> str:
    """THE NAME A PERSON WOULD TYPE, from EDGAR's legal one, by rule and not
    by list: the corporate suffix stripped ("Tesla, Inc." -> "Tesla",
    "UWM Holdings Corp" -> "UWM Holdings"), all-caps legal names given
    their case ("NVIDIA CORP" -> "Nvidia"), short all-caps words kept as
    they are (AMD, IBM). Used in titles and descriptions; the record on the
    page keeps the legal name."""
    name = (co or "").strip()
    stripped = name
    for _ in range(2):
        stripped = _SUFFIX.sub("", stripped).strip(" ,")
    if stripped:
        name = stripped
    if name.isupper() and len(name) > 3:
        cased = []
        for w in name.split():
            if _INITIALISM.match(w) or re.fullmatch(r"[IVX]+", w) or "&" in w:
                cased.append(w)             # PVH, DXP, W R Berkley's initials, G III, AT&T
            else:
                cased.append("-".join(part.capitalize() for part in w.split("-")))   # BIO-RAD -> Bio-Rad
        name = " ".join(cased)
    return name or (co or "")


def page_text(r, price):
    """Title and description: the number when the record settles on one, the
    question verbatim when it does not. The company's name is the one a
    person would type (display_name)."""
    ceo, co, tk = r["ceo"] or "The chief executive", display_name(r["company"] or r["ticker"]), r["ticker"]
    pct = num(r.get("pct"))
    if pct is not None:
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
        desc = (f"{ceo} is the chief executive of {co}. The stake this site computes from SEC filings "
                f"has not settled on a single figure for this company; the price, the market cap and "
                f"every filing on record are here.")
    return title, desc[:300]


def answer_text(r, price):
    """THE H1 AND THE FIRST SENTENCE (2026-09-24): the answer to the question
    the searcher typed, in the static HTML. With a number: "Elon Musk owns
    28.44% of Tesla" and the shares, the date and the value. Without one:
    the question as the heading and an honest sentence."""
    ceo = r["ceo"] or "The chief executive"
    co = display_name(r["company"] or r["ticker"])
    pct = num(r.get("pct"))
    sh = num(r.get("shares")) or 0
    if pct is not None:
        h1 = f"{ceo} owns {pct:.2f}% of {co}"
        when = r.get("shares_as_of") or ""
        try:
            nice = datetime.date.fromisoformat(when).strftime("%B %-d, %Y") if when else ""
        except ValueError:
            nice = when
        val = f", worth {money(sh * price)} at the latest close" if price and sh else ""
        # THE SENTENCE IS THE FACT (2026-09-23): the shares, the date, the value.
        # The method ("computed from every filing, never estimated") is the
        # footer's line on every page; said beside the answer it was furniture.
        ans = f"{sh:,.0f} shares{' as of the ' + html.escape(nice) + ' filing' if nice else ''}{val}."
    else:
        h1 = f"How much of {co} does {ceo} own?"
        ans = (f"The filings on record do not state a share count the site can stand behind; the reasons are below. "
               f"The company's price, market cap and every filing are here.")
    return h1, ans


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
            d = ev.setdefault(tk, {"buys": 0, "sells": 0, "last": None, "first": "",
                                   "last_sale": None, "last_buy": None})
            d["buys" if r["code"] == "P" else "sells"] += 1
            fd = r.get("filed") or ""
            if not d["first"] or fd < d["first"]:
                d["first"] = fd
            key = (r.get("traded") or r.get("filed") or "", r.get("filed") or "")
            if d["last"] is None or key > d["last"][0]:
                d["last"] = (key, r)
            # THE TWO CLOCKS (2026-09-23): the page's cards say how long since
            # he last sold and last bought, so the newest of each is kept --
            # the same rows the counts above count, nothing reinterpreted.
            side = "last_buy" if r["code"] == "P" else "last_sale"
            if d[side] is None or key > d[side][0]:
                d[side] = (key, r)
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
    page (the badge's receipt): the words behind the founder verdict."""
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


def kicker_mcap(r, price) -> str:
    """The market cap beside the ticker, beside the name, SAYING WHAT IT IS
    (2026-09-23): "$1.50T" alone read as anything. The tk span's small caps
    set "mkt cap" in the same register. Public data, so every page carries
    it too."""
    out = num(r.get("outstanding"))
    return f" · {money(out * price)} market cap" if (price and out) else ""


def founder_row(founder) -> str:
    """The badge alone (2026-09-24): the clay tag rides the kicker line
    after the market cap. The proxy quote and its link left the page --
    the badge asserts, the site's record earns the trust. The evidence
    stays in founders.csv and in the export for anyone who asks."""
    if not founder or (founder.get("f") or founder.get("founder") or "").lower() != "yes":
        return ""
    return ' &middot; <span class="kbadge">Founder-led</span>'


def _hdate(d):
    """'2026-07-31' -> 'Jul 31, 2026'; '' stays ''."""
    try:
        import datetime as _dt
        t = _dt.date.fromisoformat(d[:10])
        return t.strftime("%b %-d, %Y") if os.name != "nt" else t.strftime("%b %d, %Y")
    except Exception:
        return d


def held_section(tk, rows, shares, co="", pct=None, cik=""):
    """HOW THE STAKE IS HELD (2026-09-25, regrouped 2026-09-25b): the
    position statement. Classes first, each band with its own subtotal,
    share of the stake, and the filing that last stated it (one section
    date could not speak for DELL's two classes, a year apart). Inside a
    class the direct line, then the indirect vehicles -- behind an
    'HELD INDIRECTLY' sub-band with subtotal when there are two or more.
    Past six vehicles in one group, the tail folds. The double rule closes
    the account: THE STAKE, bold shares, the percent in clay. Renders ONLY
    when the rows sum to the published stake (the ledger's warranty,
    enforced here): excluded, not guessed."""
    try:
        want = float(str(shares).replace(",", ""))
    except Exception:
        return ""
    if not rows or not want:
        return ""
    try:
        tot = sum(float(x.get("shares") or 0) for x in rows)
    except Exception:
        return ""
    if abs(tot - want) > max(1.0, want * 0.001):
        return ""

    def f(x):
        return float(x.get("shares") or 0)

    def stale_suffix(x):
        if str(x.get("stale") or "") == "1" and (x.get("as_of") or "")[:7]:
            return f" &middot; last stated {html.escape(_hdate(x['as_of'])[:3])} {x['as_of'][:4]}"
        return ""

    def row_html(x, text, indent):
        cls = "hrow" + (" hstale" if str(x.get("stale") or "") == "1" else "")
        veh = ('<div class="hveh hind">' if indent else '<div class="hveh">') \
            + text + stale_suffix(x) + "</div>"
        return (f'<div class="{cls}">' + veh
                + f'<div class="hsh">{int(f(x)):,}</div>'
                + f'<div class="hpc">{x.get("pct_of_stake") or ""}%</div></div>')

    # the classes, largest first, each as its filings last stated it
    by_k, order = {}, []
    for x in rows:
        k = x.get("klass") or "Common stock"
        if k not in by_k:
            by_k[k] = []
            order.append(k)
    for x in rows:
        by_k[x.get("klass") or "Common stock"].append(x)
    order.sort(key=lambda k: -sum(f(x) for x in by_k[k]))

    def flink(acc):
        a = (acc or "").replace("-", "")
        if a and cik:
            return (f' &middot; <a href="https://www.sec.gov/Archives/edgar/data/'
                    f'{int(cik)}/{a}/" target="_blank" rel="noopener">Form 4 &nearr;</a>')
        return ""

    parts = []
    for k in order:
        grp = sorted(by_k[k], key=lambda x: -f(x))
        gsum = sum(f(x) for x in grp)
        newest = max(grp, key=lambda x: (x.get("as_of") or ""))
        lab = (html.escape(k).upper() + ' <span class="hcd">&middot; stated '
               + html.escape(_hdate((newest.get('as_of') or '')[:10]))
               + flink(newest.get("accession")) + '</span>')
        nums = (f'<div class="hsh">{int(gsum):,}</div>'
                f'<div class="hpc">{gsum / want * 100:.1f}%</div>') if len(order) > 1 else                '<div class="hsh"></div><div class="hpc"></div>'
        parts.append('<div class="hcband"><div class="hcl">' + lab + '</div>' + nums + '</div>')
        # TWO MANNERS, ONE GRAMMAR (2026-09-25c): direct and indirect are
        # sibling bands; plain rows are reserved for actual vehicles, listed
        # only when there are two or more to enumerate. Direct ownership has
        # no vehicle -- it is shares in the person's own name -- so its band
        # is its number, and nothing is invented to fill a column.
        direct = [x for x in grp if (x.get("di") or "").upper() != "I"
                  and (x.get("vehicle") or "").lower().startswith("held directly")]
        indirect = [x for x in grp if x not in direct]

        def band(label, xs, name=None):
            bsum = sum(f(x) for x in xs)
            stale = all(str(x.get("stale") or "") == "1" for x in xs)
            lab = label + ('' if name is None else ' &middot; <span class="hvn">'
                           + html.escape(name) + '</span>' + stale_suffix(xs[0]))
            return ('<div class="hsub' + (' hstale' if stale else '') + '">'
                    + f'<div class="hveh">{lab}</div><div class="hsh">{int(bsum):,}</div>'
                    + f'<div class="hpc">{bsum / want * 100:.1f}%</div></div>')

        if direct:
            parts.append(band("HELD DIRECTLY", direct))
        if len(indirect) >= 2:
            parts.append(band(f"HELD INDIRECTLY &middot; {len(indirect)} VEHICLES", indirect))
            for x in indirect[:6]:
                parts.append(row_html(x, html.escape(x.get("vehicle") or ""), True))
            rest = indirect[6:]
            if rest:
                rest_sum = int(sum(f(x) for x in rest))
                parts.append(
                    f'<button class="chip hmore" onclick="HELD_ALL=true;renderOpen(PANEL[0])">'
                    f'{len(rest)} more vehicle{"" if len(rest) == 1 else "s"} &middot; '
                    f'{rest_sum:,} shares &darr;</button>')
        elif indirect:
            parts.append(band("HELD INDIRECTLY", indirect,
                              name=indirect[0].get("vehicle") or "per the filing"))

    try:
        pct_s = f"{float(pct):.2f}%"
    except (TypeError, ValueError):
        pct_s = ""
    total = ('<div class="htot"><div class="htl">THE STAKE</div>'
             + f'<div class="hsh">{int(tot):,}</div><div class="hpc">{pct_s}</div></div>')
    hasof = ("each class as its filings last stated it" if len(order) > 1 else
             f"as of the {html.escape(_hdate(max((x.get('as_of') or '')[:10] for x in rows)))} filing")
    return (
        '<section class="csec chold" id="chold">'
        + '<div class="cshead"><h2>How the stake is held</h2>'
        + f'<div class="hasof">{hasof}</div></div>'
        + '<div class="hbox"><div class="hhead">'
        + '<div class="hveh">HOW IT IS HELD</div>'
        + '<div class="hsh">SHARES</div><div class="hpc">OF THE STAKE</div></div>'
        + "".join(parts) + total + '</div>'
        + '</section>')


def static_body(payload, r, price, price_date, ev, hist, founder, n_filings=0, ret_1y=None,
                last_filed="", scale=None):
    """THE PAGE SAYS ITS NUMBERS IN HTML. A fetch without scripts (a
    crawler's first pass, an assistant, a reader in the second before the
    data arrives) read a name and a footer; the stake, the value, the
    record and the last trade all arrived by script. Now the answer band
    and a paragraph are written into the page; the script redraws over
    them."""
    co = html.escape(payload["co"]); ceo = html.escape(payload["ceo"] or "the chief executive")
    fsent = ""
    if founder and founder.get("f") == "yes":
        fsent = ""
    elif founder and founder.get("f") == "uncertain":
        fsent = ""
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
    # THREE CARDS, LABEL FIRST (2026-09-23): the share, the shares and the
    # worth all live in the H1 and the first sentence now, so the cards say
    # what the sentence does not: the stake's rank by dollar value, and how
    # long since the chief executive last sold and last bought. The label is
    # the card's name; the date is the fine print; the script redraws the
    # day counts from the reader's own day.
    e0 = ev.get(payload["tk"]) or {}
    today = datetime.date.today()

    def clock(side):
        hit = e0.get(side)
        if not hit:
            since = (e0.get("first") or "2016")[:4] or "2016"
            return "None", f"no {'sales' if side == 'last_sale' else 'purchases'} since {since}"
        lr = hit[1]
        d = lr.get("traded") or lr.get("filed") or ""
        try:
            days = (today - datetime.date.fromisoformat(d)).days
            v = f'{days:,}<small> days ago</small>'
        except ValueError:
            v = html.escape(d)
        val = num(lr.get("value"))
        try:
            nice = datetime.date.fromisoformat(d).strftime("%b %-d, %Y")
        except ValueError:
            nice = d
        # the sale's fine print is its date; the buy carries its size too (design v4)
        return v, html.escape(nice) + (f" · {money(val)}" if val and side == "last_buy" else "")

    sv, ss = clock("last_sale")
    bv, bs = clock("last_buy")
    rank = payload.get("rank")
    # THE STAKE LEADS THE CARDS (2026-09-24): the same clay figure the home
    # page's stakes cards teach, first in the row; the worth is its caption.
    wsub = (f"worth {money(sh * price)} at the latest close" if price and sh else "of the common shares")
    band = ('<div class="cband kpi">'
            + stat("The stake", f"{pct:.2f}%", "clay", wsub)
            + stat("Stake rank", f"#{rank:,}" if rank else "&mdash;", "", "by dollar value of the stake")
            + stat("Last sale", sv, "", ss)
            + stat("Last buy", bv, "", bs)
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
.screendef{font-size:15.5px;line-height:1.55;color:var(--mut);max-width:72ch;margin:8px 0 0}
.sstatic table.stable{width:100%;border-collapse:collapse;font-size:14px;font-variant-numeric:tabular-nums}
.sstatic table.stable th{text-align:left;font-family:var(--ui);font-size:12.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ink);padding:0 10px 10px 0;border-bottom:1px solid var(--ink)}
.sstatic table.stable td{padding:10px 10px 10px 0;border-bottom:1px solid var(--line);vertical-align:middle;color:var(--ink)}
.sstatic table.stable td.n,.sstatic table.stable th.n{text-align:right;white-space:nowrap;padding-right:28px}
.sstatic table.stable td.tk a{font-weight:700;color:var(--ink);text-decoration:none}
.sstatic table.stable td.tk .co{color:var(--mut);margin-left:8px}
.sstatic .fb{font-family:var(--mono);font-size:9.5px;letter-spacing:.08em;background:var(--ink);color:var(--bg);padding:1px 5px;border-radius:2px;vertical-align:middle;margin-left:8px}

.cidx{padding:32px 0 60px}.cidx h1{font-family:var(--disp);font-size:clamp(28px,4vw,44px);font-weight:650;letter-spacing:-.02em;margin:0 0 8px}
.cidx .sub{color:var(--mut);margin-bottom:18px}.cidx .letters{font-family:var(--mono);font-size:13px;display:flex;flex-wrap:wrap;gap:10px;margin-bottom:24px}.cidx .letters a{color:var(--blue);text-decoration:none}
.cidx section{margin-top:22px}.cidx h2{font-family:var(--mono);font-size:13px;color:var(--faint);letter-spacing:.14em;margin:0 0 8px}
.cidx ul{list-style:none;margin:0;padding:0;columns:3;column-gap:32px}.cidx li{break-inside:avoid;padding:4px 0;font-size:13.5px}
.cidx li a{font-family:var(--mono);font-weight:600;color:var(--blue);text-decoration:none}.cidx .co{color:var(--ink)}.cidx .ceo{color:var(--mut)}
.cidx .seal{font-family:var(--mono);font-size:10px;color:var(--faint);border:1px solid var(--line);border-radius:4px;padding:1px 5px;margin-left:4px}
@media(max-width:900px){.cidx ul{columns:2}}@media(max-width:560px){.cidx ul{columns:1}}
""")


def neighbours_html(tk, ranked, sp, k=2):
    """KEEP READING (design v4): a labeled row of chips, each a sentence a
    reader might follow -- the tape, up to two neighbouring founders' own
    stake sentences (the cross-links the old list carried), the founder-led
    screen with its count, and the letter. Every page gets the row; only
    the neighbour chips need the ranked list."""
    chips = ['<a href="/tape/">Founders who bought this week &rarr;</a>']
    if ranked:
        if tk in ranked:
            i = ranked.index(tk)
            cand = [t for t in ranked[max(0, i - 12): i + 13] if t != tk]
            cand.sort(key=lambda t: (t not in sp, abs(ranked.index(t) - i)))
        else:
            cand = [t for t in ranked if t != tk]
        for t in cand[:k]:
            ceo, pct = CEOS.get(t, ""), PCTS.get(t)
            co = display_name(NAMES.get(t) or t)
            if ceo and pct is not None:
                chips.append(f'<a href="/company/{html.escape(t)}/">{html.escape(ceo)} owns {pct:.2f}% of {html.escape(co)} &rarr;</a>')
            else:
                chips.append(f'<a href="/company/{html.escape(t)}/">{html.escape(co)} &rarr;</a>')
        chips.append(f'<a href="/screens/founder-led/">All {len(ranked):,} founder-led companies &rarr;</a>')
    chips.append('<a href="/letter/">The weekly letter &rarr;</a>')
    return f'<div class="cmore"><div class="k">Keep reading</div><div class="chiprow">{"".join(chips)}</div></div>'


NAMES = {}
CEOS = {}
PCTS = {}


# THE SCREENS AS PAGES (2026-09-18): the reference's list pages. The Companies
# page's screens are query strings a crawler folds into /companies/; these are
# five addresses with the table in the HTML, each titled with the question
# people type, defined in one sentence exactly as the site computes it, sorted
# by stake value, every row a link to its company page. Built from the site's
# own universe.csv (build_site_data), so a screen page and the interactive
# screen agree to the row.
# THE SCREENS ARE PRESETS (2026-09-21): each page is one setting of the
# Companies page's five groups, tested here with the same rule the page and
# the count file use (who runs it; the index; owns at least; years since the
# last discretionary sale; years since the last open-market buy). The record
# starts in 2016, and the words say so where it matters.
def _years_since(day):
    if not day:
        return None
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(day[:10])).days / 365.25
    except ValueError:
        return None


SCREENS = [
    ("founder-led", "Founder-led companies",
     "US public companies worth $1B or more whose chief executive founded them, by the company's own proxy statement, with what each founder owns today",
     lambda r, f: f),
    ("never-sold", "CEOs with no discretionary sale since 2016",
     "chief executives who have not sold a share of their company at their own discretion since 2016, the start of the record: every Form 4 they signed, with sales on a Rule 10b5-1 plan set aside",
     lambda r, f: not (r.get("last_disc") or "") and ((r.get("never_sold") or "") == "1" or (r.get("lt_code") or "") != "")),
    ("own-more-than-10-percent", "CEOs who own more than 10% of their company",
     "chief executives whose stake is a tenth of the company or more, counted from the filings they signed",
     lambda r, f: _num(r.get("pct")) is not None and _num(r.get("pct")) >= 10),
    ("bought-this-year", "CEOs who bought shares this year",
     "chief executives who bought their company's shares on the open market in the last year, with their own money",
     lambda r, f: (_years_since(r.get("last_buy")) or 99) < 1),
    ("hired-under-1-percent", "Hired CEOs who own less than 1%",
     "chief executives the proxy statement does not name as founders, owning less than one percent of the company they run",
     lambda r, f: (not f) and _num(r.get("pct")) is not None and _num(r.get("pct")) < 1),
]

SCREEN_CSS = """
.spage{max-width:var(--max);margin:0 auto;padding:clamp(28px,4vw,52px) clamp(20px,3.5vw,48px) 72px}
.spage h1{font-family:var(--disp);font-weight:500;letter-spacing:-.02em;line-height:1.05;font-size:clamp(32px,4.4vw,56px);margin:0 0 10px}
.spage .def{font-size:15.5px;line-height:1.55;color:var(--mut);max-width:72ch;margin:0 0 6px}
.spage .meta{font-family:var(--mono);font-size:12px;color:var(--faint);margin:0 0 22px}
.spage .meta a{color:var(--mut)}
.spage table{width:100%;border-collapse:collapse;font-size:14px;font-variant-numeric:tabular-nums}
.spage th{text-align:left;font-family:var(--ui);font-size:12.5px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--ink);padding:0 10px 10px 0;border-bottom:1px solid var(--ink)}
.spage td{padding:10px 10px 10px 0;border-bottom:1px solid var(--line);vertical-align:middle;font-size:14px;color:var(--ink)}
.spage td.n,.spage th.n{text-align:right;white-space:nowrap;padding-right:28px}
.spage td.tk a{font-weight:700;color:var(--ink);text-decoration:none}
.spage td.tk .co{color:var(--mut);margin-left:8px}
.spage .fb{font-family:var(--mono);font-size:9.5px;letter-spacing:.08em;background:var(--ink);color:var(--bg);padding:1px 5px;border-radius:2px;vertical-align:middle;margin-left:8px}
.spage .others{margin:36px 0 0;font-size:14px;color:var(--mut)}
.spage .others a{color:var(--ink);margin-right:14px}
@media(max-width:760px){.spage th.mc,.spage td.mc,.spage th.c12,.spage td.c12{display:none}}
"""


PRESET = {"founder-led": "founder-led", "never-sold": "never-sold", "own-more-than-10-percent": "over-10",
          "bought-this-year": "bought-this-year", "hired-under-1-percent": "hired-under-1"}


def screen_pages(universe_p, founders, prices, out_dir, topnav, css_v, index_rows=None, sp=None):
    """-> the list of screen URLs written. Reads the site's universe.csv; when
    it is absent (a test build without the site data) writes nothing."""
    if not os.path.exists(universe_p):
        return []
    rows = list(csv.DictReader(open(universe_p, encoding="utf-8-sig")))
    urls = []
    today = datetime.date.today().isoformat()
    def worth(r):
        sh, px = _num(r.get("shares")), prices.get((r.get("ticker") or "").upper())
        return sh * px if sh is not None and px else None
    for slug, title, definition, test in SCREENS:
        picked = []
        for r in rows:
            tk = (r.get("ticker") or "").upper()
            f = (founders.get(tk) or {}).get("f") == "yes"
            try:
                if test(r, f):
                    picked.append((r, f))
            except Exception:  # noqa: BLE001
                continue
        picked.sort(key=lambda x: -(worth(x[0]) or 0))
        trs = []
        for r, f in picked:
            tk = (r.get("ticker") or "").upper()
            pct = _num(r.get("pct")); w = worth(r)
            ago = _num(r.get("pct_12m_ago"))
            agos = "" if ago is None else (f"{ago:.3f}%" if ago < 1 else f"{ago:.2f}%")
            trs.append(f'<tr><td class="tk"><a href="/company/{html.escape(tk)}/">{html.escape(tk)}</a><span class="co">{html.escape(r.get("company") or "")}</span></td>'
                       f'<td>{html.escape(r.get("ceo") or "")}{"<span class=\"fb\">FOUNDER</span>" if f else ""}</td>'
                       f'<td class="n">{"" if pct is None else (f"{pct:.3f}%" if pct < 1 else f"{pct:.2f}%")}</td>'
                       f'<td class="n c12">{agos}</td>'
                       f'<td class="n">{"" if w is None else _money(w)}</td></tr>')
        others = " ".join(f'<a href="/screens/{o_slug}/">{html.escape(o_title)}</a>' for o_slug, o_title, _d, _t in SCREENS if o_slug != slug)
        desc = f"{len(picked):,} {definition}. Computed from SEC filings, updated nightly."
        static_table = (f'<div class="sstatic" id="sstatic"><div class="wrap"><p class="meta" style="font-family:var(--mono);font-size:12px;color:var(--faint);margin:28px 0 10px">The list, as of {today}, sorted by the value of the stake</p>'
                        f'<table class="stable"><thead><tr><th>Company</th><th>CEO</th><th class="n">Stake</th><th class="n c12">A year ago</th><th class="n">Worth</th></tr></thead>'
                        f'<tbody>{"".join(trs)}</tbody></table>'
                        f'<p class="others" style="margin:28px 0 0;font-size:14px;color:var(--mut)">Other screens: {others}</p></div></div>')
        if _PAGE_FN is not None:
            # ONE SCREEN, ONE ADDRESS (2026-09-18): the Companies page itself, preset to the question, with the
            # rows in the HTML beneath so a crawler reads them and the reader gets the sortable table above
            page = _PAGE_FN(title, definition, PRESET[slug], static_table, title, desc, f"{SITE}/screens/{slug}/")
        else:
            page = (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                    f'<title>{html.escape(title)} · Founder Led Equities</title>'
                    f'<meta name="description" content="{html.escape(desc[:300])}">'
                    f'<link rel="canonical" href="{SITE}/screens/{slug}/">'
                    f'<link rel="stylesheet" href="/site.css?v={css_v}"><style>{SCREEN_CSS}</style></head><body>\n{topnav}\n'
                    f'<main class="spage"><h1>{html.escape(title)}</h1><p class="def">{len(picked):,} {html.escape(definition)}.</p>'
                    f'{static_table}</main></body></html>\n')
        d = os.path.join(out_dir, "screens", slug)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as fh:
            fh.write(page)
        urls.append(f"{SITE}/screens/{slug}/")
    print(f"  screen pages: {len(urls)} written")
    return urls


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _money(v):
    if v >= 1e12: return f"${v / 1e12:.2f}T"
    if v >= 1e9: return f"${v / 1e9:.1f}B"
    if v >= 1e6: return f"${v / 1e6:.1f}M"
    return f"${v:,.0f}"


_PAGE_FN = None   # the Companies page as a function, set by companies_index, used by screen_pages


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
            seal = ""
            # THE NAME RIDES THE ANCHOR (2026-09-24): the ticker alone was the
            # link text; the company's name inside it is the anchor a name
            # query deserves.
            items.append(f'<li><a href="/company/{html.escape(r["tk"])}/">{html.escape(r["tk"])} '
                         f'<span class="co">{html.escape(r["co"])}</span></a> <span class="ceo">{html.escape(r["ceo"])}</span>{badge}{seal}</li>')
        parts.append(f'<section><h2 id="{letter}">{letter}</h2><ul>{"".join(items)}</ul></section>')
    nav = " ".join(f'<a href="#{l}">{l}</a>' for l in sorted(by))
    n = f"{len(rows):,}"
    index_html_block = (f"<div class=\"cidx\"><div class=\"wrap\"><h2 style=\"font-family:var(--disp);font-weight:500;font-size:22px;letter-spacing:-.01em;color:var(--ink);margin:28px 0 4px\">The index, A to Z</h2>"
                        f"<div class=\"sub\">{n} US public companies worth $1B or more, each with a page for what its chief executive owns.</div>"
                        f"<div class=\"letters\">{nav}</div>{''.join(parts)}</div></div>")
    # THE SCREENER IN FULL (PLAN.md section 5): the page is the template
    # companies.html (the table with its controls, the same block the home
    # page shows twenty rows of) with the A-Z index under it. Without the
    # template, the index alone.
    here = os.path.dirname(os.path.abspath(__file__))
    tpl_p = os.path.join(os.path.dirname(here), "companies.html")
    if os.path.exists(tpl_p):
        # THE TABLE IS INDEX.HTML'S, TAKEN AT BUILD. A copy pasted into the
        # template drifted (a column removed from the home table's header
        # and rows stayed in the template's header, and the page's last two
        # columns sat one cell to the left, 2026-09-14). The section is
        # lifted from index.html here, with the home page's heading and
        # class swapped for this page's.
        idx = open(os.path.join(os.path.dirname(here), "index.html"), encoding="utf-8").read()
        a = idx.index('<section class="tablesec home" id="table">')
        b = idx.index("</div></section>", a) + len("</div></section>")
        table = (idx[a:b]
                 .replace('<section class="tablesec home" id="table">', '<section class="tablesec" id="table">')
                 .replace("<h2>Founder stakes</h2>",
                          '<h1 style="font-family:var(--disp);font-weight:500;letter-spacing:-.02em;line-height:1.04;font-size:clamp(38px,5vw,60px);margin:0">{{HEADING}}</h1>{{DEF}}')
                 .replace('<div class="shead">', '<div class="shead" style="align-items:flex-start">')
                 # THE CONTROLS ARE THE SCREENS (2026-09-21): no named chips; the five groups in the lifted markup are the whole question
                 )
        tpl = open(tpl_p, encoding="utf-8").read()
        js_v = ""
        js_p = os.path.join(out_dir, "companies.js")
        if os.path.exists(js_p):
            import hashlib as _h
            js_v = _h.sha256(open(js_p, "rb").read()).hexdigest()[:10]

        def companies_page(heading, definition, preset, static_block, title, desc, canonical):
            # THE PAGE IS THE PAGE (2026-09-18): the heading stays "Every company" on every screen's address;
            # only the document's title and description name the screen, for search
            # the line under the heading names the screen (the title's words), in the HTML for a crawler and live for a reader
            # the same words the page script writes, so the line does not change when the script runs
            # the same words screenSentence() writes for the preset, so the line does not change when the script runs
            line = {"founder-led": "Companies whose CEO founded them, by the company's own proxy statement.",
                    "never-sold": "CEOs who have not sold at their own discretion since 2016.",
                    "over-10": "CEOs who own at least 10%.",
                    "bought-this-year": "CEOs who last bought on the open market in the last year.",
                    "hired-under-1": "Hired CEOs who own less than 1%."}.get(preset, "Every US public company worth $1B or more, with what its CEO owns.")
            t = table.replace("{{HEADING}}", "Every company").replace("{{DEF}}", f'<div class="screenline" id="screenline">{html.escape(line)}</div>')
            pg = (tpl.replace("{{TABLE}}", t)
                     .replace("{{TOPNAV}}", topnav)
                     .replace("{{INDEX_CSS}}", INDEX_CSS)
                     .replace("{{INDEX}}", static_block)
                     .replace('href="/site.css"', f'href=\"/site.css?v={css_v}\"'.replace('\\"', '"'))
                     .replace("<title>Every company · Founder Led Equities</title>", f"<title>{html.escape(title)} · Founder Led Equities</title>")
                     .replace('<meta property="og:title" content="Every company · Founder Led Equities">', f'<meta property="og:title" content="{html.escape(title)} · Founder Led Equities">')
                     .replace('<link rel="canonical" href="https://founderledequities.com/companies/">', f'<link rel="canonical" href="{canonical}">'))
            if desc:
                pg = re.sub(r'<meta name="description" content="[^"]*">', f'<meta name="description" content="{html.escape(desc[:300])}">', pg, count=1)
            # the preset: the page script reads it before it reads the URL
            pg = pg.replace("{{TOPNAV}}", topnav).replace("</head>", f"<script>window.SCREEN_PRESET={json.dumps(preset)};</script></head>", 1)
            if js_v:
                pg = pg.replace('src="/companies.js"', f'src="/companies.js?v={js_v}"')
            return pg

        # START SOMEWHERE (2026-09-24): the five screens as the page's first
        # row, each a named idea and a static link; the founder-led count
        # rides the first chip in clay.
        n_led = sum(1 for r in rows if (founders.get(r["tk"]) or {}).get("f") == "yes")
        chips = ('<div class="screenchips">'
                 f'<a href="/screens/founder-led/">Founder-led<b>{n_led}</b></a>'
                 '<a href="/screens/never-sold/">Never sold a share &rarr;</a>'
                 '<a href="/screens/bought-this-year/">Bought this year &rarr;</a>'
                 '<a href="/screens/own-more-than-10-percent/">Own more than 10% &rarr;</a>'
                 '<a href="/screens/hired-under-1-percent/">Hired, under 1% &rarr;</a></div>')
        page = companies_page("Every company", "", "", index_html_block, "Every company",
                              "", "https://founderledequities.com/companies/")
        line = "Every US public company worth $1B or more, with what its CEO owns."
        marker = f'<div class="screenline" id="screenline">{line}</div>'
        assert marker in page, "the companies screenline moved"
        page = page.replace(marker, marker + chips, 1)
        global _PAGE_FN
        _PAGE_FN = companies_page
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
    # HOW THE STAKE IS HELD (2026-09-25): the walk's decomposition, keyed by
    # ticker. Absent file = no sections anywhere; the pages build as before.
    held_by_tk = {}
    hp = os.path.join(os.path.dirname(panel_p) or ".", "holdings.csv")
    if os.path.exists(hp):
        for hr in csv.DictReader(open(hp, encoding="utf-8-sig")):
            held_by_tk.setdefault(hr.get("ticker", "").upper(), []).append(hr)
    index_html = open(os.path.join(root, "index.html"), encoding="utf-8").read()
    template = open(os.path.join(root, "company.html"), encoding="utf-8").read()
    page_js = open(os.path.join(root, "assets", "company-page.js"), encoding="utf-8").read()

    shared = extract_shared(index_html)
    header = ('/* generated by ops/build_company_pages.py -- do not edit; the source is\n'
              '   index.html (the declarations marked @shared) and assets/company-page.js */\n'
              'let PANEL=[],HIST={},PRICES={},PRICES_ASOF="",FOUNDERS={},EVENTS=[];\n'
              'const state={live:{}};\n')
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
    # THE HEADER SEARCH (2026-09-23): one standalone script on every page
    # (the topnav carries its tag), one index behind it. The script rides
    # over verbatim; ops/deploy.sh stamps its DATA_V like every data loader,
    # so /search.json?v= changes with the deploy and caches until the next.
    sjs_p = os.path.join(root, "assets", "search.js")
    if os.path.exists(sjs_p):
        with open(os.path.join(out_dir, "search.js"), "w", encoding="utf-8") as fh:
            fh.write(open(sjs_p, encoding="utf-8").read())
    # THE TAPE AS A PAGE (PLAN.md section 5): /tape/ is the same block the
    # home page carries, built from the same shared declarations plus its
    # own script, with the Monday-tape signup beside it.
    tape_tpl_p = os.path.join(root, "tape.html")
    tape_js_p = os.path.join(root, "assets", "tape-page.js")

    def tape_rows_html():
        """THE TAPE'S ROWS, STAMPED (SEO): the page renders its table with
        JavaScript, so its HTML carried no link to any company page; a
        crawler that does not run scripts saw an empty tape, and every
        Monday post links here. The week's founders' rows are written into
        the table at build, from ops/kinds.py (the page's kinds, every
        filing, 2026-09-15); the script redraws them for the reader's tier."""
        try:
            sys.path.insert(0, here)
            import kinds as _kinds
            until = datetime.date.today().isoformat()
            rows, _since = _kinds.window_rows(root, until)
            if not rows:   # an events file older than a week: its own last week
                newest = max((x.get("filed") or "" for x in csv.DictReader(open(events_p, encoding="utf-8-sig"))), default="")
                if newest:
                    rows, _since = _kinds.window_rows(root, newest)
        except Exception:  # noqa: BLE001 - no events file, no rows; the script still draws
            return ""
        if not rows:
            return ""
        return _kinds.table_html(_kinds.sorted_rows(rows), _kinds.company_names(panel_p), limit=60)

    if os.path.exists(tape_tpl_p) and os.path.exists(tape_js_p):
        tape_js = header + shared + "\n\n" + open(tape_js_p, encoding="utf-8").read()
        tape_v = hashlib.sha256(tape_js.encode("utf-8")).hexdigest()[:10]
        with open(os.path.join(out_dir, "tape.js"), "w", encoding="utf-8") as fh:
            fh.write(tape_js)
        tape_html = (open(tape_tpl_p, encoding="utf-8").read()
                     .replace('<div class="tapewrap" id="actwrap"></div>', f'<div class="tapewrap" id="actwrap">{tape_rows_html()}</div>')
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
    # THE ALERTS PAGE (2026-09-17): one rule, three switches; built like the
    # account page, with the shared block for the view beacon
    a_tpl_p = os.path.join(root, "alerts.html")
    a_js_p = os.path.join(root, "assets", "alerts-page.js")
    if os.path.exists(a_tpl_p) and os.path.exists(a_js_p):
        a_js = header + shared + "\n\n" + open(a_js_p, encoding="utf-8").read()
        with open(os.path.join(out_dir, "alerts.js"), "w", encoding="utf-8") as fh:
            fh.write(a_js)
        a_v = hashlib.sha256(a_js.encode("utf-8")).hexdigest()[:10]
        a_html = (open(a_tpl_p, encoding="utf-8").read()
                  .replace("{{TOPNAV}}", extract_topnav(index_html))
                  .replace('href="/site.css"', f'href="/site.css?v={css_v}"')
                  .replace('src="/alerts.js"', f'src="/alerts.js?v={a_v}"'))
        os.makedirs(os.path.join(out_dir, "alerts"), exist_ok=True)
        with open(os.path.join(out_dir, "alerts", "index.html"), "w", encoding="utf-8") as fh:
            fh.write(a_html)
    topnav = extract_topnav(index_html)
    # THE ABOUT PAGE: a template with the masthead from index.html, written
    # where the site has always served it (/about.html)
    about_tpl_p = os.path.join(root, "about.html")
    if os.path.exists(about_tpl_p) and "{{TOPNAV}}" in open(about_tpl_p, encoding="utf-8").read():
        about_html = (open(about_tpl_p, encoding="utf-8").read()
                      .replace("{{TOPNAV}}", topnav)
                      .replace('href="/site.css"', f'href="/site.css?v={css_v}"'))
        with open(os.path.join(out_dir, "about.html"), "w", encoding="utf-8") as fh:
            fh.write(about_html)

    # A REAL 404 (2026-09-14): without one the host answers an unknown path
    # with the home page and a 200, which a script fetching a file that does
    # not exist takes for the file. Pages serves 404.html with a 404.
    nf_p = os.path.join(root, "404.html")
    if os.path.exists(nf_p):
        with open(os.path.join(out_dir, "404.html"), "w", encoding="utf-8") as fh:
            fh.write(open(nf_p, encoding="utf-8").read().replace("{{TOPNAV}}", topnav)
                     .replace('href="/site.css"', f'href="/site.css?v={css_v}"'))

    # the S&P set is a fact the pages may show (the sp flag, neighbour order);
    # it gates nothing
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
                                             "ev": r.get("evidence") or "", "src": r.get("source") or "",
                                             "cik": r.get("cik") or ""}
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
    # history walk saw (a count the prose may say)
    panel_rows = [r for r in csv.DictReader(open(panel_p, encoding="utf-8-sig"))
                  if re.match(r"^[A-Z0-9.\-]{1,8}$", (r.get("ticker") or "").upper())]
    ranked = sorted((r for r in panel_rows
                     if (founders.get((r.get("ticker") or "").upper()) or {}).get("f") == "yes"
                     and num(r.get("shares")) and prices.get((r.get("ticker") or "").upper())),
                    key=lambda r: -(num(r.get("shares")) * prices[(r.get("ticker") or "").upper()]))
    ranked = [(r.get("ticker") or "").upper() for r in ranked]
    # THE STAKE RANK (2026-09-23): every company with a share count and a
    # close, ordered by what the stake is worth. The whole universe, not
    # only founders: #1 means the most valuable CEO stake on the site.
    by_value = sorted((r for r in panel_rows
                       if num(r.get("shares")) and prices.get((r.get("ticker") or "").upper())),
                      key=lambda r: -(num(r.get("shares")) * prices[(r.get("ticker") or "").upper()]))
    vrank = {(r.get("ticker") or "").upper(): i + 1 for i, r in enumerate(by_value)}
    # the search box's index: ticker, display name, CEO, stake, founder flag,
    # stake value (the ranking key). One small file for 2,000 companies.
    srows = []
    for r in panel_rows:
        t = (r.get("ticker") or "").upper()
        if not t:
            continue
        sh, px = num(r.get("shares")), prices.get(t)
        srows.append({"t": t,
                      "c": display_name(r.get("company") or t),
                      "e": r.get("ceo") or "",
                      "p": (round(num(r.get("pct")), 2) if num(r.get("pct")) is not None else None),
                      "f": 1 if (founders.get(t) or {}).get("f") == "yes" else 0,
                      "v": int(sh * px) if sh and px else 0})
    srows.sort(key=lambda x: -x["v"])
    with open(os.path.join(out_dir, "search.json"), "w", encoding="utf-8") as fh:
        json.dump({"rows": srows}, fh, separators=(",", ":"))
    NAMES.clear()
    NAMES.update({(r.get("ticker") or "").upper(): (r.get("company") or "") for r in panel_rows})
    CEOS.clear(); PCTS.clear()
    for _pr in panel_rows:
        _t = (_pr.get("ticker") or "").upper()
        CEOS[_t] = _pr.get("ceo") or ""
        PCTS[_t] = num(_pr.get("pct"))
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
    # scale for the prose: how many CEOs on the site own more than 5%
    sp_rows = [r for r in panel_rows if (r.get("ticker") or "").upper() in sp and num(r.get("pct")) is not None]
    scale = (sum(1 for r in sp_rows if num(r.get("pct")) > 5), len(sp_rows)) if sp_rows else None
    urls = []
    lastmods = {}
    index_rows = []
    # THE PARTNERSHIP REGISTER (fle/partnerships.py, 2026-09-15): a kept
    # company's page carries a note; an excluded company has left the
    # universe before the panel walked and gets a page that says why
    sys.path.insert(0, os.path.join(root, ""))
    from fle.partnerships import read_register, note_for
    register = read_register(os.path.join(os.path.dirname(os.path.abspath(sp_p)), "partnerships.csv"))   # beside the universe files
    n_open = 0
    for r in panel_rows:
        tk = (r.get("ticker") or "").upper()
        if not tk or not re.match(r"^[A-Z0-9.\-]{1,8}$", tk):
            continue
        if tk in register and register[tk]["action"] == "exclude":
            continue      # the register's decision wins over a panel row that has not yet been rebuilt without it
        is_sp = tk in sp
        price = prices.get(tk)
        title, desc = page_text(r, price)
        h1, answer_html = answer_text(r, price)
        payload = {"tk": tk, "co": r.get("company") or tk, "ceo": r.get("ceo") or "", "sp": is_sp,
                   "founder": founders.get(tk)}
        e_sum = ev.get(tk) or {}
        # THE CARDS' DATA (2026-09-23): the rank and the two clocks ride in the
        # payload so the script draws "N days ago" from the reader's own day.
        if vrank.get(tk):
            payload["rank"] = vrank[tk]
        for side, name in (("last_sale", "ls"), ("last_buy", "lb")):
            hit = e_sum.get(side)
            if hit:
                lr = hit[1]
                payload[name] = {"d": lr.get("traded") or lr.get("filed") or "",
                                 "v": num(lr.get("value"))}
        if e_sum.get("first"):
            payload["since"] = (e_sum.get("first") or "")[:4]   # the record's first year: the KPI clock's "no sales since"
        row = {k: r.get(k, "") for k in ("ticker", "company", "ceo", "pct", "shares", "outstanding",
                                         "shares_as_of", "confidence", "cik", "form4_url",
                                         "excluded_shares", "excluded_detail", "problems", "cautions",
                                         "operating_partnership", "stake_source")}
        if ret_1y and tk in ret_1y:
            row["ret_1y"] = f"{ret_1y[tk]:.4f}"
        payload["row"] = row
        n_open += 1
        if price:
            payload["price"] = price
            payload["price_date"] = price_date
        index_rows.append({"tk": tk, "co": payload["co"], "ceo": payload["ceo"]})
        body = static_body(payload, r, price, price_date, ev, hist, founders.get(tk), filings.get(tk, 0), ret_1y,
                           last_filed=last_filed.get(tk, ""), scale=scale)
        held = held_by_tk.get(tk, [])
        hs = held_section(tk, held, r.get("shares"), co=r.get("company") or "",
                          pct=r.get("pct"), cik=r.get("cik") or "")
        if hs:
            body += hs
            payload["held"] = [{"vehicle": x.get("vehicle") or "", "klass": x.get("klass") or "",
                                "shares": int(float(x.get("shares") or 0)),
                                "pct": x.get("pct_of_stake") or "", "as_of": (x.get("as_of") or "")[:10],
                                "accession": x.get("accession") or "", "stale": int(x.get("stale") or 0)}
                               for x in held]
        lastmods[tk] = (r.get("shares_as_of") or "")[:10]
        # WHEN THE PAGE WAS LAST TRUE: dateModified is the newest filing the
        # figure rests on (a crawler reads it; a reader sees the same date on
        # the page), so a page built nightly from a June filing says June,
        # not last night.
        as_of = (r.get("shares_as_of") or r.get("as_of") or "")[:10] or datetime.date.today().isoformat()
        crumbs = json.dumps({"@context": "https://schema.org", "@graph": [
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Founder Led Equities", "item": f"{SITE}/"},
                {"@type": "ListItem", "position": 2, "name": "Every company", "item": f"{SITE}/companies/"},
                {"@type": "ListItem", "position": 3, "name": payload["co"], "item": f"{SITE}/company/{tk}/"}]},
            {"@type": "WebPage", "@id": f"{SITE}/company/{tk}/", "name": title, "description": desc,
             "dateModified": as_of, "isPartOf": {"@type": "WebSite", "name": "Founder Led Equities", "url": f"{SITE}/"},
             "about": {"@type": "Organization", "name": payload["co"], "tickerSymbol": tk}}]})
        if tk in register and register[tk]["action"] == "keep":
            body += f'<p class="sub structure-note">{html.escape(note_for(register[tk]))}</p>'
        # THE WATCH IS ON THE PAGE BEFORE THE SCRIPT (design v4): the card and
        # the dark band are baked, so a reader without the script still sees
        # the ask; the script redraws the card with the reader's own state.
        ceo_esc = html.escape(payload["ceo"] or "this chief executive")
        watch_static = ('<div class="wcard" id="cwatch">'
                        + f'<div class="wq">Get an email when {ceo_esc}&rsquo;s stake moves.</div>'
                        + f'<form class="wform" onsubmit="return watchThis(&quot;{tk}&quot;,event)">'
                        + '<input type="email" id="wemail" placeholder="you@email.com" required autocomplete="email" aria-label="Email address">'
                        + '<button class="wbtn" type="submit">Watch &rarr;</button></form>'
                        + '<div class="wfine" id="wfine">Free. No account.</div></div>')
        # ONE ASK PER PAGE (2026-09-24): the white box under the header is the
        # company page's whole ask; the dark band at the foot belongs to every
        # other page. Two asks read as pressure.
        page = (template
                .replace('<div id="cbody"></div>', '<div id="cbody">' + body + '</div>')
                .replace('<div id="cmore"></div>', '<div id="cmore">' + neighbours_html(tk, ranked, sp) + '</div>')
                .replace('<div class="cwatchslot" id="cwatchslot"></div>', '<div class="cwatchslot" id="cwatchslot">' + watch_static + '</div>')
                .replace('</head>', f'<script type="application/ld+json">{crumbs}</script>\n</head>')
                .replace("{{TITLE}}", html.escape(title))
                .replace("{{DESCRIPTION}}", html.escape(desc))
                .replace("{{TICKER}}", html.escape(tk))
                .replace("{{MCAP}}", kicker_mcap(r, price) + founder_row(founders.get(tk)))
                                .replace("{{BODYCLS}}", "fdl" if (founders.get(tk) or {}).get("f") == "yes" else "")
                .replace("{{COMPANY}}", html.escape(payload["co"]))
                .replace("{{H1}}", html.escape(h1))
                .replace("{{ANSWER}}", answer_html)
                .replace("{{CEO}}", html.escape(payload["ceo"]))
                .replace("{{TOPNAV}}", topnav)
                .replace('href="/site.css"', f'href="/site.css?v={css_v}"')
                .replace('src="/company.js"', f'src="/company.js?v={js_v}"')
                .replace("{{COMPANY_JSON}}", json.dumps(payload).replace("</", "<\\/")))
        page = card_tags(page, tk, og_dir)
        d = os.path.join(out_dir, "company", tk)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as fh:
            fh.write(page)
        urls.append(f"{SITE}/company/{tk}/")

    # AN EXCLUDED COMPANY HAS NO PAGE (2026-09-15): it is not in the universe,
    # not in the screener, not in the sitemap; its address answers with the
    # real 404 like any company the site does not cover. The register row
    # holds the facts should it ever be asked for.
    companies_index(index_rows, founders, sp, out_dir, topnav, css_v)
    urls.append("https://founderledequities.com/companies/")
    urls.extend(screen_pages(os.path.join(out_dir, "universe.csv"), founders, prices, out_dir, topnav, css_v, index_rows, sp))
    # the letter's archive (ops/letter.py publish writes the pages; the sitemap lists them here)
    import glob as _glob
    issues = [p for p in sorted(_glob.glob(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "weekly", "letter-*.md")))
              if re.search(r"^sent:\s*\S", open(p, encoding="utf-8").read(2000), re.M)]   # sent issues only
    if issues:
        urls.append("https://founderledequities.com/letter/")
        urls.extend(f"https://founderledequities.com/letter/{os.path.basename(p)[7:-3]}/" for p in issues)
    if os.path.exists(os.path.join(out_dir, "alerts", "index.html")):
        urls.append(f"{SITE}/alerts/")
    with open(os.path.join(out_dir, "sitemap.xml"), "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        today = datetime.date.today().isoformat()
        for u in [f"{SITE}/", f"{SITE}/tape/", f"{SITE}/about.html"] + urls:
            m = re.search(r"/company/([A-Z0-9.\-]+)/$", u)
            lm = (lastmods.get(m.group(1)) if m else "") or today
            fh.write(f"  <url><loc>{html.escape(u)}</loc><lastmod>{lm}</lastmod></url>\n")
        fh.write("</urlset>\n")
    with open(os.path.join(out_dir, "robots.txt"), "w", encoding="utf-8") as fh:
        # the workers under /api/ are not pages; nothing else is closed
        fh.write(f"User-agent: *\nAllow: /\nDisallow: /api/\nSitemap: {SITE}/sitemap.xml\n")
    print(f"  company pages: {n_open}; company.js, search.js, search.json, site.css, sitemap.xml, robots.txt")
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
