"""THE PARTNERSHIP REGISTER (fle/partnerships.py, 2026-09-15): a company
whose founder's ownership is partnership units the site does not count is
excluded before the panel walks, and its page says why; one whose paired
class is on the cover is kept with a note. Nothing else changes."""
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "ops"))
from fle.partnerships import read_register, excluded, kept, note_for, path_for  # noqa: E402
from fle.universe import read_universe  # noqa: E402
import build_company_pages as bcp  # noqa: E402

REG = ("ticker,action,structure,company,ceo,cik,cover_classes,paired_class,units_reported,reason,source,as_of\n"
       "BX,exclude,up-c,Blackstone Inc.,Stephen A. Schwarzman,1393818,Common stock only,,Holdings units in Table II,"
       "The founder's ownership is Holdings units the site does not count.,https://www.sec.gov/x,2026-09-15\n"
       "CVNA,keep,up-c,CARVANA CO.,Ernest C. Garcia,1690820,Class A and Class B,Class B Common Stock,27666483 = Class B,"
       "Paired class on the cover and in Table I.,https://www.sec.gov/y,2026-09-15\n"
       "ZZZ,maybe,up-c,,,,,,,not a decision,,\n")


def test_the_register_reads_decisions_only(tmp_path):
    p = tmp_path / "partnerships.csv"; p.write_text(REG)
    r = read_register(str(p))
    assert set(r) == {"BX", "CVNA"}, "a row without a decision is not a row"
    assert set(excluded(str(p))) == {"BX"} and set(kept(str(p))) == {"CVNA"}
    assert "does not count" in note_for(r["BX"]) and "Schwarzman" in note_for(r["BX"])
    assert "Class B Common Stock" in note_for(r["CVNA"]) and "one for one" in note_for(r["CVNA"])
    assert read_register(str(tmp_path / "missing.csv")) == {}


def test_an_excluded_company_leaves_the_universe_before_the_panel_walks(tmp_path):
    (tmp_path / "universe").mkdir()
    u = tmp_path / "universe" / "universe-2026-08-31.csv"
    u.write_text("cik,ticker,company,added\n1393818,BX,Blackstone Inc.,\n1690820,CVNA,Carvana Co.,\n1318605,TSLA,Tesla,\n")
    assert [m.ticker for m in read_universe(str(u))] == ["BX", "CVNA", "TSLA"], "no register: everyone"
    (tmp_path / "universe" / "partnerships.csv").write_text(REG)
    assert path_for(str(u)).endswith(os.path.join("universe", "partnerships.csv"))
    assert [m.ticker for m in read_universe(str(u))] == ["CVNA", "TSLA"], "BX is gone; CVNA (keep) and TSLA stay"
    assert [m.ticker for m in read_universe(str(u), register=False)] == ["BX", "CVNA", "TSLA"], "and can be read whole on request"


def test_the_excluded_company_has_no_page_and_the_kept_page_carries_a_note(tmp_path):
    panel = tmp_path / "panel.csv"
    with open(panel, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "cik", "company", "ceo", "pct", "shares", "outstanding", "shares_as_of", "confidence", "form4_url"])
        w.writerow(["CVNA", "1690820", "CARVANA CO.", "Ernest C. Garcia", "13.36", "147049214", "1100463770", "2026-09-01", "high", "https://sec.gov/x"])
    (tmp_path / "universe").mkdir()
    sp = tmp_path / "universe" / "sp500-2026-09-10.csv"; sp.write_text("cik,ticker,company,added\n1690820,CVNA,Carvana,\n")
    (tmp_path / "universe" / "partnerships.csv").write_text(REG)
    prices = tmp_path / "prices.csv"; prices.write_text("ticker,close,as_of\nCVNA,67.80,2026-09-15\n")
    founders = tmp_path / "founders.csv"; founders.write_text('ticker,founder,evidence,source\nCVNA,yes,"co-founded",DEF 14A\n')
    out = tmp_path / "public"
    bcp.main(str(panel), str(founders), str(prices), str(sp), str(out))
    assert not (out / "company" / "BX").exists(), "an excluded company has no page: the real 404"
    cv = open(out / "company" / "CVNA" / "index.html", encoding="utf-8").read()
    assert 'class="sub structure-note"' in cv and "Class B Common Stock" in cv and "one for one" in cv
    sm = open(out / "sitemap.xml", encoding="utf-8").read()
    assert "/company/BX/" not in sm and "/company/CVNA/" in sm, "the kept page is in the sitemap; the excluded one is not"
    idx = open(out / "companies" / "index.html", encoding="utf-8").read()
    assert "/company/BX/" not in idx, "an excluded company is not in the screener"


def test_the_seeded_register_is_well_formed():
    p = os.path.join(ROOT, "universe", "partnerships.csv")
    r = read_register(p)
    assert set(r) >= {"CVNA", "BX", "MLTX", "PEB"}
    for tk, row in r.items():
        assert row["source"].startswith("https://www.sec.gov/") and row["as_of"] and row["reason"], tk
        assert row["structure"] in ("up-c", "upreit"), tk
    assert r["CVNA"]["action"] == "keep" and r["BX"]["action"] == "exclude"
