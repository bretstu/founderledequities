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
                 "function cleanHist(", "function trajStats(", "function evBadge(",
                 "function unchangedKind(", "function pctOf(", "function lagNote(", "const money=",
                 "const SEAL=", "let _cleanCache="):
        assert name in js, f"{name} is not marked @shared"
    assert "document.querySelector" not in js, "shared code must not touch the DOM"
    assert "state.pro" not in js and "state.live" not in js, "shared code must not read app state"
    if shutil.which("node"):
        r = subprocess.run(["node", "-e", "new Function(process.argv[1])", "--", js],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-400:]


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
    assert "<title>What Jane Doe owns of Sealed Co (SEALD)" in sealed
    assert "41.2" not in sealed and "1000000" not in sealed and "2400000" not in sealed
    assert '"sp": false' in sealed and '"row"' not in sealed
    assert '"price": 10.0' in sealed, "the close is public and rides on a sealed page; the shares do not"
    assert "Sealed universe" not in sealed and "open to everyone" not in tsla and " · S&amp;P 500</div>" in tsla and " · Pro</div>" in sealed
    # the machinery around them
    assert os.path.exists(os.path.join(out, "company.js"))
    assert 'src="/company.js?v=' in tsla and 'href="/site.css?v=' in tsla, "a new script is a new address"
    assert os.path.exists(os.path.join(out, "site.css"))
    sm = open(os.path.join(out, "sitemap.xml"), encoding="utf-8").read()
    assert sm.count("<loc>") == 5 and "/company/SEALD/" in sm and "/companies/" in sm, "every company is in the sitemap, sealed ones too, and the index page"
    robots = open(os.path.join(out, "robots.txt"), encoding="utf-8").read()
    assert "Disallow: /pro/" in robots and "Sitemap:" in robots
    js = open(os.path.join(out, "company.js"), encoding="utf-8").read()
    assert "function renderSealed(" in js and "function cleanHist(" in js, "the page's own logic follows the shared code"


def test_the_nav_on_a_page_points_home():
    idx = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    nav = bcp.extract_topnav(idx)
    assert 'href="/#board"' in nav and 'href="/about.html"' in nav
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
    panel, founders, prices, sp, _ = _fixture(tmp_path)
    out = tmp_path / "index.html"
    src = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    out.write_text(src, encoding="utf-8")
    st.main(panel, founders, prices, sp, str(out))
    page = out.read_text(encoding="utf-8")
    assert '<h1 id="thesis">What every <b>CEO</b> owns of the company they run.</h1>' in page, \
        "the headline is the purpose, the same for every reader, and needs no stamp"
    assert '<div class="n hl">1 of 1</div><div class="k">S&amp;P 500 CEOs own more than 5%</div>' in page, \
        "the free strip leads with the rarity against the S&P 500"
    assert "1 of them are sealed" in page, "the free subline states the seal as one fact"
    assert 'class="brow"' in page and 'href="/company/TSLA/"' in page and "28.44% of co." in page, "the board's rows are real HTML"
    assert 'class="hstat"' in page and "Founder-led companies" in page, "and so is the stat strip"
    assert 'id="herostats" data-pro="' in page and "CEOs own more than 5%" in html.unescape(page), \
        "and the Pro strip rides along, escaped, for the first paint, leading with the bare count"
    # a subscriber's first byte already carries the Pro hero: the function
    # on / rewrites from the same attributes the stamp wrote, and the page
    # sets no cookie to do it
    fn = open(os.path.join(ROOT, "functions", "_tier.js"), encoding="utf-8").read()
    assert 'getAttribute("data-pro")' in fn and "HTMLRewriter" in fn and "isPro" in fn
    assert 'span.sealnote' in fn, "a subscriber's page does not say N are sealed"
    assert "proPage" in open(os.path.join(ROOT, "functions", "index.js")).read()
    assert "proPage" in open(os.path.join(ROOT, "functions", "company", "[[path]].js")).read()
    assert "document.cookie" not in src


def test_the_published_perf_file_is_the_chart_cohort(tmp_path):
    """perf.csv on the site is founders plus the two benchmarks; whatever
    else is on disk stays on disk."""
    import build_site_data as bsd
    perf = tmp_path / "perf.csv"
    with open(perf, "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["ticker", "month", "close"])
        for tk in ("SPY", "RSP", "TSLA", "MSFT"):
            w.writerow([tk, "2026-08", 100])
    founders = tmp_path / "founders.csv"
    founders.write_text("ticker,founder,evidence,source\nTSLA,yes,co-founded,x\nMSFT,no,,x\n", encoding="utf-8")
    out = tmp_path / "out"; out.mkdir()
    n = bsd.write_perf_for_chart(str(perf), str(founders), str(out))
    kept = {row["ticker"] for row in csv.DictReader(open(out / "perf.csv", encoding="utf-8"))}
    assert kept == {"SPY", "RSP", "TSLA"} and n == 3


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
    for label in ("Value", "Market cap", "Shares held", "1Y return"):
        assert f'<div class="k">{label}</div>' in body, "the band uses the table's labels"
    assert "from 21.10% in 2016 to 28.44% on 2026-07-06" in body, "the record, as a sentence"
    assert "1 sale and 1 purchase" in body, "kept-apart trades do not count"
    assert "planned sale of $24.2M on 2026-08-29" in body, "the last trade that moved it"
    assert "names Elon Musk a founder" in body
    sealed = open(out / "company" / "SEALD" / "index.html", encoding="utf-8").read()
    sbody = sealed[sealed.index('<div id="cbody">'):sealed.index('<div class="creport"')]
    assert "chief executive of" in sbody and "Pro tier" in sbody and "41.2" not in sbody, "a sealed page: the person and the offer, no numbers"
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
    assert '<div class="k">Elon Musk owns</div><h2 class="p">28.44%</h2>' in tsla, \
        "the query phrase is the card, read top to bottom, with the number as the heading"
    assert '"@type": "BreadcrumbList"' in tsla and '/companies/' in tsla
    assert '<div id="cmore"><div class="cmore">' in tsla or '<div id="cmore"></div>' in tsla, "neighbour links live outside the block the script redraws"
    sealed = open(out / "company" / "SEALD" / "index.html", encoding="utf-8").read()
    assert "2 filings by the chief executive are on record" in sealed, "a count, never a number behind the seal"
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
    """Value, Market cap, Shares held, 1Y return: the home table's labels,
    in the home page's own strip. The 3-year change cell is gone: it read
    "+5.0% since 2026-01" for a company eight months old, and the table it
    was meant to match never had such a column. Confidence is a plain
    word that opens the reasons, shown only when the figure is not clean."""
    js = open(os.path.join(ROOT, "assets", "company-page.js"), encoding="utf-8").read()
    band = js[js.index("function stat("):js.index("/* ---- the record:")]
    for label in ('"Value"', '"Market cap"', '"Shares held"', '"1Y return"'):
        assert label in band, f"{label} is a stat"
    assert "3-year" not in band[band.index("function band("):] and "trajStats" not in js
    assert "never estimated" not in band, "the answer needs no sentence beside it"
    assert 'class="cband">' in band and 'class="cstat"' in band, "five cards: the answer and four figures"
    assert '<details class="cconf">' in band and 'confidence</summary>' in band
    assert 'r.conf!=="high"' in band, "a clean figure says nothing about confidence"
    assert "\u2014" not in js, "no em dashes"


def test_a_sealed_page_says_whose_stake_is_in_pro(tmp_path):
    panel, founders, prices, sp, _ = _fixture(tmp_path)
    out = tmp_path / "pub"
    bcp.main(panel, founders, prices, sp, str(out))
    sealed = open(out / "company" / "SEALD" / "index.html", encoding="utf-8").read()
    assert "Jane Doe&#x27;s stake</div><h2 class=\"p\">is in Pro" in sealed
    assert bcp.poss("Jabbok Schlacks") == "Jabbok Schlacks'"
    js = open(os.path.join(ROOT, "assets", "company-page.js"), encoding="utf-8").read()
    assert "is in Pro" in js and "const poss=" in js


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
    assert '<div class="k">1Y return</div><div class="v up">+50.0%</div>' in body
    assert '"ret_1y": "50.0000"' in tsla, "the script's row carries the same figure"
    bcp.main(panel, founders, prices, sp, str(out))
    tsla = open(out / "company" / "TSLA" / "index.html", encoding="utf-8").read()
    assert '<div class="k">1Y return</div><div class="v none">&mdash;</div>' in tsla
    assert "ret_1y" not in tsla


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
