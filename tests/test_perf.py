"""The performance dataset: raw monthly closes, honestly gathered."""
import json

from fle.perf import Perf, build_perf, fetch_monthly, write_perf


class _Feed:
    """A price feed that answers like polygon's monthly aggregates."""

    def __init__(self, bars):
        self.bars = bars          # ticker -> list of (epoch_ms, close)

    def get(self, url, use_cache=True):
        for tk, rows in self.bars.items():
            if f"/ticker/{tk}/" in url:
                return json.dumps({"results": [
                    {"t": ms, "c": c} for ms, c in rows]})
        raise KeyError(url)


JAN, FEB, MAR = 1704067200000, 1706745600000, 1709251200000   # 2024 months


def test_monthly_closes_come_back_as_year_month_pairs():
    feed = _Feed({"SPY": [(JAN, 470.0), (FEB, 490.0)]})
    got = fetch_monthly(feed, "SPY", "k")
    assert got == [("2024-01", 470.0), ("2024-02", 490.0)]


def test_share_class_tickers_are_spelled_polygons_way():
    feed = _Feed({"BRK.B": [(JAN, 350.0)]})
    assert fetch_monthly(feed, "BRK-B", "k") == [("2024-01", 350.0)]


def test_a_ticker_the_feed_lacks_is_reported_not_fatal():
    feed = _Feed({"SPY": [(JAN, 470.0)], "TSLA": [(JAN, 200.0)]})
    perf = build_perf(feed, ["TSLA", "GHOST"], "k")
    assert "TSLA" in perf.series and "SPY" in perf.series
    assert perf.missing == ["GHOST"]
    assert perf.ok and not perf.note


def test_a_missing_benchmark_is_named_loudly():
    feed = _Feed({"TSLA": [(JAN, 200.0)]})
    perf = build_perf(feed, ["TSLA"], "k")
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


def test_months_beyond_the_rolling_window_are_preserved():
    from fle.perf import merge_history
    stored = {"TSLA": [("2021-01", 100.0), ("2021-02", 110.0),
                       ("2021-03", 120.0)]}
    fresh = {"TSLA": [("2021-03", 120.0), ("2021-04", 130.0)]}
    got = merge_history(stored, fresh)
    assert got["TSLA"] == [("2021-01", 100.0), ("2021-02", 110.0),
                           ("2021-03", 120.0), ("2021-04", 130.0)]


def test_a_restated_series_rescales_the_preserved_tail():
    """A 2-for-1 split halves every adjusted close in the new fetch; the
    preserved months must move to the same basis or the seam is a cliff."""
    from fle.perf import merge_history
    stored = {"TSLA": [("2021-01", 100.0), ("2021-02", 110.0),
                       ("2021-03", 120.0)]}
    fresh = {"TSLA": [("2021-03", 60.0), ("2021-04", 65.0)]}
    got = merge_history(stored, fresh)
    assert got["TSLA"] == [("2021-01", 50.0), ("2021-02", 55.0),
                           ("2021-03", 60.0), ("2021-04", 65.0)]


def test_yesterdays_cohort_members_leave_with_it():
    from fle.perf import merge_history
    stored = {"GONE": [("2021-01", 10.0)], "TSLA": [("2021-01", 100.0)]}
    fresh = {"TSLA": [("2021-01", 100.0)]}
    assert "GONE" not in merge_history(stored, fresh)


def test_a_renamed_ticker_gets_its_old_symbols_years():
    feed = _Feed({"XYZ": [(MAR, 90.0)],
                  "SQ": [(JAN, 80.0), (FEB, 85.0), (MAR, 999.0)],
                  "SPY": [(JAN, 470.0)]})
    perf = build_perf(feed, ["XYZ"], "k")
    # SQ's months before XYZ begins are prepended; its overlap month is not
    assert perf.series["XYZ"] == [("2024-01", 80.0), ("2024-02", 85.0),
                                  ("2024-03", 90.0)]
