"""A COMPANY THAT WAS ACQUIRED LEAVES THE SITE (fle/delisted.py, 2026-09-17):
Crinetics (Vertex, 1 Sep) and AtaiBeckley (Lilly, 11 Sep) read 0.00% at high
confidence after their founders' final Form 4s; the issuer's Form 25 or 15
after that filing is the structured signal."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fle.delisted import delisting, read, record, path_for  # noqa: E402
from fle.universe import read_universe  # noqa: E402


class _C:
    def __init__(self, filings):
        self.filings = filings

    def submissions(self, cik):
        return {"_filings": self.filings}


def test_a_delisting_form_after_the_persons_newest_filing_is_the_signal():
    crnx = _C([{"form": "8-K", "filingDate": "2026-09-02"}, {"form": "25-NSE", "filingDate": "2026-09-03"}, {"form": "15-12B", "filingDate": "2026-09-15"}])
    assert delisting(crnx, 1658247, after="2026-09-01") == ("25-NSE", "2026-09-03"), "the earliest delisting form on or after the last Form 4"
    assert delisting(crnx, 1658247, after="2026-09-16") is None, "nothing after the person's newest filing: still listed"
    old = _C([{"form": "15-15D", "filingDate": "2014-03-01"}])   # a subsidiary's notes deregistered years ago
    assert delisting(old, 1, after="2026-09-01") is None
    assert delisting(_C([]), 1, after="") is None


def test_the_file_is_appended_once_and_the_universe_drops_the_tickers(tmp_path):
    (tmp_path / "universe").mkdir()
    u = tmp_path / "universe" / "universe-2026-08-31.csv"
    u.write_text("cik,ticker,company,added\n1658247,CRNX,Crinetics,\n2081043,ATAI,AtaiBeckley,\n1318605,TSLA,Tesla,\n")
    p = path_for(str(u))
    assert p.endswith(os.path.join("universe", "delisted.csv"))
    rows = [{"ticker": "CRNX", "cik": "1658247", "company": "Crinetics", "ceo": "R. Scott Struthers", "form": "25-NSE", "date": "2026-09-03", "noted": "2026-09-17"}]
    assert record(p, rows) == 1 and record(p, rows) == 0, "written once"
    assert set(read(p)) == {"CRNX"}
    assert [m.ticker for m in read_universe(str(u))] == ["ATAI", "TSLA"], "the delisted company is not a member"
    record(p, [{"ticker": "ATAI", "cik": "2081043", "company": "AtaiBeckley", "ceo": "Srinivas Rao", "form": "15-12B", "date": "2026-09-16", "noted": "2026-09-17"}])
    assert [m.ticker for m in read_universe(str(u))] == ["TSLA"]


def test_the_panel_drops_a_delisted_row_on_publish():
    import inspect
    import fle.cli as C
    src = inspect.getsource(C.cmd_panel)
    assert 'r.get("delisted")' in src and "left the panel" in src and "write_csv(rows, args.out)" in src.split("left the panel")[1]
