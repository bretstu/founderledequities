"""The nightly must ask EDGAR what is new.

Production ran five nights after the universe promotion without fetching a
single new filing: the submissions feeds were served from a cache with no
clock and the panel resumed a finished checkpoint. Two rules stop that.
"""
import json
import os
import time
import types

import pytest

from fle import edgar
from fle.cli import fresh_checkpoint


class _Resp:
    def __init__(self, text, status=200):
        self.text, self.status_code, self.headers = text, status, {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def _client(tmp_path, bodies):
    """A client whose session returns `bodies` in order, then fails."""
    c = edgar.EdgarClient(user_agent="t t@t", cache_dir=str(tmp_path))
    calls = []

    def get(url, timeout=30):
        calls.append(url)
        if not bodies:
            raise ConnectionError("down")
        b = bodies.pop(0)
        return _Resp(b) if not isinstance(b, int) else _Resp("", b)
    c._session = types.SimpleNamespace(get=get)
    c._limiter = types.SimpleNamespace(wait=lambda: None, clear=lambda: None,
                                       trip=lambda ra: 0.0, exhausted=False)
    return c, calls


def test_filings_cache_forever_but_a_feed_ages(tmp_path):
    c, calls = _client(tmp_path, ["v1", "v2"])
    url = "https://data.sec.gov/submissions/CIK0000000001.json"
    assert c.get(url) == "v1"
    # no max_age: the cache is the document, however old
    old = time.time() - 10 * 86400
    os.utime(c._cache_path(url), (old, old))
    assert c.get(url) == "v1" and len(calls) == 1
    # a max_age: ten days old is refetched
    assert c.get(url, max_age=3600) == "v2" and len(calls) == 2
    # and the refetched copy is fresh again
    assert c.get(url, max_age=3600) == "v2" and len(calls) == 2


def test_a_failed_refetch_serves_stale_and_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(edgar.time, "sleep", lambda s: None)
    c, calls = _client(tmp_path, ["v1"])
    url = "https://data.sec.gov/submissions/CIK0000000002.json"
    assert c.get(url) == "v1"
    old = time.time() - 86400
    os.utime(c._cache_path(url), (old, old))
    assert c.get(url, max_age=3600) == "v1", "stale beats dead"
    assert c.stale_served == 1, "and it is counted"
    # with nothing cached at all, a failure is still a failure
    with pytest.raises(RuntimeError):
        c.get("https://data.sec.gov/submissions/CIK0000000003.json", max_age=3600)


def test_submissions_uses_the_age_rule(tmp_path):
    feed = json.dumps({"filings": {"recent": {"accessionNumber": ["a"],
                                              "form": ["4"],
                                              "filingDate": ["2026-09-01"]},
                                   "files": []}})
    feed2 = feed.replace('"a"', '"b"')
    c, calls = _client(tmp_path, [feed, feed2])
    assert c.submissions(1)["_filings"][0]["accessionNumber"] == "a"
    old = time.time() - edgar.SUBMISSIONS_MAX_AGE - 60
    os.utime(c._cache_path("https://data.sec.gov/submissions/CIK0000000001.json"), (old, old))
    assert c.submissions(1)["_filings"][0]["accessionNumber"] == "b", \
        "a feed older than SUBMISSIONS_MAX_AGE is refetched"
    assert edgar.SUBMISSIONS_MAX_AGE <= 24 * 3600, "at most a day: the nightly must see yesterday"


def test_the_refresh_starts_from_a_clean_checkpoint(tmp_path):
    ck = tmp_path / "panel.jsonl"
    assert fresh_checkpoint(str(ck)) is False
    ck.write_text('{"cik": 1}\n')
    assert fresh_checkpoint(str(ck)) is True and not ck.exists()


# ---------------------------------------------------------------- the gate

def _panel(path, rows):
    import csv as _csv
    with open(path, "w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=["ticker", "shares", "shares_as_of"])
        w.writeheader()
        w.writerows(rows)


def test_the_gate_tells_a_filing_from_a_rule_change(tmp_path):
    from fle.cli import anchor_moves, ANCHORS
    tsla = ANCHORS["TSLA"]
    before = tmp_path / "before.csv"
    after = tmp_path / "after.csv"
    # the person filed: a newer filing states a new figure -> explained
    _panel(before, [dict(ticker="TSLA", shares=tsla, shares_as_of="2026-06-17")])
    _panel(after, [dict(ticker="TSLA", shares=tsla + 1000, shares_as_of="2026-09-02")])
    assert anchor_moves(str(before), str(after)) == {"TSLA": "explained"}
    # the same filing, a different figure -> the rules moved -> unexplained
    _panel(after, [dict(ticker="TSLA", shares=tsla + 1000, shares_as_of="2026-06-17")])
    assert anchor_moves(str(before), str(after)) == {"TSLA": "unexplained"}
    # the night after an explained move: unchanged from last night -> carried
    _panel(before, [dict(ticker="TSLA", shares=tsla + 1000, shares_as_of="2026-09-02")])
    _panel(after, [dict(ticker="TSLA", shares=tsla + 1000, shares_as_of="2026-09-02")])
    assert anchor_moves(str(before), str(after)) == {"TSLA": "carried"}
    # a figure that matches its constant is not a move at all
    _panel(after, [dict(ticker="TSLA", shares=tsla, shares_as_of="2026-09-02")])
    assert anchor_moves(str(before), str(after)) == {}
    # no baseline at all (first run) and a figure off its constant -> unexplained
    _panel(after, [dict(ticker="META", shares=1, shares_as_of="2026-09-02")])
    assert anchor_moves(str(tmp_path / "missing.csv"), str(after)) == {"META": "unexplained"}


def test_weekly_copies_keep_their_date(tmp_path):
    """copyfile stamped the weekly file with tonight's date; published, it
    read as one day old again tomorrow, and the weekly re-read never came."""
    import shutil
    src = tmp_path / "founders.csv"; src.write_text("ticker,founder\n")
    old = time.time() - 6 * 86400
    os.utime(src, (old, old))
    dst = tmp_path / "staged.csv"
    shutil.copy2(src, dst)
    assert abs(os.path.getmtime(dst) - old) < 2, "the date travels with the file"
    import inspect
    from fle import cli
    assert "copy2(fpath" in inspect.getsource(cli.cmd_refresh) and \
           "copyfile(fpath" not in inspect.getsource(cli.cmd_refresh)


def test_polygon_days_are_never_cached(tmp_path):
    """A day asked for before its close comes back empty; cached, it stayed
    empty forever and the site priced Sep 2 at the Aug 28 close."""
    import inspect
    from fle import prices
    src = inspect.getsource(prices.fetch_prices)
    assert "use_cache=False" in src
    assert edgar.SUBMISSIONS_MAX_AGE <= 4 * 3600, \
        "a run by hand in the evening must not blind the 02:30 nightly"
