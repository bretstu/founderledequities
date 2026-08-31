"""The universe."""
from fle.universe import parse_members


ROWS = """
<table><tr><th>Symbol</th><th>Security</th><th>GICS</th><th>CIK</th><th>Added</th></tr>
<tr><td>GOOGL</td><td>Alphabet Inc. (Class A)</td><td>Technology</td>
    <td>1652044</td><td>2014-04-03</td></tr>
<tr><td>GOOG</td><td>Alphabet Inc. (Class C)</td><td>Technology</td>
    <td>1652044</td><td>2006-04-03</td></tr>
<tr><td>BRK.B</td><td>Berkshire Hathaway</td><td>Financials</td>
    <td>1067983</td><td>2010-02-16</td></tr>
</table>
"""


def test_dual_class_pairs_collapse_to_one_company():
    """GOOG and GOOGL are one filer with one set of Section 16 filings.
    Deduplicating on ticker would run Alphabet twice and publish the same
    chief executive under two rows."""
    members = parse_members(ROWS)
    assert len(members) == 2
    assert {m.cik for m in members} == {1652044, 1067983}


def test_class_tickers_use_edgars_dash():
    """EDGAR and the price feeds both write BRK-B; only Wikipedia uses a
    dot, and getting it wrong misses every dual-class filer."""
    members = parse_members(ROWS)
    assert any(m.ticker == "BRK-B" for m in members)


def test_the_cik_is_found_by_shape_not_by_position():
    """A reordered table should lose rows loudly rather than mismatch them
    silently."""
    reordered = ROWS.replace(
        "<td>1652044</td><td>2014-04-03</td>",
        "<td>2014-04-03</td><td>1652044</td>")
    assert any(m.cik == 1652044 for m in parse_members(reordered))


def test_the_sec_ticker_file_becomes_a_universe():
    """The S&P 500 list is scraped from a third party and is licensed IP.
    The SEC's own ticker file is public domain and covers the whole
    exchange-listed market -- which is where a founder still owning forty
    per cent of their company actually lives."""
    from fle.universe import parse_all_tickers

    raw = ('{"0":{"cik_str":789019,"ticker":"MSFT","title":"MICROSOFT CORP"},'
           '"1":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."},'
           '"2":{"cik_str":1652044,"ticker":"GOOGL","title":"Alphabet Inc."},'
           '"3":{"cik_str":1652044,"ticker":"GOOG","title":"Alphabet Inc."}}')
    members = parse_all_tickers(raw)
    assert len(members) == 3                       # Alphabet counted once
    assert {m.ticker for m in members} == {"MSFT", "AAPL", "GOOGL"}
    assert all(m.cik and m.company for m in members)


def test_a_broken_ticker_file_yields_nothing_rather_than_garbage():
    from fle.universe import parse_all_tickers
    assert parse_all_tickers("not json") == []
    assert parse_all_tickers('{"0":{"ticker":"X"}}') == []      # no CIK
