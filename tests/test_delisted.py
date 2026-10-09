"""A COMPANY THAT WAS ACQUIRED LEAVES THE SITE (fle/delisted.py, 2026-09-17):
Crinetics (Vertex, 1 Sep) and AtaiBeckley (Lilly, 11 Sep) read 0.00% at high
confidence after their founders' final Form 4s; the issuer's Form 15 after
that filing raises the question, and (2026-10-09) the vendor's `active` flag
answers it: Bristol Myers, Apollo, ONEOK, Enbridge and four more filed a
Form 15 for a class that was not their stock and left the site for three
weeks on the form alone."""
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


GONE = lambda c, t, k: False      # the vendor: delisted   # noqa: E731
TRADING = lambda c, t, k: True    # the vendor: active      # noqa: E731
UNKNOWN = lambda c, t, k: None    # no key, no record       # noqa: E731


def test_a_delisting_form_after_the_persons_newest_filing_raises_the_question():
    crnx = _C([{"form": "8-K", "filingDate": "2026-09-02"}, {"form": "25-NSE", "filingDate": "2026-09-03"}, {"form": "15-12B", "filingDate": "2026-09-15"}])
    assert delisting(crnx, 1658247, after="2026-09-01", listed=GONE) == ("15-12B", "2026-09-15"), "the Form 15, not the 25: the registration ending is the signal"
    att = _C([{"form": "25-NSE", "filingDate": "2026-09-08"}])   # AT&T: a series of notes leaving the exchange
    assert delisting(att, 732717, after="2026-09-01", listed=GONE) is None, "a Form 25 alone is not the stock leaving (warrants, notes, a preferred)"
    assert delisting(crnx, 1658247, after="2026-09-16", listed=GONE) is None, "nothing after the person's newest filing: still listed"
    old = _C([{"form": "15-15D", "filingDate": "2014-03-01"}])   # a subsidiary's notes deregistered years ago
    assert delisting(old, 1, after="2026-09-01", listed=GONE) is None
    assert delisting(_C([]), 1, after="", listed=GONE) is None


def test_the_vendor_answers_the_question_the_form_raises():
    """Bristol Myers filed a 15-12G on 2026-03-27 and trades every day;
    Crinetics filed one on 2026-09-15 and never traded again."""
    bmy = _C([{"form": "15-12G", "filingDate": "2026-03-27"}, {"form": "10-Q", "filingDate": "2026-07-28"}])
    assert delisting(bmy, 14272, after="2026-03-02", listed=TRADING) is None, "the form was for another class; the stock trades"
    assert delisting(bmy, 14272, after="2026-03-02", listed=UNKNOWN) is None, "no vendor answer: nobody leaves on the form alone"
    crnx = _C([{"form": "15-12B", "filingDate": "2026-09-15"}])
    assert delisting(crnx, 1658247, after="2026-09-01", listed=GONE) == ("15-12B", "2026-09-15")
    asked = []
    def spy(c, t, k):
        asked.append((t, k)); return False
    assert delisting(crnx, 1658247, after="2026-09-01", ticker="CRNX", api_key="k", listed=spy) and asked == [("CRNX", "k")], "the vendor is asked for this ticker with the key"
    assert delisting(_C([{"form": "10-Q", "filingDate": "2026-09-15"}]), 1, after="2026-09-01", listed=spy) is None and len(asked) == 1, "no Form 15: the vendor is not asked"


def test_the_vendor_record_is_read_for_active_and_delisted():
    from fle.delisted import still_listed
    class _V:
        def __init__(self, body): self.body = body
        def get(self, url, use_cache=True): return self.body
    assert still_listed(_V('{"results": {"ticker": "BMY", "active": true}}'), "BMY", "k") is True
    assert still_listed(_V('{"results": {"ticker": "CRNX", "active": false, "delisted_utc": "2026-09-03T00:00:00Z"}}'), "CRNX", "k") is False
    assert still_listed(_V('{"results": {}}'), "X", "k") is None, "no active field: no answer"
    assert still_listed(_V('not json'), "X", "k") is None
    assert still_listed(_V('{}'), "X", None) is None, "no key: no answer"
    assert still_listed(_V('{"results": {"ticker": "BRK.B", "active": true}}'), "BRK-B", "k") is True


def test_the_file_is_appended_once_and_the_universe_drops_the_tickers(tmp_path):
    (tmp_path / "universe").mkdir()
    u = tmp_path / "universe" / "universe-2026-08-31.csv"
    u.write_text("cik,ticker,company,added\n1658247,CRNX,Crinetics,\n2081043,ATAI,AtaiBeckley,\n1318605,TSLA,Tesla,\n")
    p = path_for(str(u))
    assert p.endswith(os.path.join("universe", "delisted.csv"))
    rows = [{"ticker": "CRNX", "cik": "1658247", "company": "Crinetics", "ceo": "R. Scott Struthers", "form": "15-12B", "date": "2026-09-15", "noted": "2026-09-17"}]
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
