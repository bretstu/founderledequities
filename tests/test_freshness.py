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
from fle.cli import rotate_checkpoint


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


def test_a_finished_checkpoint_becomes_the_prior_and_an_unfinished_one_resumes(tmp_path):
    """Resumed as-is, a finished checkpoint asks EDGAR nothing. Moved aside
    as the prior, it is what lets the panel carry unchanged companies. A
    checkpoint short of the universe is a night that died, and stays."""
    uni = tmp_path / "u.csv"
    uni.write_text("cik,ticker,company,added\n1,A,A Co,\n2,B,B Co,\n")
    ck, prior = tmp_path / "panel.jsonl", tmp_path / "panel-prior.jsonl"
    assert rotate_checkpoint(str(ck), str(prior), str(uni)) is False
    ck.write_text('{"cik": 1}\n')
    assert rotate_checkpoint(str(ck), str(prior), str(uni)) is False and ck.exists(), \
        "one of two members: unfinished, left to resume"
    ck.write_text('{"cik": 1}\n{"cik": 2}\n')
    assert rotate_checkpoint(str(ck), str(prior), str(uni)) is True
    assert prior.exists() and not ck.exists()


# ---------------------------------------------------------------- the prior

class _Feeds:
    """A client whose submissions feeds are dictated by the test."""
    def __init__(self, feeds):
        self.feeds, self.asked = feeds, []

    def submissions(self, cik):
        self.asked.append(cik)
        return {"_filings": self.feeds.get(cik, [])}


def _f(form, date, acc):
    return {"form": form, "filingDate": date, "accessionNumber": acc}


def test_a_company_with_nothing_new_keeps_its_row(tmp_path, monkeypatch):
    """The whole point of the universe nightly: two small feed requests per
    company, and a recompute only for the ones that filed something that
    could move the row."""
    import fle.panel as P
    from fle.universe import Member
    built = []
    def _build(client, cik, company="", ticker="", exclusions=None, on_progress=None):
        built.append(cik)
        from fle.ownership import Ownership
        return Ownership(cik=cik, company=company)
    monkeypatch.setattr(P, "build", _build)
    feeds = {1: [_f("4", "2026-08-01", "0001-26-1"), _f("8-K", "2026-09-02", "0001-26-9")],
             2: [_f("4", "2026-08-01", "0002-26-1")],
             77: [_f("4", "2026-07-01", "0077-26-1")]}
    client = _Feeds(feeds)
    prior = {1: {"cik": 1, "ticker": "A", "owner_cik": "77", "settled": True,
                 "fingerprint": "2026-08-01 0001-26-1 | 2026-07-01 0077-26-1", "remarks": "", "addition_key": "", "opening_source": "", "pct": 5.0},
             2: {"cik": 2, "ticker": "B", "owner_cik": "", "settled": True,
                 "fingerprint": "2026-08-01 0002-26-1", "remarks": "", "addition_key": "", "opening_source": "", "pct": 1.0}}
    ck = tmp_path / "p.jsonl"
    rows = P.run_panel(client, [Member(1, "A", "A Co"), Member(2, "B", "B Co")],
                       str(ck), prior=prior)
    assert built == [], "an 8-K is not a filing that moves a row"
    assert [r["pct"] for r in rows] == [5.0, 1.0], "both rows carried, fingerprints and all"
    assert set(client.asked) == {1, 77, 2}, "the issuer feeds and the one known owner feed were read"

    # a new Form 4 on the issuer's feed forces a recompute, and the new row
    # carries the new fingerprint
    feeds[2].append(_f("4", "2026-09-02", "0002-26-5"))
    ck.unlink()
    rows = P.run_panel(client, [Member(2, "B", "B Co")], str(ck), prior=prior)
    assert built == [2]
    assert rows[0]["fingerprint"] == "2026-09-02 0002-26-5"

    # a new 10-Q moves the denominator: recompute
    feeds[1].append(_f("10-Q", "2026-09-02", "0001-26-7"))
    ck.unlink()
    P.run_panel(client, [Member(1, "A", "A Co")], str(ck), prior=prior)
    assert built == [2, 1]

    # an error row or an unsettled row is never carried
    ck.unlink()
    P.run_panel(client, [Member(2, "B", "B Co")], str(ck),
                prior={2: {"cik": 2, "settled": False, "fingerprint": "x"}})
    assert built == [2, 1, 2]


def test_the_fingerprint_forms_are_the_ones_that_move_a_row():
    from fle.panel import FINGERPRINT_FORMS
    for f in ("4", "4/A", "10-Q", "10-K", "20-F", "SC 13G/A"):
        assert f in FINGERPRINT_FORMS
    for f in ("8-K", "424B2", "DEF 14A"):
        assert f not in FINGERPRINT_FORMS


# ---------------------------------------------------------------- the gate

def _panel(path, rows):
    import csv as _csv
    with open(path, "w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=["ticker", "shares", "shares_as_of"])
        w.writeheader()
        w.writerows(rows)


def test_the_history_reuse_key_moves_on_a_cover_page():
    """A 10-Q adds a point to a company's series with no Form 4 from the
    person (history.add_cover_points). Keyed on Section 16 alone, that
    company would be carried, stale, until the person next filed."""
    import inspect
    from fle import cli
    src = inspect.getsource(cli.cmd_history)
    assert "key_forms = SECTION16 + COVER_FORMS" in src
    assert 'if f.get("form") in key_forms:' in src
    assert 'if f.get("form") in SECTION16:' not in src


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
    assert "copy2(fpath" in inspect.getsource(cli._refresh) and \
           "copyfile(fpath" not in inspect.getsource(cli._refresh)


def test_polygon_days_are_never_cached(tmp_path):
    """A day asked for before its close comes back empty; cached, it stayed
    empty forever and the site priced Sep 2 at the Aug 28 close."""
    import inspect
    from fle import prices
    src = inspect.getsource(prices.fetch_prices)
    assert "use_cache=False" in src
    assert edgar.SUBMISSIONS_MAX_AGE <= 4 * 3600, \
        "a run by hand in the evening must not blind the 02:30 nightly"


# ---------------------------------------------------------------- the S&P list

def _m(cik, tk):
    from fle.universe import Member
    return Member(cik, tk, tk + " Co")


def test_the_sp_list_is_accepted_only_when_it_looks_like_the_index():
    from fle.universe import sp_list_acceptable
    current = [_m(i, f"T{i}") for i in range(1, 504)]
    # an ordinary quarter: two swapped
    fresh = [m for m in current if m.cik not in (1, 2)] + [_m(901, "NEW1"), _m(902, "NEW2")]
    ok, why, adds, drops = sp_list_acceptable(fresh, current)
    assert ok and adds == ["NEW1", "NEW2"] and drops == ["T1", "T2"]
    # a broken page: 480 rows
    ok, why, _, _ = sp_list_acceptable(current[:480], current)
    assert not ok and "480 members" in why
    # a vandalised page: the right size, the wrong companies
    fresh = current[:490] + [_m(900 + i, f"X{i}") for i in range(13)]
    ok, why, adds, drops = sp_list_acceptable(fresh, current)
    assert not ok and "not an index change" in why
    # the first list ever: no current to compare against, size alone decides
    ok, _, _, _ = sp_list_acceptable(current, [])
    assert ok


def test_the_newest_sp_list_is_found_by_its_date(tmp_path):
    from fle.universe import newest_sp_list
    assert newest_sp_list(str(tmp_path)) is None
    (tmp_path / "sp500-2026-08-25.csv").write_text("cik,ticker,company,added\n")
    (tmp_path / "sp500-2026-09-09.csv").write_text("cik,ticker,company,added\n")
    (tmp_path / "sp500-notadate.csv").write_text("")
    path, when = newest_sp_list(str(tmp_path))
    assert path.endswith("sp500-2026-09-09.csv") and when.isoformat() == "2026-09-09"


# ---------------------------------------------------------------- every company

def test_the_gate_asks_every_company_whether_a_filing_explains_its_move(tmp_path):
    from fle.cli import unexplained_moves
    before, after = tmp_path / "b.csv", tmp_path / "a.csv"
    _panel(before, [dict(ticker="A", shares=100, shares_as_of="2026-08-01"),
                    dict(ticker="B", shares=100, shares_as_of="2026-08-01"),
                    dict(ticker="C", shares=100, shares_as_of="2026-08-01")])
    _panel(after, [dict(ticker="A", shares=100, shares_as_of="2026-08-01"),   # carried
                   dict(ticker="B", shares=120, shares_as_of="2026-09-02"),   # filed: explained
                   dict(ticker="C", shares=120, shares_as_of="2026-08-01"),   # moved, no filing
                   dict(ticker="D", shares=5, shares_as_of="2026-09-02")])    # new member
    assert unexplained_moves(str(before), str(after)) == ["C"]


def test_the_resnapshot_is_quarterly_with_a_weeks_notice():
    from fle.cli import resnapshot_due
    assert resnapshot_due(30, {}) == ""
    assert resnapshot_due(83, {}) == "warn" and resnapshot_due(89, {}) == "warn"
    assert resnapshot_due(90, {}) == "take"
    assert resnapshot_due(120, {"FLE_UNIVERSE_RESNAPSHOT": "0"}) == "hold"


# ---------------------------------------------------------------- the heartbeat

def _capture(monkeypatch):
    import urllib.request
    calls = []
    def fake_open(req, timeout=10):
        calls.append((req.full_url, req.data.decode("utf-8")))
        class R: pass
        return R()
    monkeypatch.setattr(urllib.request, "urlopen", fake_open)
    monkeypatch.setenv("FLE_HEARTBEAT_URL", "https://hc-ping.com/uuid")
    return calls


def test_every_way_the_nightly_ends_is_reported(tmp_path, monkeypatch):
    """The switch used to hear success and one kind of failure; a panel
    that failed, a gate that refused, or an exception died silent."""
    from fle import cli
    import argparse
    calls = _capture(monkeypatch)
    (tmp_path / "refresh.log").write_text("[x] earlier line\n")
    args = argparse.Namespace(dir=str(tmp_path))

    monkeypatch.setattr(cli, "_refresh", lambda a, log: (log("published"), 0)[1])
    assert cli.cmd_refresh(args) == 0
    assert [u.rsplit("/", 1)[1] for u, _ in calls] == ["start", "0"]
    assert "published" in calls[-1][1], "the log tail rides with the ping"

    calls.clear()
    monkeypatch.setattr(cli, "_refresh", lambda a, log: (log("REFUSING TO PUBLISH -- gate"), 2)[1])
    assert cli.cmd_refresh(args) == 2
    assert [u.rsplit("/", 1)[1] for u, _ in calls] == ["start", "2"]
    assert "REFUSING" in calls[-1][1]

    calls.clear()
    def boom(a, log):
        raise RuntimeError("panel died")
    monkeypatch.setattr(cli, "_refresh", boom)
    import pytest as _pt
    with _pt.raises(RuntimeError):
        cli.cmd_refresh(args)
    assert [u.rsplit("/", 1)[1] for u, _ in calls] == ["start", "1"]
    assert "panel died" in calls[-1][1]


def test_no_url_means_no_ping_and_never_an_error(tmp_path, monkeypatch):
    from fle import cli
    monkeypatch.delenv("FLE_HEARTBEAT_URL", raising=False)
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("pinged")))
    cli._heartbeat(lambda m: None, 0, "x")   # silent, no call
    monkeypatch.setenv("FLE_HEARTBEAT_URL", "https://hc-ping.com/uuid")
    said = []
    cli._heartbeat(said.append, 0, "x")      # the fake raises; the run must not
    assert said and "heartbeat failed" in said[0]


def test_the_breaker_gives_up_after_an_hour_of_rest_even_with_successes_between(monkeypatch):
    """The 2026-09-14 run: EDGAR's maintenance window answered some
    requests and refused others; a give-up counter that reset on every
    success never fired, and the run rested four hours until systemd
    killed it. The budget of rest is per run and a success does not
    refund it."""
    from fle.edgar import RateLimiter
    import time as _t
    lim = RateLimiter()
    clock = [1000.0]
    monkeypatch.setattr(_t, "monotonic", lambda: clock[0])
    rested = 0.0
    for _ in range(6):
        q = lim.trip()          # refused
        rested += q
        clock[0] += q + 1       # the nap ends
        lim.clear()             # a request got through
        assert not lim.exhausted or rested > 3600
    assert rested > 3600 and lim.exhausted, "an hour of rest in total is the run's whole budget"
