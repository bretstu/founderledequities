"""The trailing edge is the one place a reader could be misled silently."""
import csv

from fle.cli import edge_confidence


def _write(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def _panel(tmp_path, rows):
    p = str(tmp_path / "sp500.csv")
    _write(p, ["ticker", "pct", "confidence", "cautions"], rows)
    return p


def _hist(tmp_path, rows):
    p = str(tmp_path / "history.csv")
    _write(p, ["ticker", "date", "shares", "unexplained"], rows)
    return p


def _read(p):
    return {r["ticker"]: r for r in csv.DictReader(open(p, encoding="utf-8-sig"))}


def test_an_unreconciled_newest_filing_caps_confidence(tmp_path):
    panel = _panel(tmp_path, [
        {"ticker": "AAA", "pct": "2.0", "confidence": "high", "cautions": ""},
        {"ticker": "BBB", "pct": "5.0", "confidence": "high", "cautions": ""},
    ])
    hist = _hist(tmp_path, [
        # AAA: a crater as the LAST row -- 2.7m held, 2.66m unexplained away
        {"ticker": "AAA", "date": "2024-01-01", "shares": "2700000",
         "unexplained": ""},
        {"ticker": "AAA", "date": "2024-02-01", "shares": "40000",
         "unexplained": "-2660000"},
        # BBB: reconciled throughout
        {"ticker": "BBB", "date": "2024-02-01", "shares": "900000",
         "unexplained": ""},
    ])
    assert edge_confidence(panel, hist) == 1
    got = _read(panel)
    assert got["AAA"]["confidence"] == "medium"
    assert "partial" in got["AAA"]["cautions"]
    assert got["BBB"]["confidence"] == "high"
    assert got["BBB"]["cautions"] == ""


def test_a_cover_page_after_the_crater_does_not_clear_the_cap(tmp_path):
    """history.add_cover_points writes a 10-Q row after the person's last
    filing, with no residue by construction. The cap judges the person's
    last FILING: read the last row instead and it would never fire again
    once a quarter had passed."""
    panel = _panel(tmp_path, [
        {"ticker": "AAA", "pct": "2.0", "confidence": "high", "cautions": ""}])
    hist = str(tmp_path / "history.csv")
    _write(hist, ["ticker", "date", "form", "shares", "unexplained"], [
        {"ticker": "AAA", "date": "2024-01-01", "form": "4", "shares": "2700000", "unexplained": ""},
        {"ticker": "AAA", "date": "2024-02-01", "form": "4", "shares": "40000", "unexplained": "-2660000"},
        {"ticker": "AAA", "date": "2024-03-31", "form": "10-Q", "shares": "40000", "unexplained": ""},
    ])
    assert edge_confidence(panel, hist) == 1
    assert _read(panel)["AAA"]["confidence"] == "medium"


def test_a_crater_that_is_not_the_newest_filing_is_left_alone(tmp_path):
    """Mid-record craters are already handled -- marked, and excluded from
    every summary. Only the trailing edge lacks a successor to settle it."""
    panel = _panel(tmp_path, [
        {"ticker": "AAA", "pct": "2.0", "confidence": "high", "cautions": ""}])
    hist = _hist(tmp_path, [
        {"ticker": "AAA", "date": "2024-01-01", "shares": "2700000",
         "unexplained": ""},
        {"ticker": "AAA", "date": "2024-02-01", "shares": "40000",
         "unexplained": "-2660000"},
        {"ticker": "AAA", "date": "2024-03-01", "shares": "2720000",
         "unexplained": "2680000"},
    ])
    assert edge_confidence(panel, hist) == 0
    assert _read(panel)["AAA"]["confidence"] == "high"


def test_an_unreconciled_RISE_does_not_cap(tmp_path):
    """An unexplained increase overstates nothing the reader is asked to
    trust, and usually reads as the award it is."""
    panel = _panel(tmp_path, [
        {"ticker": "AAA", "pct": "2.0", "confidence": "high", "cautions": ""}])
    hist = _hist(tmp_path, [
        {"ticker": "AAA", "date": "2024-01-01", "shares": "100000",
         "unexplained": ""},
        {"ticker": "AAA", "date": "2024-02-01", "shares": "2700000",
         "unexplained": "2600000"},
    ])
    assert edge_confidence(panel, hist) == 0
    assert _read(panel)["AAA"]["confidence"] == "high"


def test_it_never_raises_confidence(tmp_path):
    panel = _panel(tmp_path, [
        {"ticker": "AAA", "pct": "2.0", "confidence": "low",
         "cautions": "something else"}])
    hist = _hist(tmp_path, [
        {"ticker": "AAA", "date": "2024-01-01", "shares": "2700000",
         "unexplained": ""},
        {"ticker": "AAA", "date": "2024-02-01", "shares": "40000",
         "unexplained": "-2660000"},
    ])
    assert edge_confidence(panel, hist) == 1
    got = _read(panel)["AAA"]
    assert got["confidence"] == "low"
    assert got["cautions"].startswith("something else|")


def test_missing_files_are_survivable(tmp_path):
    assert edge_confidence(str(tmp_path / "nope.csv"),
                           str(tmp_path / "also-nope.csv")) == 0


def test_a_block_rests_every_worker_and_probes_once(tmp_path, monkeypatch):
    """A 429 trips a SHARED breaker: the quiet period applies to all
    threads, one request tests the door afterwards, a refusal doubles the
    rest, and a success resets the escalation."""
    import fle.edgar as E
    naps = []
    clock = [1000.0]
    monkeypatch.setattr(E.time, "sleep", lambda s: (naps.append(s), clock.__setitem__(0, clock[0] + s)))
    monkeypatch.setattr(E.time, "monotonic", lambda: clock[0])

    class Resp:
        def __init__(self, code, body="ok"):
            self.status_code, self.text, self.headers = code, body, {}
        def raise_for_status(self): pass

    class Sess:
        def __init__(self, refusals): self.calls, self.refusals = 0, refusals
        def get(self, url, timeout=30):
            self.calls += 1
            return Resp(429) if self.calls <= self.refusals else Resp(200, "body")
    c = E.EdgarClient(cache_dir=str(tmp_path))
    c._session = Sess(refusals=2)
    c._limiter._min_interval = 0
    assert c.get("https://www.sec.gov/x", use_cache=False) == "body"
    # two refusals -> rests of 10 min then 20 min, then success clears
    assert sum(naps) >= 660 + 1320 and c._session.calls == 3
    assert c._limiter._consecutive == 0
    # a second worker arriving mid-rest joins the same nap (trip returns 0)
    c._limiter.trip(); assert c._limiter.trip() == 0.0


def test_a_fetch_starved_certification_search_refuses_to_conclude():
    """The eight false 'no certification' rows: every fetch failed inside
    SEC's block and each was swallowed. Now the search errors instead."""
    import pytest
    from fle.identity import peo_from_certification

    class Blocked:
        def submissions(self, cik):
            return {"_filings": [{"form": "10-Q", "accessionNumber": "a-1",
                                  "filingDate": "2026-08-07"}]}
        def filing_index(self, cik, acc):
            raise RuntimeError("429 for https://www.sec.gov/...")
    with pytest.raises(RuntimeError, match="refusing to conclude"):
        peo_from_certification(Blocked(), 1520006)


def test_a_partial_submissions_index_raises_instead_of_truncating(tmp_path, monkeypatch):
    """Ally and AGNC file 424B2s daily; their 10-Ks live in EDGAR's history
    files. When those failed inside a throttle, the index silently lost
    every periodic filing and the CEO was recorded as certless."""
    import json
    import pytest
    import fle.edgar as E
    c = E.EdgarClient(cache_dir=str(tmp_path))
    main = {"filings": {"recent": {"form": ["424B2"], "accessionNumber": ["a"],
                                   "filingDate": ["2026-08-01"]},
                        "files": [{"name": "CIK0000040729-submissions-001.json"}]}}
    def fake_get_json(url, use_cache=True, max_age=None):
        if url.endswith("submissions-001.json"):
            raise RuntimeError("429 for " + url)
        return json.loads(json.dumps(main))
    monkeypatch.setattr(c, "get_json", fake_get_json)
    with pytest.raises(RuntimeError, match="partial"):
        c.submissions(40729)


def test_a_search_that_opened_no_documents_refuses_to_conclude():
    """Wrapper-only index listings whose page fallback yielded nothing:
    eight 'filings with no documents' in a row became 'no certification'.
    Zero documents opened is a broken index, not an absent certification."""
    import pytest
    from fle.identity import peo_from_certification

    class WrappersOnly:
        def submissions(self, cik):
            return {"_filings": [{"form": "10-K",
                                  "accessionNumber": f"0001234567-26-00000{i}",
                                  "filingDate": f"2026-0{i+1}-01",
                                  "primaryDocument": ""} for i in range(3)]}
        def filing_index(self, cik, acc):
            # only the submission wrapper: the shape a throttled page
            # fallback leaves behind
            return {"directory": {"item": [{"name": f"{acc}.txt", "size": "1"}]}}
    with pytest.raises(RuntimeError, match="opened 0 documents"):
        peo_from_certification(WrappersOnly(), 1)
