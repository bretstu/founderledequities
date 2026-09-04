"""The price record: one daily store, honestly gathered, and the
month-ends the performance chart cuts from it."""
import json

from fle.dailies import (append_day, fetch_daily, merge, month_ends,
                         read_one, read_store, write_one, write_store)
from fle.perf import Perf, apply_floors, build_perf, write_perf


class _Feed:
    """A price feed that answers like polygon's daily aggregates."""

    def __init__(self, bars):
        self.bars = bars          # ticker -> list of (epoch_ms, close)

    def get(self, url, use_cache=True):
        for tk, rows in self.bars.items():
            if f"/ticker/{tk}/" in url:
                return json.dumps({"results": [
                    {"t": ms, "c": c} for ms, c in rows]})
        raise KeyError(url)


D1, D2, D3 = 1704067200000, 1704153600000, 1706745600000   # 2024-01-01, 01-02, 02-01


def test_daily_closes_come_back_dated():
    feed = _Feed({"SPY": [(D1, 470.0), (D2, 471.0)]})
    assert fetch_daily(feed, "SPY", "k") == [("2024-01-01", 470.0), ("2024-01-02", 471.0)]


def test_share_class_tickers_are_spelled_polygons_way():
    feed = _Feed({"BRK.B": [(D1, 350.0)]})
    assert fetch_daily(feed, "BRK-B", "k") == [("2024-01-01", 350.0)]


def test_a_ticker_the_feed_lacks_returns_nothing_not_an_error():
    assert fetch_daily(_Feed({}), "GHOST", "k") == []


def test_days_beyond_the_rolling_window_are_preserved():
    stored = [("2021-01-04", 100.0), ("2021-01-05", 110.0), ("2021-01-06", 120.0)]
    fresh = [("2021-01-06", 120.0), ("2021-01-07", 130.0)]
    assert merge(stored, fresh) == [("2021-01-04", 100.0), ("2021-01-05", 110.0),
                                    ("2021-01-06", 120.0), ("2021-01-07", 130.0)]


def test_a_restated_series_rescales_the_preserved_tail():
    """A 2-for-1 split halves every adjusted close in the new fetch; the
    preserved days must move to the same basis or the seam is a cliff."""
    stored = [("2021-01-04", 100.0), ("2021-01-05", 110.0), ("2021-01-06", 120.0)]
    fresh = [("2021-01-06", 60.0), ("2021-01-07", 65.0)]
    assert merge(stored, fresh) == [("2021-01-04", 50.0), ("2021-01-05", 55.0),
                                    ("2021-01-06", 60.0), ("2021-01-07", 65.0)]


def test_appending_a_day_keeps_order_and_flags_a_split_sized_move():
    s = [("2024-01-01", 100.0)]
    assert append_day(s, "2024-01-02", 101.0) is False
    assert append_day(s, "2024-01-02", 102.0) is False and s[-1] == ("2024-01-02", 102.0)
    assert append_day(s, "2024-01-03", 20.0) is True, "a fifth of yesterday: re-ask the feed"
    assert append_day(s, "2024-01-04", 19.0) is False
    # a late-arriving older day goes in order, and never reads as a split
    assert append_day(s, "2023-12-29", 99.0) is False
    assert [d for d, _ in s] == ["2023-12-29", "2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]


def test_month_ends_take_the_last_close_of_each_month():
    s = [("2024-01-02", 1.0), ("2024-01-31", 2.0), ("2024-02-01", 3.0), ("2024-02-29", 4.0), ("2024-03-01", 5.0)]
    assert month_ends(s) == [("2024-01", 2.0), ("2024-02", 4.0), ("2024-03", 5.0)]


def test_the_store_is_one_file_per_ticker_and_round_trips(tmp_path):
    d = str(tmp_path / "store")
    n = write_store(d, {"TSLA": [("2024-01-02", 200.0)], "SPY": [("2024-01-02", 470.0)], "EMPTY": []})
    assert n == 2
    assert sorted(p.name for p in tmp_path.joinpath("store").iterdir()) == ["SPY.csv", "TSLA.csv"]
    assert open(tmp_path / "store" / "TSLA.csv").read().splitlines() == ["date,close", "2024-01-02,200.0000"]
    assert read_one(d, "tsla") == [("2024-01-02", 200.0)]
    assert read_one(d, "GHOST") == []
    assert set(read_store(d)) == {"TSLA", "SPY"}
    write_one(d, "TSLA", [("2024-01-02", 200.0), ("2024-01-03", 201.0)])
    assert len(read_one(d, "TSLA")) == 2


def test_perf_is_the_stores_month_ends_with_both_benchmarks():
    store = {"SPY": [("2024-01-02", 470.0), ("2024-01-31", 480.0)],
             "RSP": [("2024-01-31", 160.0)],
             "TSLA": [("2024-01-31", 200.0), ("2024-02-01", 190.0)]}
    perf = build_perf(store, ["TSLA", "GHOST"])
    assert perf.series["SPY"] == [("2024-01", 480.0)]
    assert "RSP" in perf.series, "the equal-weight S&P rides along as the second benchmark"
    assert perf.series["TSLA"] == [("2024-01", 200.0), ("2024-02", 190.0)]
    assert perf.missing == ["GHOST"]
    assert perf.ok and not perf.note and perf.start == "2024-01" and perf.end == "2024-02"


def test_a_missing_benchmark_is_named_loudly():
    perf = build_perf({"TSLA": [("2024-01-31", 200.0)]}, ["TSLA"])
    assert "SPY" in perf.note and "cannot draw" in perf.note


def test_the_csv_is_long_form_and_sorted(tmp_path):
    perf = Perf(series={"TSLA": [("2024-01", 200.0), ("2024-02", 190.5)],
                        "SPY": [("2024-01", 470.0)]})
    out = str(tmp_path / "perf.csv")
    assert write_perf(perf, out) == 3
    lines = open(out, encoding="utf-8-sig").read().strip().splitlines()
    assert lines[0] == "ticker,month,close"
    assert lines[1].startswith("SPY,2024-01,470.0")
    assert lines[2] == "TSLA,2024-01,200.0000"


def test_no_price_before_this_security_traded_under_the_symbol():
    """Polygon answers by symbol and symbols are recycled: SPCX carried a
    SPAC's sixty months before SpaceX's three. The vendor's per-security
    list_date is the floor. EDGAR's registration date is NOT: Apollo,
    BlackRock and DraftKings reorganised into new registrants while their
    stock traded on, and a floor drawn there cut real history."""
    from fle.perf import listing_month

    class _Client:
        def get(self, url, **kw):
            assert "reference/tickers/SPCX" in url
            return json.dumps({"results": {"ticker": "SPCX", "list_date": "2026-06-12", "cik": "0001181412"}})
    assert listing_month(_Client(), "SPCX", "k") == "2026-06"
    # the floor cuts daily points and monthly points alike
    series = {"SPCX": [("2021-09-01", 28.74), ("2026-05-29", 29.0), ("2026-06-12", 161.0), ("2026-07-01", 115.0)],
              "TSLA": [("2021-09-01", 250.0), ("2026-07-01", 310.0)]}
    cut = apply_floors(series, {"SPCX": "2026-06"})
    assert [d for d, _ in cut["SPCX"]] == ["2026-06-12", "2026-07-01"], "the SPAC's days are gone"
    assert cut["TSLA"] == series["TSLA"], "a ticker without a floor is untouched"

    class _NoRecord:
        def get(self, url, **kw):
            raise RuntimeError("offline")
    assert listing_month(_NoRecord(), "X", "k") == "", "no record, no floor -- the series is kept, never guessed"


# ------------------------------------------------------------ the stages

def test_the_weekly_refresh_fills_the_store_and_the_nightly_close_extends_it(tmp_path, monkeypatch):
    """perf backfills every panel ticker plus SPY and RSP into one file
    each and cuts perf.csv from them; prices then appends the day's close
    to the same files from the grouped request it already makes, and
    re-asks the feed for a ticker whose close moved like a split."""
    import types
    from fle import cli
    from fle.config import SETTINGS

    class _Client:
        def __init__(self):
            self.daily = {"SPY": [(D1, 470.0), (D2, 471.0)], "RSP": [(D1, 160.0)],
                          "TSLA": [(D1, 200.0), (D2, 202.0)]}
            self.refetched = []
        def get(self, url, use_cache=True):
            if "reference/tickers" in url:
                return json.dumps({"results": {"list_date": "2010-06-29"}})
            for tk, rows in self.daily.items():
                if f"/ticker/{tk}/" in url:
                    if "range/1/day" in url and tk == "TSLA" and self.refetched is not None:
                        self.refetched.append(tk)
                    return json.dumps({"results": [{"t": ms, "c": c} for ms, c in rows]})
            return json.dumps({"results": []})
        def get_json(self, url, use_cache=True):
            # the grouped-daily answer: TSLA at a fifth of yesterday
            return {"results": [{"T": "SPY", "c": 472.0}, {"T": "RSP", "c": 161.0},
                                {"T": "TSLA", "c": 40.0}]}

    client = _Client()
    monkeypatch.setattr(cli, "_client", lambda a: client)
    monkeypatch.setattr(SETTINGS, "polygon_api_key", "k")
    panel = tmp_path / "panel.csv"
    panel.write_text("ticker,cik\nTSLA,1318605\n")
    store = str(tmp_path / "store")
    perf_out = str(tmp_path / "perf.csv")
    rc = cli.cmd_perf(types.SimpleNamespace(panel=str(panel), store=store, out=perf_out,
                                            only=None, user_agent=None))
    assert rc == 0
    assert set(read_store(store)) == {"SPY", "RSP", "TSLA"}
    assert read_one(store, "TSLA") == [("2024-01-01", 200.0), ("2024-01-02", 202.0)]
    perf_rows = open(perf_out, encoding="utf-8-sig").read().splitlines()
    assert "TSLA,2024-01,202.0000" in perf_rows and "SPY,2024-01,471.0000" in perf_rows

    client.refetched = []
    client.daily["TSLA"] = [(D1, 40.0), (D2, 40.4), (D3, 40.0)]   # the feed's restated series
    rc = cli.cmd_prices(types.SimpleNamespace(panel=str(panel), out=str(tmp_path / "prices.csv"),
                                              date="2024-02-01", store=store, user_agent=None))
    assert rc == 0
    assert read_one(store, "SPY")[-1] == ("2024-02-01", 472.0), "the benchmark is appended though it is not in the panel"
    assert client.refetched == ["TSLA"], "a fifth of yesterday is re-asked, not inferred"
    assert read_one(store, "TSLA") == [("2024-01-01", 40.0), ("2024-01-02", 40.4), ("2024-02-01", 40.0)]
