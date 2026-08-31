"""Monthly closes for the founder-led cohort and the benchmark.

The site's other sections say WHAT the founders own; the performance chart
says why anyone should care. It needs one small dataset: an adjusted
monthly close for each founder-led company and for SPY, as far back as the
price feed will give us.

WHY MONTHLY. A decade at daily resolution is half a megabyte of numbers
that render identically to the monthly line at chart size. Monthly keeps
perf.csv small enough to sit on the free tier and load instantly, and it
is the honest resolution for a comparison measured in years.

WHY SPY AND NOT "THE S&P 500". Index values themselves are licensed data;
the ETF's price history is just a stock price from the same feed as every
other price on the site, and it tracks the index to within basis points.
The chart says "via SPY" and means it.

THE INDEX ITSELF IS NOT COMPUTED HERE. This module publishes the raw
monthly closes; the equal-weight chaining lives in the page, next to the
chart it draws, where a reader who views source can check the method
against the note that describes it. It also means a custom-index builder
later needs no new data -- the matrix is already in the browser.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field

# LIMIT COUNTS THE DAYS UNDERNEATH, NOT THE MONTHS RETURNED. Polygon builds
# month bars from base (daily) aggregates and `limit` caps how many base
# aggregates are scanned -- limit=200 quietly truncated a decade request to
# ~200 trading days: ten months, the last of them built from four days of
# May. The maximum is the only honest value here.
MONTHLY = ("https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/month/"
           "{start}/{end}?adjusted=true&sort=asc&limit=50000&apiKey={key}")


@dataclass
class Perf:
    # ticker -> list of (YYYY-MM, close)
    series: dict = field(default_factory=dict)
    start: str = ""
    end: str = ""
    missing: list = field(default_factory=list)
    note: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.series)


def _polygon_ticker(t: str) -> str:
    # the panel writes BRK-B; polygon writes BRK.B -- same rule as prices.py
    return t.upper().replace("-", ".")


def fetch_monthly(client, ticker: str, api_key: str,
                  start: str = "2016-01-01", end: str | None = None) -> list:
    """Adjusted monthly closes as (YYYY-MM, close), oldest first.

    The feed returns one bar per month with `c` the adjusted close and `t`
    the bar's start in epoch milliseconds. History depth depends on the
    plan; whatever comes back is what gets published, and the chart starts
    where the data does rather than pretending.
    """
    end = end or dt.date.today().isoformat()
    url = MONTHLY.format(ticker=_polygon_ticker(ticker), start=start,
                         end=end, key=api_key)
    try:
        body = client.get(url, use_cache=False)
        data = json.loads(body)
    except Exception:  # noqa: BLE001 - a ticker the feed lacks is reported, not fatal
        return []
    out = []
    for bar in data.get("results") or []:
        close = bar.get("c")
        ts = bar.get("t")
        if close is None or ts is None:
            continue
        month = dt.datetime.fromtimestamp(ts / 1000, dt.timezone.utc).strftime("%Y-%m")
        out.append((month, float(close)))
    return out


# A COMPANY OUTLIVES ITS TICKER. Block traded as SQ until January 2025 and
# the feed keeps the old years under the old symbol only -- fetched as XYZ,
# four of its five years vanish. Renames are rare enough to name by hand.
FORMER_TICKER = {"XYZ": "SQ"}


def merge_history(stored: dict, fresh: dict) -> dict:
    """Keep every month ever fetched; trust the newest fetch where they meet.

    THE PLAN'S WINDOW ROLLS; THE RECORD MUST NOT. A five-year price plan
    returns today-minus-five-years, so each refresh would silently drop the
    oldest month off the back of the chart -- history already in hand,
    eroding weekly. Months the new fetch no longer covers are preserved
    from the stored file.

    RESTATEMENTS RESCALE THE TAIL. Adjusted closes are rewritten after a
    split: every month in the new fetch shifts by the split factor, but the
    preserved months before its window would keep the old basis -- putting
    a fake cliff at the seam. Where stored and fresh overlap, the ratio at
    the earliest shared month is applied to every preserved month before
    it, so the whole series stays on one basis.

    Tickers present only in the stored file are dropped: the file describes
    today's cohort, and yesterday's members leave with it.
    """
    out = {}
    for tk, new in fresh.items():
        old = stored.get(tk)
        if not old or not new:
            out[tk] = list(new)
            continue
        new_months = {m for m, _ in new}
        keep = [(m, c) for m, c in old if m < new[0][0]]
        overlap = next(((m, c) for m, c in old if m in new_months), None)
        if keep and overlap:
            fresh_at = dict(new)[overlap[0]]
            ratio = fresh_at / overlap[1] if overlap[1] else 1.0
            if abs(ratio - 1.0) > 1e-9:
                keep = [(m, c * ratio) for m, c in keep]
        out[tk] = keep + list(new)
    return out


def build_perf(client, founder_tickers, api_key: str,
               benchmark: str = "SPY", start: str = "2016-01-01",
               on_step=None) -> Perf:
    perf = Perf(start=start)
    todo = [benchmark] + sorted(set(t.upper() for t in founder_tickers))
    for i, tk in enumerate(todo, 1):
        if on_step:
            on_step(i, len(todo), tk)
        series = fetch_monthly(client, tk, api_key, start=start)
        former = FORMER_TICKER.get(tk)
        if former:
            before = fetch_monthly(client, former, api_key, start=start)
            cut = series[0][0] if series else "9999-99"
            series = [p for p in before if p[0] < cut] + series
        if series:
            perf.series[tk] = series
            perf.end = max(perf.end, series[-1][0])
        else:
            perf.missing.append(tk)
    if benchmark not in perf.series:
        perf.note = f"benchmark {benchmark} returned no data; chart cannot draw"
    return perf


def write_perf(perf: Perf, path: str) -> int:
    import csv
    rows = 0
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "month", "close"])
        for tk in sorted(perf.series):
            for month, close in perf.series[tk]:
                w.writerow([tk, month, f"{close:.4f}"])
                rows += 1
    return rows
