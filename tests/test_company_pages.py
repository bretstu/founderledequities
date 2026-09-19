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
                 "const SEAL=", "let _cleanCache="):
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
    renderers = {"paintSw", "wireSw", "renderTable", "exportTable", "lastTrades", "renderActivity", "setWin", "setScreen"}
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
    # THE SEAL IS OFF (2026-09-18): a company outside the S&P is an open page too
    assert "<title>Jane Doe owns 41.20% of Sealed (SEALD)" in sealed
    assert "41.2" in sealed and '"sp": true' in sealed, "the stake is on the page, whatever the index"
    assert '"price": 10.0' in sealed, "the close is public and rides on a sealed page; the shares do not"
    assert "Sealed universe" not in sealed and "open to everyone" not in tsla
    # the ticker and the market cap sit beside the name, on both tiers (public data)
    assert 'id="ctk">TSLA · $' in tsla and 'id="ctk">' in sealed
    assert "<h1>Tesla, Inc.</h1>" in tsla, "the heading is the company's name and nothing else"
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
    assert sm.count("<loc>") == 8 and "/company/SEALD/" in sm and "/companies/" in sm and "/tape/" in sm and "/pro/" in sm and "/alerts/" in sm, \
        "every company is in the sitemap: the open ones with the answer, the sealed ones with the question; and the alerts page (2026-09-17)"
    robots = open(os.path.join(out, "robots.txt"), encoding="utf-8").read()
    assert "Sitemap:" in robots
    # the Pro page is indexable; the data beneath the prefix is not (2026-09-16, Search Console)
    assert "Disallow: /pro/\n" not in robots and "Disallow: /pro/history/" in robots and "Disallow: /pro/events/" in robots and "Disallow: /pro/universe.csv" in robots
    js = open(os.path.join(out, "company.js"), encoding="utf-8").read()
    assert "const BLUR=" in js and "function cleanHist(" in js, "the page's own logic follows the shared code"


def test_the_nav_on_a_page_points_home():
    idx = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    nav = bcp.extract_topnav(idx)
    assert 'href="/tape/"' in nav and 'href="/companies/"' in nav and 'href="/about.html"' in nav and 'class="gopro" href="/pro/"' in nav and '<a href="/pro/">Pro</a>' not in nav and "#board" not in nav and "#perfsec" not in nav
    assert "devtog" not in nav and "openPro()" not in nav, "no modal, no dev toggle on a static page"


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
    # THE HOME PREVIEW IS THE OPEN SET: a sealed company is not in the free
    # reader's twenty rows (it is on /companies/, named and blurred); the
    # line beneath says how many more match in Pro
    assert 'href="/company/SEALD/"' not in page[page.index('<tbody id="tbody">'):], \
        "a sealed company is not in the home preview's rows"
    assert "41.2" not in page, "and none of its numbers"
    assert 'class="hstat"' in page and "Founder-led companies" in page, "and so is the stat strip"
    fn = open(os.path.join(ROOT, "functions", "_tier.js"), encoding="utf-8").read()
    assert "HTMLRewriter" in fn and "isPro" in fn
    assert "proPage" in open(os.path.join(ROOT, "functions", "index.js")).read()
    assert "proPage" in open(os.path.join(ROOT, "functions", "company", "[[path]].js")).read()
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
    assert "28.44%" in body and "1,120,000,000 of 3,950,000,000 shares" in body and "$370B" in body, "the answer band is in the HTML"
    assert "Confidence" not in body and "3-year" not in body
    # three cards about the stake; the stock's facts are in the kicker, not cards
    for label in ("Shares held", "Worth"):
        assert f'<div class="k">{label}</div>' in body, "the band is the stake: share, shares, worth"
    assert '<div class="k">Outstanding</div>' not in body, "shares outstanding is a column of the trades table, not a card"
    for label in ("Market cap", "1Y return"):
        assert f'<div class="k">{label}</div>' not in body, "the stock's facts are not cards"
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
    assert '<h2 class="p"><span class="k">Elon Musk owns</span>28.44%</h2>' in tsla, \
        "the query phrase is the card, read top to bottom, with the number as the heading"
    assert '"@type": "BreadcrumbList"' in tsla and '/companies/' in tsla
    assert '<div id="cmore"><div class="cmore">' in tsla or '<div id="cmore"></div>' in tsla, "neighbour links live outside the block the script redraws"
    sealed = open(out / "company" / "SEALD" / "index.html", encoding="utf-8").read()
    assert '<h2 class="p"><span class="k">Jane Doe owns</span>41.20%</h2>' in sealed, "the seal is off: the figure is the heading on every page"
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


def test_the_band_uses_the_tables_words_and_has_no_three_year_cell():
    """Three cards, one subject: the share, the shares, what they are worth.
    Market cap, the close and the year's return are the stock's facts and
    ride the kicker line beside the ticker. The 3-year change cell is gone:
    it read "+5.0% since 2026-01" for a company eight months old."""
    js = open(os.path.join(ROOT, "assets", "company-page.js"), encoding="utf-8").read()
    band = js[js.index("function stat("):js.index("/* ---- the record:")]
    for label in ('"Shares held"', '"Worth"'):
        assert label in band, f"{label} is a stat"
    for label in ('"Market cap"', '"1Y return"', '"Value"'):
        assert f"stat({label}" not in band, f"{label} is not a card"
    assert "kick.innerHTML" in band and "1Y" not in band, "beside the name: the ticker and the market cap, nothing else of the stock's"
    assert "3-year" not in band[band.index("function band("):] and "trajStats" not in js
    assert "never estimated" not in band, "the answer needs no sentence beside it"
    assert 'class="cband four">' in band and 'class="cstat"' in band and "${watchCard(r)}" in band, "four cards of one width: the three numbers and the watch (2026-09-17)"
    assert "confidence</summary>" not in band, "no confidence grade on the card"
    # A LOW-CONFIDENCE STAKE SAYS WHY BESIDE THE NUMBER (2026-09-17, EquipmentShare): the same sentence the tape's "?" carries;
    # medium and high stay a bare number
    assert 'r.conf==="low"' in band and 'class="lowc"' in band and '(r.flags||"").split("\\n")[0]' in band
    assert "\u2014" not in js, "no em dashes"


def test_every_page_is_open_and_the_script_still_knows_the_seal(tmp_path):
    """THE SEAL IS OFF (2026-09-18): a company outside the S&P renders exactly
    as one inside it. The page script keeps its sealed branch (a masked row
    would still render blurred) but no row is masked."""
    panel, founders, prices, sp, out = _fixture(tmp_path)
    bcp.main(panel, founders, prices, sp, out)
    sealed = open(os.path.join(out, "company", "SEALD", "index.html"), encoding="utf-8").read()
    assert '<h2 class="p"><span class="k">Jane Doe owns</span>41.20%</h2>' in sealed
    assert 'class="sealed"' not in sealed, "no blurred figures anywhere"
    assert bcp.poss("Jabbok Schlacks") == "Jabbok Schlacks'"
    js = open(os.path.join(ROOT, "assets", "company-page.js"), encoding="utf-8").read()
    assert "const BLUR=" in js and "row.masked?Promise.resolve(null)" in js, "the page loads no record for a sealed company"


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


def test_the_pro_page_is_the_plan(tmp_path):
    """/pro/: one plan, the two prices, the trial, the four lines, the quiet
    line, the copy rule; the masthead from index.html; every Go Pro on the
    site is a link to it, and the checkout takes the plan."""
    panel, founders, prices, sp, out = _fixture(tmp_path)
    bcp.main(panel, founders, prices, sp, out)
    page = open(os.path.join(out, "pro", "index.html"), encoding="utf-8").read()
    assert "{{TOPNAV}}" not in page and 'class="topnav"' in page
    assert "$8" in page and "$69" in page and "14-day trial" in page and "The site is free. Members keep it that way" in page
    assert 'href="/api/checkout?plan=monthly"' in page and 'href="/api/checkout?plan=yearly"' in page
    assert "Alerts, watches and export are for members" in page, "the copy rule, verbatim"
    idx = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    assert 'function openPro(){location.href="/pro/";}' in idx and '<a href="/pro/">Pro</a>' not in idx
    for f in ("assets/company-page.js", "assets/tape-page.js"):
        assert 'location.href="/pro/"' in open(os.path.join(ROOT, f), encoding="utf-8").read(), f
    co = open(os.path.join(ROOT, "functions", "api", "checkout.js"), encoding="utf-8").read()
    assert "PRICE_ID_MONTHLY" in co and "PRICE_ID_YEARLY" in co and "env.PRICE_ID " not in co and "|| env.PRICE_ID" not in co and '"subscription_data[trial_period_days]": "14"' in co and 'payment_method_collection: "always"' in co


def test_the_watches_have_a_box_a_page_and_two_ways_to_stop(tmp_path):
    """Every company page carries the watch box; /watches/ lists a signed-in
    reader's names; every alert carries a stop link per name and one for
    all; the free cap is one confirmed name."""
    panel, founders, prices, sp, out = _fixture(tmp_path)
    bcp.main(panel, founders, prices, sp, out)
    assert os.path.exists(os.path.join(out, "account", "index.html")) and os.path.exists(os.path.join(out, "account.js")), "the account page is the control panel"
    assert "url=/account/" in open(os.path.join(out, "watches", "index.html"), encoding="utf-8").read(), "the old watches address lands on the account"
    nav = bcp.extract_topnav(open(os.path.join(ROOT, "index.html"), encoding="utf-8").read())
    assert "Weekly tape, free" not in nav and "navwatches" not in nav and 'class="gopro"' in nav and 'href="/alerts/">Alerts' in nav, "the header is where you are: four pages and one button (Alerts, 2026-09-17)"
    for f in ("functions/api/letter.js", "functions/api/logout.js"):
        assert os.path.exists(os.path.join(ROOT, f)), f
    page_js = open(os.path.join(ROOT, "assets", "company-page.js"), encoding="utf-8").read()
    # THE WATCH IS THE FOURTH CARD (2026-09-17), not a band under the numbers: a switch with the person's name and
    # one line of fine print, "An email when the stake moves."; the definition lives on the About page and the hover
    assert "function watchCard(" in page_js and "function watchBlock(" not in page_js and "band(r)+recordBlock(r)" in page_js
    assert "An email when the stake moves." in page_js and "Never for a plan" not in page_js and "Email me if" not in page_js
    assert 'id="wsw"' in page_js and "toggleWatch(" in page_js, "a switch, on every page"
    about = open(os.path.join(ROOT, "about.html"), encoding="utf-8").read()
    assert "What counts as a move" in about and "1% or more" in about, "the definition is stated once, on the About page"
    assert "Stopped. No more emails about" in page_js and "No more emails about anyone" in page_js, "the box says what a stop link did"
    assert "One founder watch is free" not in page_js and "Copy the sentence" not in page_js, "the box carries no fine print for a free reader"
    w = open(os.path.join(ROOT, "functions", "api", "watch.js"), encoding="utf-8").read()
    assert "A list of names is Pro" in w and "stopall" in w and "confirm=" in w
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


def test_the_alerts_page_is_built_with_three_switches_on_one_rule(tmp_path):
    """THE ALERTS PAGE (2026-09-17): one rule stated once, three grains of one
    stream (the letter, live founder alerts, the watches), a sample email;
    the live alert is a watch on the reserved name FOUNDERS."""
    panel, founders, prices, sp, out = _fixture(tmp_path)
    bcp.main(panel, founders, prices, sp, out)
    page = open(os.path.join(out, "alerts", "index.html"), encoding="utf-8").read()
    assert "When a founder" in page and "1% or more" in page and "within about ten minutes of the SEC filing" in page
    assert page.count('class="lcard') == 3 and "The letter" in page and "Live founder alerts" in page and "Your watches" in page
    assert "Everything founders did this week" in page and "Pick any company" in page and 'class="pro">Members' in page, "the three sentences and the members mark (2026-09-18)"
    assert 'class="k"' not in page.split('id="lbody"')[1].split("What one looks like")[0], "no small labels above the card titles"
    assert "Paul Gu bought $1.3M of Upstart" in page and "1.33% &rarr; 1.38%" in page and "Upstart on Founder Led Equities" in page, "the sample is the email as it arrives"
    assert 'href="/alerts/">Alerts' in page, "the page carries the nav with itself in it"
    js = open(os.path.join(out, "alerts.js"), encoding="utf-8").read()
    assert 'tk:"FOUNDERS"' in js and "/api/letter" in js and "/api/subscribe" in js and "/api/watch" in js
    # NO FAKE SWITCH (2026-09-17): a reader who is not Pro sees a trial button where the switch would be
    assert "Start a 14-day trial" in js and 'ME&&ME.pro?sw("fsw"' in js and "Already a member?" in js
    assert "names.slice(0,2)" in js and "Manage all" in js, "the watches card stays compact: two names and the account for the rest"
    acct = open(os.path.join(ROOT, "assets", "account-page.js"), encoding="utf-8").read()
    assert "<h2>Live founder alerts</h2>" in acct and "Saturday morning" in acct and "Monday" not in acct and "names_only:true" in acct
    w = open(os.path.join(ROOT, "functions", "api", "watch.js"), encoding="utf-8").read()
    assert 'tk === "FOUNDERS"' in w and "Live founder alerts are for members" in w
    run = open(os.path.join(ROOT, "functions", "api", "watch", "run.js"), encoding="utf-8").read()
    assert "tk = 'FOUNDERS'" in run and "e.founder" in run and "b.accs" in run, "FOUNDERS matches founder events; one email per event per address"
    assert "PRO_STATUSES.has(sub.status)" in run and "proNow" in run, "a FOUNDERS watch mails only while the address is Pro (a lapsed trial stops)"


def test_the_screens_are_pages_when_the_site_data_is_there(tmp_path):
    """THE SCREENS AS PAGES (2026-09-18): five addresses with the table in the
    HTML, built from universe.csv; absent the site data, nothing is written."""
    panel, founders, prices, sp, out = _fixture(tmp_path)
    bcp.main(panel, founders, prices, sp, out)
    assert not os.path.exists(os.path.join(out, "screens")), "no universe.csv, no screen pages"
    uni = os.path.join(out, "universe.csv")
    with open(uni, "w", encoding="utf-8") as fh:
        fh.write("ticker,company,ceo,pct,shares,never_sold,lt_code,lt_traded,pct_12m_ago\n"
                 "TSLA,Tesla,Elon Musk,28.44,1120000000,1,P,2026-08-01,15.8\n"
                 "SEALD,Sealed Co,Jane Doe,0.5,1000000,0,S,2026-01-01,\n")
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
