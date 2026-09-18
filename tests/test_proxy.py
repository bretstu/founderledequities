"""THE PROXY CHECK (fle/proxy.py, 2026-09-18): the company's own table on its
record date against the history on that date. The verdict names the line
when the difference is one of ours; nothing here changes a number."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fle.proxy import read_proxy, verdict, ours_on, ProxyRead  # noqa: E402

META = """<html><body>
<p>SECURITY OWNERSHIP OF CERTAIN BENEFICIAL OWNERS AND MANAGEMENT</p>
<p>The following table sets forth information regarding the beneficial ownership of our Class A common stock and Class B common stock as of March 31, 2026 by each of our directors and named executive officers. Applicable percentage ownership is based on 2,205,128,509 shares of Class A common stock and 342,377,716 shares of Class B common stock outstanding as of March 31, 2026.</p>
<table>
<tr><th>Name of Beneficial Owner</th><th>Shares of Class A Common Stock Beneficially Owned</th><th>%</th><th>Shares of Class B Common Stock Beneficially Owned</th><th>%</th><th>% of Total Voting Power</th></tr>
<tr><td>Named Executive Officers and Directors:</td><td></td><td></td><td></td><td></td><td></td></tr>
<tr><td>Mark Zuckerberg(1)</td><td>&#8212;</td><td>*</td><td>341,232,288</td><td>99.7%</td><td>61.2%</td></tr>
<tr><td>Susan Li(2)</td><td>124,010</td><td>*</td><td>&#8212;</td><td>*</td><td>*</td></tr>
</table>
<p>(1) Consists of (i) 3,388,097 shares of Class B common stock held by Mr. Zuckerberg as trustee of a trust, and (ii) 337,844,191 shares of Class B common stock held of record by entities of which Mr. Zuckerberg is the sole member. Excludes 1,231,037 shares of Class A common stock held by the Chan Zuckerberg Biohub, a non-profit, as to which Mr. Zuckerberg disclaims beneficial ownership.</p>
<p>(2) Consists of 124,010 shares of Class A common stock and includes 40,000 shares of Class A common stock subject to RSUs that will vest within 60 days of March 31, 2026.</p>
</body></html>"""

SINGLE = """<html><body>
<p>The table below shows shares beneficially owned as of April 15, 2026.</p>
<table>
<tr><td>Name</td><td>Number of Shares Beneficially Owned</td><td>Percent of Class</td></tr>
<tr><td>Jen-Hsun Huang (3)</td><td>812,394,004</td><td>3.3%</td></tr>
<tr><td>Colette Kress</td><td>1,230,100</td><td>*</td></tr>
</table>
<p>(3) Includes 1,000,000 shares subject to options held by Mr. Huang that are exercisable within 60 days of April 15, 2026.</p>
</body></html>"""

THREE_COL = """<html><body>
<p>Beneficial ownership as of March 1, 2026.</p>
<table>
<tr><th>Name</th><th>Shares Owned</th><th>Shares Acquirable Within 60 Days</th><th>Total Beneficial Ownership</th><th>Percent</th></tr>
<tr><td>Todd McKinnon</td><td>2,000,000</td><td>150,000</td><td>2,150,000</td><td>1.2%</td></tr>
</table></body></html>"""


def test_the_dual_class_row_is_read_with_its_record_date():
    r = read_proxy(META, "Mark Zuckerberg", "2026-04-20")
    assert r.record_date == "2026-03-31" and r.shares == 341_232_288, (r.record_date, r.shares, r.row)
    assert r.options is None, "the 60-day RSUs are Susan Li's, not his"


def test_the_single_class_row_and_the_options_formula():
    r = read_proxy(SINGLE, "Jen-Hsun Huang", "2026-05-01")
    assert r.record_date == "2026-04-15" and r.shares == 812_394_004 and r.options == 1_000_000, (r.record_date, r.shares, r.options)


def test_a_total_column_is_used_alone():
    r = read_proxy(THREE_COL, "Todd McKinnon", "2026-04-01")
    assert r.shares == 2_150_000, "owned + acquirable are not summed on top of the total"


def test_the_verdict_names_the_line_the_proxy_leaves_out():
    read = ProxyRead(proxy_date="2026-04-20", record_date="2026-03-31", shares=341_232_288)
    lines = [("Class A Common Stock by Chan Zuckerberg Biohub, Inc.", 1_231_037.0), ("Class B Common Stock by CZI Holdings, LLC", 100_119_267.0)]
    lvl, text = verdict(read, 342_463_325.0, lines)
    assert lvl == "warn" and "Biohub" in text and "exclusions register" in text
    assert verdict(ProxyRead(shares=100.0, record_date="2026-01-01"), 100.5, [])[0] == "pass"
    lvl, text = verdict(ProxyRead(shares=812_394_004.0, record_date="2026-04-15", options=1_000_000.0), 811_394_004.0, [])
    assert lvl == "pass" and "options within 60 days" in text
    assert verdict(ProxyRead(shares=100.0, record_date="2026-01-01"), 90.0, [])[0] == "fail"
    assert verdict(ProxyRead(shares=100.0, record_date="2026-01-01"), 97.0, [])[0] == "warn"
    assert verdict(ProxyRead(note="no ownership row names the chief executive"), 5.0, [])[0] == "none"


def test_ours_on_the_record_date_is_the_history_row_on_or_before_it():
    rows = [{"form": "4", "date": "2026-03-01", "shares": "100"}, {"form": "4", "date": "2026-03-30", "shares": "120"},
            {"form": "4", "date": "2026-04-05", "shares": "80"}, {"form": "10-Q", "date": "2026-03-31", "shares": "120"}]
    assert ours_on(rows, "2026-03-31") == (120.0, "2026-03-30"), "never the filing after the record date"


def test_the_grade_reads_the_check_as_its_fifth_question():
    from fle.grade import proxy, grade_row, CHECKS
    assert "proxy" in CHECKS
    assert proxy({}, {"level": "warn", "sentence": "the proxy leaves out a line we count"}) == ("warn", "the proxy leaves out a line we count")
    assert proxy({}, None) == ("pass", "") and proxy({}, {"level": "none", "sentence": "x"}) == ("pass", "")
    row = {"pct": "5", "shares": "100", "owner_cik": "1", "problems": "", "cautions": "", "lines_stated": "2026-09-01|2026-09-01", "count_as_of": "2026-06-30", "outstanding": "2000", "classes": "1", "is_officer": "1"}
    g = grade_row(row, [], None, {"level": "fail", "sentence": "the proxy differs by +9.0%"})
    assert g["confidence"] == "low" and g["proxy"].startswith("fail:") and g["reason"] == "the proxy differs by +9.0%"
