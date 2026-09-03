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
    assert sm.count("<loc>") == 4 and "/company/SEALD/" in sm, "every company is in the sitemap, sealed ones too"
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
    assert '<h1 id="thesis"><b>1</b> of 1 chief executives own' in page, "the hero is computed, not the placeholder"
    assert 'class="brow"' in page and 'href="/company/TSLA/"' in page and "28.44% of co." in page, "the board's rows are real HTML"
    assert 'class="hstat"' in page and "Founder-led companies" in page, "and so is the stat strip"
    assert "<b>20</b> of 500" not in page
