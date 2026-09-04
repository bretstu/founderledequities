"""One page per company, built from one source.

The rules a company page applies -- what a cleaned series excludes, how a
trade is badged, how money is rounded -- are extracted from index.html at
build, not copied; these tests hold the extraction to that."""
import csv
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
                 "function cleanHist(", "function trajStats(", "function chartSVG(", "function evBadge(",
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
    assert "Sealed universe" not in sealed and "open to everyone" in tsla
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
    assert '<h1 id="thesis" data-pro="2|2"><b>1</b> of 1 chief executives own' in page, \
        "the hero is computed, not the placeholder, and carries the Pro sentence's numbers (the sealed row, at 41%, counts)"
    assert 'class="brow"' in page and 'href="/company/TSLA/"' in page and "28.44% of co." in page, "the board's rows are real HTML"
    assert 'class="hstat"' in page and "Founder-led companies" in page, "and so is the stat strip"
    assert 'id="herostats" data-pro="' in page, "and the Pro strip rides along, escaped, for the first paint"
    assert "<b>20</b> of 500" not in page
    # a subscriber's first byte already carries the Pro hero: the function
    # on / rewrites from the same attributes the stamp wrote, and the page
    # sets no cookie to do it
    fn = open(os.path.join(ROOT, "functions", "index.js"), encoding="utf-8").read()
    assert 'getAttribute("data-pro")' in fn and "HTMLRewriter" in fn and "isPro" in fn
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
    assert "28.44%" in body and "1,120,000,000" in body and "$370B" in body, "the answer band is in the HTML"
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
    assert '<h2 class="p"><span class="vh">Elon Musk owns </span>28.44%<span class="vh"> of Tesla, Inc.</span></h2>' in tsla, "the query phrase is the heading; the number is what shows"
    assert '"@type": "BreadcrumbList"' in tsla and '/companies/' in tsla
    assert '<div id="cmore"><div class="cmore">' in tsla or '<div id="cmore"></div>' in tsla, "neighbour links live outside the block the script redraws"
    sealed = open(out / "company" / "SEALD" / "index.html", encoding="utf-8").read()
    assert "2 filings by the chief executive are on record" in sealed, "a count, never a number behind the seal"
    assert "41.2" not in sealed
    sm = open(out / "sitemap.xml", encoding="utf-8").read()
    assert "<lastmod>2026-07-06</lastmod>" in sm, "a company page is dated by its as-of"


def test_the_record_has_two_views_and_one_story_per_chart():
    """The page script draws the price (default) and the stake, one point
    per month-end for the stake, dots at the filed price restated in
    today's shares, the largest sale and purchase labelled, a crosshair
    hover, and one draw-in on load. The shares-held view is gone."""
    js = open(os.path.join(ROOT, "assets", "company-page.js"), encoding="utf-8").read()
    assert "function monthEnds(" in js and "share count changed" in js and '"granted"' in js
    assert '["price","Price"' in js and '["pct","Stake"' in js
    assert '["shares","Shares held"' not in js and 'mode==="shares"' not in js
    assert "function priceChart(" in js and "split-adjusted. Dots sit at the price on the filing" in js
    assert "e.apa" in js, "dots sit at the filed price restated in today's shares"
    assert 'fetchText([`/prices/${C.tk}.csv`])' in js, "prices are fetched from the public root on every page"
    assert "function attachHover(" in js and "function drawIn(" in js
    assert 'class="ann"' in js and "linearGradient" in js
    assert "steps without a dot are grants, gifts, or the share count changing" in js.lower()
