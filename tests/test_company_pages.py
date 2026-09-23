"""One page per company, built from one source.

The rules a company page applies -- what a cleaned series excludes, how a
trade is badged, how money is rounded -- are extracted from index.html at
build, not copied; these tests hold the extraction to that."""
import csv
import html
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ops"))
import build_company_pages as bcp  # noqa: E402


def _fixture(tmp_path):
    panel = tmp_path / "panel.csv"
    with open(panel, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "cik", "company", "ceo", "pct", "shares", "outstanding",
                    "shares_as_of", "confidence", "form4_url"])
        w.writerow(["TSLA", "1318605", "Tesla, Inc.", "Elon Musk", "28.4412", "1120000000",
                    "3950000000", "2026-07-06", "high", "https://sec.gov/x"])
        w.writerow(["SEALD", "999", "Sealed Co", "Jane Doe", "41.2", "1000000", "2400000",
                    "2026-06-01", "medium", ""])
    sp = tmp_path / "sp.csv"
    sp.write_text("cik,ticker,company,added\n1318605,TSLA,Tesla,\n")
    prices = tmp_path / "prices.csv"
    prices.write_text("ticker,close,as_of\nTSLA,330.00,2026-09-02\nSEALD,10.00,2026-09-02\n")
    founders = tmp_path / "founders.csv"
    founders.write_text('ticker,founder,evidence,source\nTSLA,yes,"co-founded the Company",DEF 14A\n')
    out = tmp_path / "public"
    return str(panel), str(founders), str(prices), str(sp), str(out)


def test_the_shared_code_is_extracted_whole_and_parses():
    idx = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    js = bcp.extract_shared(idx)
    for name in ("function parseCSV(", "function mapPanel(", "function mapHistory(", "function mapEvents(",
                 "function cleanHist(", "function evBadge(",
                 "function unchangedKind(", "function pctOf(", "function lagNote(", "const money=",
                 "let _cleanCache="):
        assert name in js, f"{name} is not marked @shared"
    # the parsers and formatters never touch the DOM; the tape's renderer is
    # shared on purpose (the home page and /tape/ draw the same block) and
    # is the one declaration allowed to
    # the parsers and formatters (everything before the first renderer, the
    # switch painter) never touch the DOM; the renderers shared by the home
    # page, /companies/ and /tape/ do, by nature
    # the shared block is declarations in source order; the renderers touch
    # the DOM by nature, the parsers and formatters never do
    import re as _re
    renderers = {"paintSw", "wireSw", "renderTable", "exportTable", "lastTrades", "renderActivity", "setWin", "setScreen", "setFounderLed", "screenAddress"}
    for m in _re.finditer(r"^function (\w+)\(", js, flags=_re.M):
        end = js.find("\nfunction ", m.end())
        body = js[m.start():end if end > 0 else len(js)]
        if m.group(1) not in renderers:
            assert "document.querySelector" not in body and "state.pro" not in body and "state.live" not in body, \
                m.group(1) + " is shared as a parser or formatter and must not touch the DOM or app state"

    if shutil.which("node"):
        r = subprocess.run(["node", "-e", "new Function(process.argv[1])", "--", js],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-400:]


def test_site_css_carries_the_whole_stylesheet(tmp_path):
    """index.html has two <style> blocks since the fonts came home; site.css
    is all of them. With only the first, every company page rendered
    unstyled."""
    panel, founders, prices, sp, out = _fixture(tmp_path)
    bcp.main(panel, founders, prices, sp, out)
    css = open(os.path.join(out, "site.css"), encoding="utf-8").read()
    assert ":root{" in css and "@font-face" in css and ".hstat" in css, "tokens, fonts and the shared rules, in one file"


def test_one_page_per_company_with_the_seal_respected(tmp_path):
    panel, founders, prices, sp, out = _fixture(tmp_path)
    bcp.main(panel, founders, prices, sp, out)
    tsla = open(os.path.join(out, "company", "TSLA", "index.html"), encoding="utf-8").read()
    sealed = open(os.path.join(out, "company", "SEALD", "index.html"), encoding="utf-8").read()
    # the open page carries the number where a search engine and a card read it
    assert "<title>Elon Musk owns 28.44% of Tesla (TSLA)" in tsla
    assert "worth $370B" in tsla, "the description prices the stake at the close, rounded as the page rounds"
    assert '"pct": "28.4412"' in tsla and '"sp": true' in tsla
    assert '"price_date": "2026-09-02"' in tsla, "the close's date rides with the price (prices.csv says as_of)"
    assert 'href="https://founderledequities.com/company/TSLA/"' in tsla
    assert "co-founded the Company" in tsla, "the founder evidence rides in the shell (as data for the receipt)"
    # ONE TREE (2026-09-23): a company outside the S&P is the same page,
    # and the sp flag says only what it is -- index membership
    assert "<title>Jane Doe owns 41.20% of Sealed (SEALD)" in sealed
    assert "41.2" in sealed and '"sp": false' in sealed, "the stake is on the page; sp states the index and gates nothing"
    assert '"price": 10.0' in sealed
    assert "Sealed universe" not in sealed and "open to everyone" not in tsla
    # the ticker and the market cap sit beside the name, on both tiers (public data)
    assert 'id="ctk">TSLA · $' in tsla and 'id="ctk">' in sealed
    assert "<h1>Elon Musk owns 28.44% of Tesla</h1>" in tsla and '<span class="co">Tesla, Inc.</span>' in tsla, "the answer is the heading, the company the kicker (2026-09-24)"
    assert 'class="answer">1,120,000,000 shares as of the' in tsla, "the first sentence carries the shares and the date in the HTML itself"
    # every page is indexable and answers its own question (the seal is off)
    assert '<meta name="robots"' not in sealed and "41.20%" in sealed
    assert "41.20%" in sealed, "the seal is off: the figure is on every page"
    sitemap = open(os.path.join(out, "sitemap.xml"), encoding="utf-8").read()
    assert "/company/TSLA/" in sitemap and "/company/SEALD/" in sitemap
    # the machinery around them
    assert os.path.exists(os.path.join(out, "company.js"))
    assert 'src="/company.js?v=' in tsla and 'href="/site.css?v=' in tsla, "a new script is a new address"
    assert os.path.exists(os.path.join(out, "site.css"))
    sm = open(os.path.join(out, "sitemap.xml"), encoding="utf-8").read()
    import glob as _g, re as _re
    n_letters = len([p for p in _g.glob(os.path.join(ROOT, "weekly", "letter-*.md"))
                     if _re.search(r"^sent:\s*\S", open(p, encoding="utf-8").read(2000), _re.M)])
    assert sm.count("<loc>") == 7 + (1 + n_letters if n_letters else 0) and "/company/SEALD/" in sm and "/companies/" in sm and "/tape/" in sm and "/pro/" not in sm and "/alerts/" in sm, \
        "every company is in the sitemap once, and the pro page is gone (2026-09-23)"
    assert sm.count("/alerts/") == 1 and sm.count("/companies/</loc>") == 1, "no address is listed twice"
    robots = open(os.path.join(out, "robots.txt"), encoding="utf-8").read()
    assert "Sitemap:" in robots
    # one tree, no gate (2026-09-23): only the workers are closed to crawlers
    assert "/pro" not in robots and "Disallow: /api/" in robots
    js = open(os.path.join(out, "company.js"), encoding="utf-8").read()
    assert "function cleanHist(" in js and "function watchThis(" in js, "the page's own logic follows the shared code"


def test_the_nav_on_a_page_points_home():
    idx = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    nav = bcp.extract_topnav(idx)
    assert 'href="/tape/"' in nav and 'href="/companies/"' in nav and 'href="/about.html"' in nav and "#board" not in nav and "#perfsec" not in nav
    assert "devtog" not in nav and "gopro" not in nav and "openPro()" not in nav, "no dev toggle and no Join on a static page"
    assert 'id="navq"' in nav and 'src="/search.js"' in nav, "the search box rides on every built page (2026-09-23)"


def test_money_rounds_as_the_page_does():
    """$369.6B rounds to $370B, and a stripped zero must never turn it into $37B."""
    assert bcp.money(1.12e9 * 330) == "$370B"
    assert bcp.money(1.03e12) == "$1.03T"
    assert bcp.money(1.9e12) == "$1.9T"
    assert bcp.money(27.3e9) == "$27.3B"
    assert bcp.money(903e6) == "$903M"
    assert bcp.money(999_959_042) == "$1B", "rounding may cross the unit boundary; the unit is chosen after"


def test_the_published_home_page_carries_the_numbers(tmp_path):
    """A fetch without scripts must read tonight's hero and top ten, not
    the placeholder '20 of 500' and an empty board."""
    import stamp_static as st
    st.OPEN_TOP = 0   # the fixture has two rows; keep the sealed one sealed (by share it would lead)
    panel, founders, prices, sp, _ = _fixture(tmp_path)
    out = tmp_path / "index.html"
    src = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    out.write_text(src, encoding="utf-8")
    st.main(panel, sp, prices, founders, str(out))
    page = out.read_text(encoding="utf-8")
    assert '<h1 id="thesis">How much of the company does the CEO own?</h1>' in page, \
        "the headline is the purpose, the same for every reader, and needs no stamp"
    # ONE STRIP FOR EVERYONE: three aggregates over every company, no company's stake
    assert '<div class="n">2</div><div class="k">CEOs own more than 5%</div>' in page, \
        "the strip counts over every company, the sealed one included"
    strip = page[page.index('id="herostats"'):page.index('id="table"')]
    assert strip.index("Founder-led companies") < strip.index("CEOs own more than 5%") < strip.index("Held by those founders"), \
        "three numbers in the plan's order"
    assert "Of all CEO wealth" not in page, "the fourth number said the same thing as the third"
    assert "of them are sealed" not in page, "no second Go Pro: the nav button is the one call"
    assert 'data-pro="' not in page, "one strip, no second copy to swap in"
    assert '<tbody id="tbody"><tr' in page and 'href="/company/TSLA/"' in page and ">28.44%<" in page, "the table's first rows are real HTML, by share of the company"
    # ONE TREE (2026-09-23): the preview ranks every company alike
    assert 'class="hstat"' in page and "Founder-led companies" in page, "and so is the stat strip"
    assert not os.path.exists(os.path.join(ROOT, "functions", "_tier.js")), "the gate worker left with the tier"
    assert not os.path.exists(os.path.join(ROOT, "functions", "index.js"))
    assert not os.path.isdir(os.path.join(ROOT, "functions", "company"))
    assert "document.cookie" not in src


def test_the_about_page_is_built_with_the_masthead(tmp_path):
    """About is a template with the masthead from index.html, written where
    the site serves it; it explains ownership and the kinds of trade and
    carries no chart or marks legend."""
    panel, founders, prices, sp, out = _fixture(tmp_path)
    bcp.main(panel, founders, prices, sp, out)
    about = open(os.path.join(out, "about.html"), encoding="utf-8").read()
    assert "{{TOPNAV}}" not in about and 'class="topnav"' in about or "topin" in about
    for phrase in ("What ownership means here", "What a trade means here", "EDGAR", "Rule 10b5-1"):
        assert phrase in about, phrase
    assert "PERF_SVG" not in about and 'class="dot high"' not in about

def test_the_page_says_its_numbers_in_html_and_every_company_has_a_link(tmp_path):
    """A fetch without scripts must read the stake, the value, the record
    and the last trade from the HTML; a sealed page reads the person and
    the offer; and /companies/ links every page."""
    panel, founders, prices, sp, _ = _fixture(tmp_path)
    events = tmp_path / "events.csv"
    events.write_text("ticker,code,label,traded,filed,value,plan,pre_ipo\n"
                      "TSLA,S,sale,2026-08-29,2026-08-31,24200000,plan,0\n"
                      "TSLA,P,purchase,2020-02-14,2020-02-18,10000000,discretionary,0\n"
                      "TSLA,S,exercise and sell,2026-06-01,2026-06-02,50000000,,0\n", encoding="utf-8")
    hist = tmp_path / "history.csv"
    hist.write_text("ticker,date,pct\nTSLA,2016-03-01,21.10\nTSLA,2026-07-06,28.44\n", encoding="utf-8")
    out = tmp_path / "pub"
    bcp.main(panel, founders, prices, sp, str(out), str(events), str(hist))
    tsla = open(out / "company" / "TSLA" / "index.html", encoding="utf-8").read()
    body = tsla[tsla.index('<div id="cbody">'):tsla.index('<div class="creport"')]
    assert "28.44%" in body and "1,120,000,000 of 3,950,000,000 shares" in body and "$370B" in body, "the prose paragraph carries the figures in the HTML"
    assert "Confidence" not in body and "3-year" not in body
    # THREE CARDS, LABEL FIRST (2026-09-23): the rank and the two clocks; the
    # share, the shares and the worth live in the H1 and the first sentence
    for label in ("Stake rank", "Last sale", "Last buy"):
        assert f'<div class="k">{label}</div>' in body, "the band is the rank and the two clocks"
    assert 'class="cband kpi"' in body and "by dollar value of the stake" in body
    assert "<small> days ago</small>" in body, "the clock is a day count, redrawn by the script from the reader's day"
    assert "Aug 29, 2026 · $24.2M" in body, "the sale's date and size are the fine print"
    assert "Feb 14, 2020 · $10M" in body, "the buy's date and size are the fine print"
    for label in ("Shares held", "Worth", "Market cap", "1Y return", "Outstanding"):
        assert f'<div class="k">{label}</div>' not in body, "the sentence's figures are not repeated as cards"
    assert "from 21.10% in 2016 to 28.44% on 2026-07-06" in body, "the record, as a sentence"
    assert "1 sale and 1 purchase" in body, "kept-apart trades do not count"
    assert "planned sale of $24.2M on 2026-08-29" in body, "the last trade that moved it"
    assert "names Elon Musk a founder" in body
    sealed = open(out / "company" / "SEALD" / "index.html", encoding="utf-8").read()
    sbody = sealed[sealed.index('<div id="cbody">'):sealed.index('<div class="creport"')]
    assert "41.20%" in sbody and 'class="sealed"' not in sbody, "the seal is off: the figure is on every page"
    idx = open(out / "companies" / "index.html", encoding="utf-8").read()
    assert 'href="/company/TSLA/"' in idx and 'href="/company/SEALD/"' in idx, "every page has a plain link"
    assert "FOUNDER" in idx and "Pro</span>" not in idx, "no Pro badge on the list: nothing is sealed"


def test_the_seo_layer(tmp_path):
    """The query phrase is a heading; a sealed page carries the proxy's own
    sentence and a count of filings; every page has neighbour links and
    breadcrumbs; the sitemap dates each page."""
    panel, founders, prices, sp, _ = _fixture(tmp_path)
    hist = tmp_path / "history.csv"
    hist.write_text("ticker,date,pct\nTSLA,2016-03-01,21.10\nTSLA,2026-07-06,28.44\nSEALD,2020-01-01,40.0\nSEALD,2021-01-01,41.2\n", encoding="utf-8")
    out = tmp_path / "pub"
    bcp.main(panel, founders, prices, sp, str(out), str(tmp_path / "none.csv"), str(hist))
    tsla = open(out / "company" / "TSLA" / "index.html", encoding="utf-8").read()
    assert '<div class="k">Stake rank</div>' in tsla and ">None<" in tsla and "no sales since 2016" in tsla, \
        "the KPI band is baked even with no events file: the clocks say None honestly"
    assert "<h1>Elon Musk owns 28.44% of Tesla</h1>" in tsla, "the answer is the H1; no second card repeats it"
    assert '"@type": "BreadcrumbList"' in tsla and '/companies/' in tsla
    assert '<div id="cmore"><div class="cmore">' in tsla or '<div id="cmore"></div>' in tsla, "neighbour links live outside the block the script redraws"
    sealed = open(out / "company" / "SEALD" / "index.html", encoding="utf-8").read()
    assert "<h1>Jane Doe owns 41.20% of Sealed</h1>" in sealed and '<div class="k">Stake rank</div>' in sealed, \
        "the seal is off: the figure is the H1 and the KPI band is baked on every page"
    sm = open(out / "sitemap.xml", encoding="utf-8").read()
    assert "<lastmod>2026-07-06</lastmod>" in sm, "a company page is dated by its as-of"


def test_the_record_has_two_views_and_no_prose():
    """The page script draws the price (default) and the stake, one point
    per month-end for the stake, dots at the filed price restated in
    today's shares, a crosshair hover, and one draw-in on load. The chart
    has no heading and no caption: the toggle names the line, and what each
    line is lives on the toggle's hover. The shares-held view is gone."""
    js = open(os.path.join(ROOT, "assets", "company-page.js"), encoding="utf-8").read()
    assert "function monthEnds(" in js and "share count changed" in js and '"granted"' in js
    assert '["price","Price"' in js and '["pct","Stake"' in js
    assert '["shares","Shares held"' not in js and 'mode==="shares"' not in js
    assert "function priceChart(" in js and "split-adjusted. Dots sit at the price on the filing" in js
    assert "e.apa" in js, "dots sit at the filed price restated in today's shares"
    assert 'fetchText([`/prices/${C.tk}.csv`])' in js, "prices are fetched from the public root on every page"
    assert "function attachHover(" in js and "function drawIn(" in js
    assert 'class="ann"' not in js and "linearGradient" in js
    assert 'class="dot"' in js and 'class="dot"><circle' not in js and 'rel="noopener" class="dot"' not in js, "dots are marks, not links; the list carries the filing link"
    assert "steps without a dot are grants, gifts, or the share count changing" in js.lower()
    rec = js[js.index("function recordBlock("):js.index("/* ---- the trades ---- */")]
    assert "<h2>" not in rec and 'class="sub"' not in rec, "the chart section carries no heading and no caption"
    assert "daily closes" in rec[rec.index("const modes="):rec.index("const chips=")], "what a line is lives on the toggle"
    assert "hover for the trade" not in js and "dot size follows" not in js, "the key is two words"


def test_the_band_is_the_rank_and_the_two_clocks():
    """THREE CARDS, LABEL FIRST (2026-09-23): Stake rank, Last sale, Last buy.
    The share, the shares and the worth live in the H1 and the first
    sentence; the kicker names the market cap and carries the founder flag;
    the watch renders beside the answer, not in the band."""
    js = open(os.path.join(ROOT, "assets", "company-page.js"), encoding="utf-8").read()
    band = js[js.index("function stat("):js.index("/* ---- the record:")]
    for label in ('"Stake rank"', '"Last sale"', '"Last buy"'):
        assert f"stat({label}" in band, f"{label} is a card"
    for label in ('"Shares held"', '"Worth"', '"Market cap"', '"1Y return"', '"Value"'):
        assert f"stat({label}" not in band, f"{label} is not a card"
    assert "by dollar value of the stake" in band, "the rank says what it ranks; no cross-company comparison rides it"
    assert "SpaceX" not in js, "no sentence that only works for one company"
    assert "kick.innerHTML" in band and "mkt cap" in band and 'class="fdl"' in band, \
        "the kicker: ticker, the market cap named as such, and the founder flag"
    assert "3-year" not in band[band.index("function band("):] and "trajStats" not in js
    assert "never estimated" not in band, "the answer needs no sentence beside it"
    assert 'class="cband kpi">' in band and "${watchCard(r)}" not in band, "the watch is not a card in the band"
    assert 'id="cwatchslot"' in open(os.path.join(ROOT, "company.html"), encoding="utf-8").read() and \
        '$("#cwatchslot")' in js, "the watch renders in the head's slot, beside the answer (2026-09-23)"
    assert '"None"' in band and 'C.since||"2016"' in band, "a company with no sale on record says so"
    assert "daysSince(" in band, "the day count is drawn from the reader's own day"
    assert "confidence</summary>" not in band, "no confidence grade on the card"
    # A LOW-CONFIDENCE STAKE STILL SAYS WHY (2026-09-23): the Caution line
    # under the cards carries the same sentence the tape's "?" carries
    assert 'r.conf==="low"' in band and '(r.flags||"").split("\\n")[0]' in band and '>Caution<' in band
    assert "\u2014" not in js, "no em dashes"


def test_every_page_is_open_and_the_script_has_no_seal(tmp_path):
    """ONE TREE (2026-09-23): a company outside the S&P renders exactly as
    one inside it, and the page script has no sealed branch at all."""
    panel, founders, prices, sp, out = _fixture(tmp_path)
    bcp.main(panel, founders, prices, sp, out)
    sealed = open(os.path.join(out, "company", "SEALD", "index.html"), encoding="utf-8").read()
    assert "<h1>Jane Doe owns 41.20% of Sealed</h1>" in sealed and '<div class="k">Stake rank</div>' in sealed
    assert 'class="sealed"' not in sealed, "no blurred figures anywhere"
    assert bcp.poss("Jabbok Schlacks") == "Jabbok Schlacks'"
    js = open(os.path.join(ROOT, "assets", "company-page.js"), encoding="utf-8").read()
    for gone in ("const BLUR=", "masked", "openPro", "state.pro", "/pro/", "/api/me"):
        assert gone not in js, f"the tier left the page script: {gone}"
    assert '/history/${C.tk}.csv' in js and '/events/${C.tk}.csv' in js, "the record loads from the one tree"


def test_the_one_year_return_on_a_page_is_the_lists(tmp_path):
    """Passed --prices, the page builder reads the 1Y return through the
    same function the list uses, and the open row carries it for the
    script; without a store, the cell is a dash, never a guess."""
    panel, founders, prices, sp, _ = _fixture(tmp_path)
    store = tmp_path / "store"
    store.mkdir()
    (store / "TSLA.csv").write_text("date,close\n2025-01-02,200.0\n2025-06-02,250.0\n2026-01-05,300.0\n")
    out = tmp_path / "pub"
    bcp.main(panel, founders, prices, sp, str(out), prices_dir=str(store))
    tsla = open(out / "company" / "TSLA" / "index.html", encoding="utf-8").read()
    body = tsla[tsla.index('<div id="cbody">'):tsla.index('<div class="creport"')]
    assert '"ret_1y": "50.0000"' in tsla, "the script's row carries the figure (the list uses it)"
    bcp.main(panel, founders, prices, sp, str(out))
    tsla = open(out / "company" / "TSLA" / "index.html", encoding="utf-8").read()
    assert "ret_1y" not in tsla, "no store, no return: nothing is guessed"


def test_each_page_unfurls_into_its_own_card_when_one_is_drawn(tmp_path):
    """A shared company page pointed at the site-wide og.png; now it
    points at og/<T>.png?v=<hash> when the deploy drew one, and keeps
    og.png when it did not. The card holds the seal: a sealed company's
    card has the name, the person, the public price line, and no stake."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("company_cards", os.path.join(ROOT, "ops", "company_cards.py"))
    cc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cc)
    panel, founders, prices, sp, out = _fixture(tmp_path)
    store = tmp_path / "store"
    store.mkdir()
    days = "".join(f"2024-{m:02d}-15,{100+m*5}.0\n" for m in range(1, 13))
    (store / "TSLA.csv").write_text("date,close\n" + days)
    (store / "SEALD.csv").write_text("date,close\n" + days)
    events = tmp_path / "events.csv"
    events.write_text("ticker,code,label,traded,filed,value,avg_price_adjusted,shares\n"
                      "TSLA,S,sale,2024-06-15,2024-06-17,1000000,130.0,7692\n"
                      "TSLA,S,exercise and sell,2024-07-15,2024-07-17,500000,135.0,3703\n"
                      "SEALD,P,purchase,2024-06-15,2024-06-17,1000,130.0,8\n")
    og = tmp_path / "og"
    rc = cc.main(panel, sp, prices, founders, str(events), str(store), str(og))
    assert rc == 0
    assert sorted(p.name for p in og.iterdir()) == ["SEALD.png", "TSLA.png"]
    v = cc.card_version(str(og), "TSLA")
    assert len(v) == 10 and cc.card_version(str(og), "GHOST") == ""

    bcp.main(panel, founders, prices, sp, out, og_dir=str(og))
    tsla = open(os.path.join(out, "company", "TSLA", "index.html"), encoding="utf-8").read()
    assert f'<meta property="og:image" content="https://founderledequities.com/og/TSLA.png?v={v}">' in tsla
    assert f'<meta name="twitter:image" content="https://founderledequities.com/og/TSLA.png?v={v}">' in tsla
    assert "founderledequities.com/og.png" not in tsla

    # no card drawn: the page keeps the site's card
    bcp.main(panel, founders, prices, sp, out)
    tsla = open(os.path.join(out, "company", "TSLA", "index.html"), encoding="utf-8").read()
    assert 'content="https://founderledequities.com/og.png"' in tsla

    # the drawn images are real PNGs of the card's size
    from PIL import Image
    im = Image.open(og / "SEALD.png")
    assert im.size == (1200, 630)


def test_a_filing_link_opens_the_index_page_not_the_xml():
    """EDGAR serves the Form 4 document as raw XML; the filing's index page
    is the HTML a person can read. Derived from the document URL, so
    nothing in the data changes."""
    import subprocess
    js = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    start = js.index("function filingPage(u){")
    fn = js[start:js.index("/*@shared*/", start)]
    prog = fn + ("console.log(filingPage('https://www.sec.gov/Archives/edgar/data/1318605/000110465926075213/tm2618092-2_4seq1.xml'));"
                 "console.log(filingPage('https://example.com/x'));console.log(filingPage(''));")
    out = subprocess.run(["node", "-e", prog], capture_output=True, text=True).stdout.split("\n")
    assert out[0] == "https://www.sec.gov/Archives/edgar/data/1318605/000110465926075213/0001104659-26-075213-index.htm"
    assert out[1] == "https://example.com/x" and out[2] == ""


def test_the_tape_is_a_page(tmp_path):
    """/tape/ is the same block the home page carries, built from the shared
    declarations plus its own script, with the Monday-tape signup beside it
    and the masthead from index.html; it is in the sitemap."""
    panel, founders, prices, sp, out = _fixture(tmp_path)
    bcp.main(panel, founders, prices, sp, out)
    page = open(os.path.join(out, "tape", "index.html"), encoding="utf-8").read()
    js = open(os.path.join(out, "tape.js"), encoding="utf-8").read()
    assert "{{TOPNAV}}" not in page and 'class="topnav"' in page, "the masthead is the site's"
    assert 'id="actwrap"' in page and 'id="tg-f" checked' in page and 'id="subform"' in page, "the tape block, founders on, the signup"
    assert 'src="/tape.js?v=' in page and 'href="/site.css?v=' in page, "versioned script and stylesheet"
    for fn in ("function renderActivity(", "function actSorted(", "function tapeKind(", "function boot(", "async function subscribe("):
        assert fn in js, fn
    assert js.count("function renderActivity(") == 1, "shared once"
    sm = open(os.path.join(out, "sitemap.xml"), encoding="utf-8").read()
    assert "/tape/</loc>" in sm
    fn_src = open(os.path.join(ROOT, "functions", "api", "subscribe.js"), encoding="utf-8").read()
    assert "/contacts" in fn_src and "/segments/${env.RESEND_SEGMENT_ID}" in fn_src and "sub:${token}" in fn_src and "expirationTtl: 86400" in fn_src, \
        "double opt-in through a one-day token: the contact is created, then added to the letter's segment"


def test_the_pro_page_is_gone(tmp_path):
    """The paid tier left the code base (2026-09-23): no /pro/ page is
    built, no checkout function exists, and no script points at the plan."""
    panel, founders, prices, sp, out = _fixture(tmp_path)
    bcp.main(panel, founders, prices, sp, out)
    assert not os.path.isdir(os.path.join(out, "pro"))
    assert not os.path.exists(os.path.join(ROOT, "pro.html"))
    assert not os.path.exists(os.path.join(ROOT, "functions", "api", "checkout.js"))
    idx = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    assert "openPro" not in idx and "/pro/" not in idx
    for f in ("assets/company-page.js", "assets/tape-page.js", "assets/companies-page.js"):
        assert 'location.href="/pro/"' not in open(os.path.join(ROOT, f), encoding="utf-8").read(), f

def test_the_watches_have_a_box_and_two_ways_to_stop(tmp_path):
    """Every company page carries the watch box (an email field, free, any
    number of names); every alert carries a stop link per name and one for
    all. The account page left with the tier (2026-09-23)."""
    panel, founders, prices, sp, out = _fixture(tmp_path)
    bcp.main(panel, founders, prices, sp, out)
    assert not os.path.isdir(os.path.join(out, "account")) and not os.path.isdir(os.path.join(out, "watches"))
    nav = bcp.extract_topnav(open(os.path.join(ROOT, "index.html"), encoding="utf-8").read())
    assert "Weekly tape, free" not in nav and "navwatches" not in nav and "gopro" not in nav and 'href="/alerts/">Alerts' in nav, \
        "the header is where you are: four pages and the search box"
    for f in ("functions/api/letter.js", "functions/api/logout.js", "functions/api/login.js", "functions/api/me.js"):
        assert not os.path.exists(os.path.join(ROOT, f)), f
    page_js = open(os.path.join(ROOT, "assets", "company-page.js"), encoding="utf-8").read()
    # THE WATCH IS THE FOURTH CARD (2026-09-17): the person's name, an email
    # field, one line of fine print; the definition lives on the About page
    assert "function watchCard(" in page_js and "function watchBlock(" not in page_js and "band(r)+recordBlock(r)" in page_js
    assert "An email when the stake moves." in page_js and "Never for a plan" not in page_js
    assert 'id="wemail"' in page_js and "watchThis(" in page_js, "an email field, on every page"
    assert "toggleWatch(" not in page_js and 'id="wsw"' not in page_js, "the signed-in switch left with the tier"
    about = open(os.path.join(ROOT, "about.html"), encoding="utf-8").read()
    assert "What counts as a move" in about and "1% or more" in about, "the definition is stated once, on the About page"
    assert "Stopped. No more emails about" in page_js and "No more emails about anyone" in page_js, "the box says what a stop link did"
    assert "One founder watch is free" not in page_js and "is Pro" not in page_js, "no tier in the fine print"
    w = open(os.path.join(ROOT, "functions", "api", "watch.js"), encoding="utf-8").read()
    assert "A list of names is Pro" not in w and "stopall" in w and "confirm=" in w
    run = open(os.path.join(ROOT, "functions", "api", "watch", "run.js"), encoding="utf-8").read()
    assert "Stop everything" in run and "alerts_sent" in run and "env.ALERTS_KEY" in run

def test_the_display_name_is_the_one_a_person_types():
    """Titles and descriptions use the name a searcher would type, by rule:
    the corporate suffix stripped, an all-caps legal name given its case,
    'Holdings' kept, short initialisms kept."""
    for legal, shown in (("NVIDIA CORP", "Nvidia"), ("Tesla, Inc.", "Tesla"), ("UWM Holdings Corp", "UWM Holdings"),
                         ("AMD", "AMD"), ("3M CO", "3M"), ("AT&T INC.", "AT&T"), ("BeOne Medicines Ltd.", "BeOne Medicines"),
                         ("Apollo Global Management, Inc.", "Apollo Global Management")):
        assert bcp.display_name(legal) == shown, (legal, bcp.display_name(legal))


def test_the_page_carries_the_date_it_was_last_true_and_the_tape_carries_its_links(tmp_path):
    panel, founders, prices, sp, out = _fixture(tmp_path)
    bcp.main(panel, founders, prices, sp, out)
    page = open(os.path.join(out, "company", "TSLA", "index.html"), encoding="utf-8").read()
    assert '"dateModified": "2026-09-02"' in page or '"dateModified": "' in page, "the schema says when the figure was last true"
    assert '"tickerSymbol": "TSLA"' in page
    assert os.path.exists(os.path.join(ROOT, "llms.txt")) and "founderledequities.com/company/" in open(os.path.join(ROOT, "llms.txt"), encoding="utf-8").read()


def test_every_built_page_script_loads_without_a_top_level_error(tmp_path):
    """THE BUILT SCRIPTS ARE RUN, NOT ONLY PARSED (2026-09-16). tape.js and
    companies.js are the home page's shared blocks plus a page script, in an
    order the home page never runs; a shared block that touched state.ev at
    load passed the harness and killed both pages. Each built script is
    loaded under stub globals that swallow DOM and network calls; anything
    that throws at the top level fails here."""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    panel, founders, prices, sp, out = _fixture(tmp_path)
    bcp.main(panel, founders, prices, sp, out)
    driver = r"""
const vm=require("vm"),fs=require("fs");
const P=new Proxy(function(){},{get:(t,k)=>k===Symbol.toPrimitive?()=>"":k==="then"?undefined:P,apply:()=>P,construct:()=>P,set:()=>true,has:()=>true});
for(const f of process.argv.slice(2)){
  const src=fs.readFileSync(f,"utf8");
  const g={document:P,window:P,location:{href:"https://x/",pathname:"/",search:"",hash:""},navigator:P,fetch:()=>Promise.reject(new Error("offline")),setTimeout:()=>0,clearTimeout:()=>0,setInterval:()=>0,console,localStorage:P,history:P,Intl,Date,Math,JSON,Promise,URL,URLSearchParams,requestAnimationFrame:()=>0,addEventListener:()=>0,performance:{now:()=>0},COMPANY:{tk:"TSLA",co:"Tesla",ceo:"Elon Musk",sp:true}};
  g.window=g;g.globalThis=g;g.self=g;
  try{vm.runInNewContext(src,g,{filename:f,timeout:5000});}
  catch(e){console.error("LOAD ERROR in "+f+": "+(e&&e.stack||e));process.exit(1);}
}
// the async paths run against a fake DOM and are not judged here: the top-level load is
process.on("unhandledRejection",()=>{});
console.log("loaded "+process.argv.slice(2).length+" scripts");process.exit(0);
"""
    scripts = [os.path.join(out, n) for n in ("tape.js", "companies.js", "company.js") if os.path.exists(os.path.join(out, n))]
    assert scripts, "the builder writes the page scripts"
    drv = os.path.join(str(tmp_path), "load_check.js")
    with open(drv, "w", encoding="utf-8") as fh:
        fh.write(driver)
    p = subprocess.run([node, drv] + scripts, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[-1500:]
    assert f"loaded {len(scripts)} scripts" in p.stdout, p.stdout


def test_the_alerts_page_is_built_with_three_free_cards(tmp_path):
    """THE ALERTS PAGE, ALL FREE (2026-09-23): one rule stated once, three
    grains of one stream (the letter, live founder alerts, the watches),
    a sample email; the live alert is a watch on the reserved name FOUNDERS."""
    panel, founders, prices, sp, out = _fixture(tmp_path)
    bcp.main(panel, founders, prices, sp, out)
    page = open(os.path.join(out, "alerts", "index.html"), encoding="utf-8").read()
    assert "When a founder" in page and "1% or more" in page and "within about ten minutes of the SEC filing" in page
    assert page.count('class="lcard') == 3 and "The letter" in page and "Live founder alerts" in page and "Watches" in page
    assert "Everything founders did this week" in page and "Pick any company" in page
    assert 'class="pro">Members' not in page and "trial" not in page.lower(), "no members mark: everything on the page is free"
    assert "Paul Gu bought $1.3M of Upstart" in page and "1.33% &rarr; 1.38%" in page and "Upstart on Founder Led Equities" in page, "the sample is the email as it arrives"
    assert 'href="/alerts/">Alerts' in page, "the page carries the nav with itself in it"
    js = open(os.path.join(out, "alerts.js"), encoding="utf-8").read()
    assert 'tk:"FOUNDERS"' in js and "/api/subscribe" in js and "/api/watch" in js
    assert "trial" not in js.lower() and "/api/me" not in js and "ME&&ME.pro" not in js, "no session, no trial button"
    w = open(os.path.join(ROOT, "functions", "api", "watch.js"), encoding="utf-8").read()
    assert 'tk === "FOUNDERS"' in w and "for members" not in w
    run = open(os.path.join(ROOT, "functions", "api", "watch", "run.js"), encoding="utf-8").read()
    assert "tk = 'FOUNDERS'" in run and "e.founder" in run and "b.accs" in run, "FOUNDERS matches founder events; one email per event per address"
    assert "PRO_STATUSES" not in run and "proNow" not in run, "no subscription check in the sender"

def test_the_screens_are_pages_when_the_site_data_is_there(tmp_path):
    """THE SCREENS AS PAGES (2026-09-18): five addresses with the table in the
    HTML, built from universe.csv; absent the site data, nothing is written."""
    panel, founders, prices, sp, out = _fixture(tmp_path)
    bcp.main(panel, founders, prices, sp, out)
    assert not os.path.exists(os.path.join(out, "screens")), "no universe.csv, no screen pages"
    uni = os.path.join(out, "universe.csv")
    with open(uni, "w", encoding="utf-8") as fh:
        fh.write("ticker,company,ceo,pct,shares,never_sold,lt_code,lt_traded,pct_12m_ago,last_disc,last_buy\n"
                 "TSLA,Tesla,Elon Musk,28.44,1120000000,1,P,2026-08-01,15.8,,2026-08-01\n"
                 "SEALD,Sealed Co,Jane Doe,0.5,1000000,0,S,2026-01-01,,2026-01-01,\n")
    bcp.main(panel, founders, prices, sp, out)
    for slug in ("founder-led", "never-sold", "own-more-than-10-percent", "bought-this-year", "hired-under-1-percent"):
        page = open(os.path.join(out, "screens", slug, "index.html"), encoding="utf-8").read()
        assert "<title>" in page and 'rel="canonical"' in page and "Other screens" in page
    ns = open(os.path.join(out, "screens", "never-sold", "index.html"), encoding="utf-8").read()
    assert 'href="/company/TSLA/"' in ns and "28.44%" in ns and 'href="/company/SEALD/"' not in ns
    assert "15.80%" in ns, "the stake a year ago is on the row"
    hired = open(os.path.join(out, "screens", "hired-under-1-percent", "index.html"), encoding="utf-8").read()
    assert 'href="/company/SEALD/"' in hired and 'href="/company/TSLA/"' not in hired
    sm = open(os.path.join(out, "sitemap.xml"), encoding="utf-8").read()
    assert sm.count("/screens/") == 5
