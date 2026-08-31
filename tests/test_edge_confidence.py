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


def test_a_throttled_client_waits_and_then_succeeds(tmp_path, monkeypatch):
    """429 gets minute-scale patience (Retry-After honored), not 2-second
    knocks -- and the block does not consume the retry budget."""
    import fle.edgar as E
    naps = []
    monkeypatch.setattr(E.time, "sleep", lambda s: naps.append(s))

    class Resp:
        def __init__(self, code, body="ok"):
            self.status_code, self.text, self.headers = code, body, {"Retry-After": "90"}
        def raise_for_status(self): pass

    class Sess:
        def __init__(self): self.calls = 0
        def get(self, url, timeout=30):
            self.calls += 1
            return Resp(429) if self.calls <= 2 else Resp(200, "the body")
    c = E.EdgarClient(cache_dir=str(tmp_path))
    c._session = Sess()
    c._limiter._min_interval = 0
    assert c.get("https://www.sec.gov/x", use_cache=False) == "the body"
    assert len(naps) == 2 and all(n >= 90 for n in naps)


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
