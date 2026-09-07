"""Month-end closes for the performance chart, cut from the daily store.

The site's other sections say WHAT the founders own; the performance chart
says why anyone should care. It needs one small dataset: an adjusted
month-end close for each company and for the two benchmarks, as far back
as the price record goes.

THE PRICES COME FROM ONE PLACE. This module used to fetch monthly bars for
the cohort, once a week, one request per ticker, and keep its own rolling
history. The daily store (fle.dailies) now holds every ticker's closes and
is kept current by the nightly grouped-daily request; the month-ends here
are cut from it. One fetcher, one basis, one place to look when a price is
wrong.

WHY SPY AND NOT "THE S&P 500". Index values themselves are licensed data;
the ETF's price history is just a stock price from the same feed as every
other price on the site, and it tracks the index to within basis points.
The chart says "via SPY" and means it.

THE INDEX ITSELF IS NOT COMPUTED HERE. This module publishes the raw
monthly closes; the equal-weight chaining lives in the page, next to the
chart it draws, where a reader who views source can check the method
against the note that describes it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .dailies import month_ends, polygon_ticker


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


# (A hand-kept table of former tickers, XYZ was SQ, lived here. The feed's
# ticker events say the same for every entity: dailies.symbol_spans.)

BENCHMARKS = ("SPY", "RSP")   # the S&P 500 cap-weighted, and equal-weighted


def build_perf(store: dict, tickers, benchmark: str = "SPY") -> Perf:
    """Month-end closes for `tickers` and BOTH benchmarks, from the daily
    store. The founders line is equal-weight, so the fair comparison is the
    equal-weight S&P (RSP) beside the cap-weighted one (SPY)."""
    perf = Perf()
    bench = [benchmark] + [b for b in BENCHMARKS if b != benchmark]
    for tk in bench + sorted({t.upper() for t in tickers}):
        pts = store.get(tk) or []
        if pts:
            perf.series[tk] = month_ends(pts)
            perf.end = max(perf.end, perf.series[tk][-1][0])
            perf.start = min(perf.start or "9999-99", perf.series[tk][0][0])
        else:
            perf.missing.append(tk)
    if benchmark not in perf.series:
        perf.note = f"benchmark {benchmark} returned no data; chart cannot draw"
    return perf


REFERENCE = "https://api.polygon.io/v3/reference/tickers/{ticker}?apiKey={key}"


def listing_month(client, ticker: str, api_key: str) -> str:
    """The month THIS security began trading under the symbol, from the
    vendor's own ticker record (`list_date`).

    WHY THE PRICE HISTORY NEEDS IT. Polygon answers by symbol, and symbols
    are recycled. Asked for SPCX it returned sixty months of a SPAC that
    carried the ticker until 2026, stitched onto three months of SpaceX,
    and the chart called that a 545% three-year return. FIG was Fortress
    before it was Figma.

    WHY NOT THE EDGAR REGISTRATION DATE. It dates the registrant, not the
    security. Apollo (2022), BlackRock (2024) and DraftKings (2020) each
    reorganised into a new registrant while the stock traded on without
    a break; their first Section 16 filing is years after their price
    history begins, and a floor drawn there cut real months. The vendor's
    ticker record is per security: a recycled symbol gets a new record
    with a new list_date, a reorganised company keeps its old one.

    Cached like every other document; the record does not change."""
    url = REFERENCE.format(ticker=polygon_ticker(ticker), key=api_key)
    try:
        body = client.get(url)
        data = json.loads(body)
        ld = ((data.get("results") or {}).get("list_date") or "")[:7]
        return ld if len(ld) == 7 else ""
    except Exception:  # noqa: BLE001 -- no record, no floor; the caller keeps the series
        return ""


def apply_floors(series: dict, floors: dict) -> dict:
    """Drop every point before a ticker's listing month. `floors` maps
    TICKER -> "YYYY-MM"; points are keyed by YYYY-MM or YYYY-MM-DD, and a
    string compare against the month works for both. Tickers without a
    floor are left alone."""
    out = {}
    for tk, pts in series.items():
        fl = floors.get(tk.upper())
        out[tk] = [p for p in pts if p[0] >= fl] if fl else list(pts)
    return out


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
