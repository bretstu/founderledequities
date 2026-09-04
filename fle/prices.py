"""The closing price of every US stock, from one request.

The dashboard shows the VALUE of a chief executive's stake, and a value is
shares times a price. Shares come from the filings; the price has to come
from a market data feed, and it is the one number on the site that is not
computed from SEC documents -- so it carries its own date, and rows without
a price show a dash rather than an estimate.

Polygon's grouped-daily endpoint returns the close for the ENTIRE US equity
market in a single response. Five hundred per-ticker requests collapse into
one, which matters on a rate-limited key.

TICKER SPELLING. The panel writes share classes with a dash -- BF-B, BRK-B --
because that is how index constituent lists write them. Polygon writes them
with a dot: BF.B. The dash-to-dot translation is done here, once, rather
than taught to every consumer.

THE MOST RECENT TRADING DAY IS NOT TODAY. Markets close on weekends and
holidays, and the grouped endpoint returns an empty result for such dates.
So the fetch walks backwards from the requested date until a day with data
appears, up to a week -- enough to cross any exchange holiday cluster.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

GROUPED = ("https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/"
           "{date}?adjusted=true&apiKey={key}")


@dataclass
class Prices:
    by_ticker: dict = field(default_factory=dict)   # panel ticker -> close
    all_closes: dict = field(default_factory=dict)  # every symbol the day returned
    as_of: str = ""
    matched: int = 0
    missing: list = field(default_factory=list)
    note: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.by_ticker)


def fetch_prices(client, tickers, api_key: str | None,
                 date: str | None = None) -> Prices:
    """The close for each panel ticker, dated to the trading day used."""
    out = Prices()
    if not api_key:
        out.note = "no POLYGON_API_KEY configured"
        return out

    when = dt.date.fromisoformat(date) if date else dt.date.today()
    rows = []
    for _ in range(8):
        try:
            # NEVER FROM THE CACHE. Asked for a day before its close, Polygon
            # answers with no results, and a cached empty answer was that
            # day's answer forever: the walk stepped back past every day
            # first asked for too early and priced a Sep 2 site at the Aug
            # 28 close. One request per attempt, a handful a night.
            data = client.get_json(GROUPED.format(date=when.isoformat(),
                                                  key=api_key),
                                   use_cache=False)
        except Exception as e:  # noqa: BLE001
            out.note = (f"grouped-daily request failed: {e}; the endpoint "
                        "needs a Polygon plan with aggregate access")
            return out
        rows = data.get("results") or []
        if rows:
            break
        when -= dt.timedelta(days=1)     # weekend or holiday: step back
    if not rows:
        out.note = "no trading day with data in the last week"
        return out

    # Polygon spells share classes with a dot; the panel with a dash.
    close = {}
    for r in rows:
        t = (r.get("T") or "").upper()
        c = r.get("c")
        if t and isinstance(c, (int, float)) and c > 0:
            close[t] = float(c)

    out.as_of = when.isoformat()
    out.all_closes = close
    for t in tickers:
        got = close.get(t.upper()) or close.get(t.upper().replace("-", "."))
        if got is not None:
            out.by_ticker[t] = got
            out.matched += 1
        else:
            out.missing.append(t)
    return out
