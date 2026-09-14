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
    renderers = {"paintSw", "wireSw", "renderTable", "exportTable", "lastTrades", "renderActivity", "setWin"}
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
    assert "<title>Elon Musk owns 28.44% of Tesla, Inc. (TSLA)" in tsla
    assert "worth $370B" in tsla, "the description prices the stake at the close, rounded as the page rounds"
    assert '"pct": "28.4412"' in tsla and '"sp": true' in tsla
    assert '"price_date": "2026-09-02"' in tsla, "the close's date rides with the price (prices.csv says as_of)"
    assert 'href="https://founderledequities.com/company/TSLA/"' in tsla
    assert "co-founded the Company" in tsla, "the founder evidence rides in the shell (as data for the receipt)"
    # the sealed page carries the person and the verdict, and no figure
    assert "<title>How much of Sealed Co does Jane Doe own? (SEALD)" in sealed
    assert "41.2" not in sealed and "1000000" not in sealed, "no stake, no shares on a sealed page"
    assert "2400000" in sealed, "the cover page's count is public and the page carries it"
    assert '"sp": false' in sealed and '"row"' not in sealed
    assert '"price": 10.0' in sealed, "the close is public and rides on a sealed page; the shares do not"
    assert "Sealed universe" not in sealed and "open to everyone" not in tsla
    # the ticker and the market cap sit beside the name, on both tiers (public data)
    assert 'id="ctk">TSLA · $' in tsla and 'id="ctk">' in sealed
    assert "<h1>Tesla, Inc.</h1>" in tsla, "the heading is the company's name and nothing else"
    # a sealed page is a teaser: the question as its heading, no robots directive, in the sitemap
    assert '<meta name="robots"' not in sealed and "<h2 class=\"cq2\">How much of" in sealed and "does " in sealed
    assert "<title>How much of" in sealed and 'class="sealed"' in sealed, "the question, and blurred figures where the stake would be"
    sitemap = open(os.path.join(out, "sitemap.xml"), encoding="utf-8").read()
    assert "/company/TSLA/" in sitemap and "/company/SEALD/" in sitemap
    # the machinery around them
    assert os.path.exists(os.path.join(out, "company.js"))
    assert 'src="/company.js?v=' in tsla and 'href="/site.css?v=' in tsla, "a new script is a new address"
    assert os.path.exists(os.path.join(out, "site.css"))
    sm = open(os.path.join(out, "sitemap.xml"), encoding="utf-8").read()
    assert sm.count("<loc>") == 7 and "/company/SEALD/" in sm and "/companies/" in sm and "/tape/" in sm and "/pro/" in sm, \
        "every company is in the sitemap: the open ones with the answer, the sealed ones with the question"
    robots = open(os.path.join(out, "robots.txt"), encoding="utf-8").read()
    assert "Disallow: /pro/" in robots and "Sitemap:" in robots
    js = open(os.path.join(out, "company.js"), encoding="utf-8").read()
    assert "const BLUR=" in js and "function cleanHist(" in js, "the page's own logic follows the shared code"


def test_the_nav_on_a_page_points_home():
    idx = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    nav = bcp.extract_topnav(idx)
    assert 'href="/tape/"' in nav and 'href="/companies/"' in nav and 'href="/about.html"' in nav and 'href="/pro/"' in nav and "#board" not in nav and "#perfsec" not in nav
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
    assert '<h1 id="thesis">What the person running the company still owns.</h1>' in page, \
        "the headline is the purpose, the same for every reader, and needs no stamp"
    # ONE STRIP FOR EVERYONE: three aggregates over every company, no company's stake
    assert '<div class="n">2</div><div class="k">CEOs own more than 5%</div>' in page, \
        "the strip counts over every company, the sealed one included"
    strip = page[page.index('id="herostats"'):page.index('class="herobtns"')]
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


def test_the_index_chart_is_drawn_once_for_method(tmp_path):
    """Founders against the index is a static SVG (ops/perf_svg.py) drawn at
    deploy from perf.csv for the Method page: the S&P founders' equal-weight
    line against SPY and RSP, growth of $10,000, with the caveat in the
    page. Nothing on the home page loads perf.csv any more."""
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location("perf_svg", pathlib.Path(ROOT) / "ops" / "perf_svg.py")
    ps = importlib.util.module_from_spec(spec); spec.loader.exec_module(ps)
    (tmp_path / "sp.csv").write_text("ticker\nAAA\nBBB\n")
    (tmp_path / "founders.csv").write_text("ticker,founder\nAAA,yes\nBBB,yes\nCCC,yes\nDDD,yes\nEEE,yes\nFFF,yes\n")
    months = [f"2024-{m:02d}" for m in range(1, 13)]
    rows = ["ticker,month,close"]
    for tk, start, step in (("SPY", 100, 1), ("RSP", 100, 0.5), ("AAA", 10, 1), ("BBB", 20, 1), ("CCC", 5, 1), ("DDD", 5, 1), ("EEE", 5, 1), ("FFF", 5, 1)):
        for i, m in enumerate(months):
            rows.append(f"{tk},{m},{start + step * i}")
    (tmp_path / "perf.csv").write_text("\n".join(rows) + "\n")
    # only the S&P founders (AAA, BBB) are the cohort; fewer than five founders means no line
    assert ps.series(str(tmp_path / "perf.csv"), str(tmp_path / "founders.csv"), str(tmp_path / "sp.csv")) is None
    (tmp_path / "sp.csv").write_text("ticker\nAAA\nBBB\nCCC\nDDD\nEEE\nFFF\n")
    d = ps.series(str(tmp_path / "perf.csv"), str(tmp_path / "founders.csv"), str(tmp_path / "sp.csv"))
    assert d and d["count"] == 6 and d["months"][0] == "2024-01" and len(d["founders"]) == 12
    assert d["founders"][-1] > d["spy"][-1] > d["rsp"][-1], "the fixture's founders outgrow SPY, SPY outgrows RSP"
    svg = ps.svg(d)
    assert svg.startswith("<svg") and "Founders index" in svg and "S&amp;P 500 (SPY)" in svg and "$10,000" in svg
    idx = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    assert "perf.csv" not in idx and "function perfSeries(" not in idx, "the home page no longer draws the chart"
    about = open(os.path.join(ROOT, "about.html"), encoding="utf-8").read()
    assert "<!--PERF_SVG-->" in about and "A portrait, not a strategy." in about

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
    for label in ("Shares held", "Outstanding", "Worth"):
        assert f'<div class="k">{label}</div>' in body, "the band is the stake: share, shares, outstanding, worth"
    for label in ("Market cap", "1Y return"):
        assert f'<div class="k">{label}</div>' not in body, "the stock's facts are not cards"
    assert "from 21.10% in 2016 to 28.44% on 2026-07-06" in body, "the record, as a sentence"
    assert "1 sale and 1 purchase" in body, "kept-apart trades do not count"
    assert "planned sale of $24.2M on 2026-08-29" in body, "the last trade that moved it"
    assert "names Elon Musk a founder" in body
    sealed = open(out / "company" / "SEALD" / "index.html", encoding="utf-8").read()
    sbody = sealed[sealed.index('<div id="cbody">'):sealed.index('<div class="creport"')]
    assert "chief executive of" in sbody and 'class="sealed"' in sbody and "41.2" not in sbody, "a sealed page: the question, the person, the blurred figures, no stake"
    idx = open(out / "companies" / "index.html", encoding="utf-8").read()
    assert 'href="/company/TSLA/"' in idx and 'href="/company/SEALD/"' in idx, "every page has a plain link"
    assert "FOUNDER" in idx and "Pro</span>" in idx


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
    assert "2 Form 4 filings on record since 2016, the most recent filed 2021-01-01" in sealed, "a count and a date, never a number behind the seal"
    assert "41.2" not in sealed
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
    for label in ('"Shares held"', '"Outstanding"', '"Worth"'):
        assert label in band, f"{label} is a stat"
    for label in ('"Market cap"', '"1Y return"', '"Value"'):
        assert f"stat({label}" not in band, f"{label} is not a card"
    assert "kick.innerHTML" in band and "1Y" not in band, "beside the name: the ticker and the market cap, nothing else of the stock's"
    assert "3-year" not in band[band.index("function band("):] and "trajStats" not in js
    assert "never estimated" not in band, "the answer needs no sentence beside it"
    assert 'class="cband four">' in band and 'class="cstat"' in band, "four cards of one width"
    assert "confidence</summary>" not in band, "confidence is not on the card; the reasons block below the chart carries it"
    assert 'r.conf' not in band, "the band carries no confidence word; the reasons block below the chart does"
    assert "\u2014" not in js, "no em dashes"


def test_a_sealed_page_is_the_open_page_with_the_seals_on_the_figures(tmp_path):
    """The same card and the same table shape; a blurred placeholder where
    the stake, the shares and the worth would be; the cover page's count
    shown; one line of prose; no box (the nav's button is the one)."""
    panel, founders, prices, sp, _ = _fixture(tmp_path)
    out = tmp_path / "pub"
    bcp.main(panel, founders, prices, sp, str(out))
    sealed = open(out / "company" / "SEALD" / "index.html", encoding="utf-8").read()
    assert '<h2 class="p"><span class="k">Jane Doe owns</span><span class="sealed"' in sealed
    assert sealed.count('class="sealed"') == 3, "the share, the shares, the worth"
    assert '<div class="k">Outstanding</div><div class="v ">2,400,000</div>' in sealed
    assert "Go Pro, $5" not in sealed and "cseal" not in sealed, "no box on the page"
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
    assert "$15" in page and "$150" in page and "14-day trial" in page and "S&amp;P 500 current stakes stay free" in page
    assert 'href="/api/checkout?plan=monthly"' in page and 'href="/api/checkout?plan=yearly"' in page
    assert "the last twelve months are open" in page, "the copy rule, verbatim"
    idx = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    assert 'function openPro(){location.href="/pro/";}' in idx and 'href="/pro/">Pro</a>' in idx
    for f in ("assets/company-page.js", "assets/tape-page.js"):
        assert 'location.href="/pro/"' in open(os.path.join(ROOT, f), encoding="utf-8").read(), f
    co = open(os.path.join(ROOT, "functions", "api", "checkout.js"), encoding="utf-8").read()
    assert "PRICE_ID_MONTHLY" in co and "PRICE_ID_YEARLY" in co and "env.PRICE_ID " not in co and "|| env.PRICE_ID" not in co and '"subscription_data[trial_period_days]": "14"' in co and 'payment_method_collection: "always"' in co
