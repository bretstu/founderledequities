"""One daily price series per ticker, kept in a folder of small files.

The company page draws a price line with the chief executive's trades on
it, and the performance section draws month-end closes chained into an
index. Both are prices; they now come from ONE store, and the monthly
fetcher that used to serve the performance chart alone is gone.

WHY DAILY. Polygon returns up to 50,000 bars per request, so five years of
days is one call per ticker, the same as five years of months. The nightly
grouped-daily request the site already makes for the stake values returns
every ticker's close for the day; appended here it keeps the store current
at no extra cost. Monthly needed a per-ticker request every week for the
same result.

WHY A FOLDER, NOT ONE FILE. Two thousand tickers by 1,260 days is five
million rows. Nothing reads all of them at once except the weekly refresh;
the company page reads one ticker, and the site build copies one file per
ticker into place. The file is `<TICKER>.csv` with `date,close`, adjusted
for splits as the feed adjusts them.

THE PLAN'S WINDOW ROLLS; THE RECORD MUST NOT. A five-year plan answers
today-minus-five-years, so each refresh would drop the oldest days off the
back. Days the new fetch no longer covers are preserved from the stored
file, rescaled to the new basis where a split has restated the overlap
(see merge).

A SPLIT IS RE-ASKED, NEVER INFERRED. The nightly close after a 5-for-1
split is a fifth of yesterday's; the stored history is on the old basis.
The append reports any day-over-day move outside a wide band, and the
caller refetches that ticker's whole series from the feed. Re-asking the
source is cheap and cannot be wrong the way a computed ratio can.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import os

# LIMIT COUNTS BASE AGGREGATES; the maximum is the only honest value.
DAILY = ("https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/"
         "{start}/{end}?adjusted=true&sort=asc&limit=50000&apiKey={key}")

DEFAULT_START = "2016-01-01"     # ask for ten years; the plan decides how many come back

# THE ENTITY'S SYMBOL HISTORY. Polygon answers aggregates by symbol, and a
# symbol is a name, not a company: before 9 June 2022 "META" was an ETF at
# $15, Meta Platforms traded as FB, and a series fetched by symbol carried
# the ETF's years, a hole at the handover, and Zuckerberg's $300 sales
# floating above a $15 line. Gold.com was AMRK until December 2025 and
# "GOLD" before that was Barrick. The ticker-events feed lists, per
# entity, every symbol it has traded under and the date each began.
EVENTS = ("https://api.polygon.io/vX/reference/tickers/{ticker}/events"
          "?types=ticker_change&apiKey={key}")
EVENTS_MAX_AGE = 7 * 24 * 3600   # a symbol change is rare; the list ages like a feed


def polygon_ticker(t: str) -> str:
    # the panel writes BRK-B; polygon writes BRK.B
    return t.upper().replace("-", ".")


def fetch_daily(client, ticker: str, api_key: str,
                start: str = DEFAULT_START, end: str | None = None) -> list:
    """Adjusted daily closes as (YYYY-MM-DD, close), oldest first. A ticker
    the feed lacks returns [] and is reported by the caller, never fatal."""
    end = end or dt.date.today().isoformat()
    url = DAILY.format(ticker=polygon_ticker(ticker), start=start, end=end,
                       key=api_key)
    try:
        data = json.loads(client.get(url, use_cache=False))
    except Exception:  # noqa: BLE001
        return []
    out = []
    for bar in data.get("results") or []:
        close, ts = bar.get("c"), bar.get("t")
        if close is None or ts is None:
            continue
        day = dt.datetime.fromtimestamp(ts / 1000, dt.timezone.utc).strftime("%Y-%m-%d")
        out.append((day, float(close)))
    return out


def symbol_spans(client, ticker: str, api_key: str) -> list:
    """[(symbol, from_date, to_date_or_None)], oldest first: the symbols this
    ticker's entity has traded under and when. [] when the feed has no
    events for it (the caller falls back to the symbol as given)."""
    url = EVENTS.format(ticker=polygon_ticker(ticker), key=api_key)
    try:
        data = json.loads(client.get(url, max_age=EVENTS_MAX_AGE))
    except Exception:  # noqa: BLE001
        return []
    events = sorted(((e.get("date") or "", (e.get("ticker_change") or {}).get("ticker") or "")
                     for e in (data.get("results") or {}).get("events") or []
                     if e.get("type") == "ticker_change"), key=lambda x: x[0])
    events = [(d, t) for d, t in events if d and t]
    spans = []
    for i, (d, t) in enumerate(events):
        nxt = events[i + 1][0] if i + 1 < len(events) else None
        to = (dt.date.fromisoformat(nxt) - dt.timedelta(days=1)).isoformat() if nxt else None
        spans.append((t, d, to))
    return spans


def fetch_history(client, ticker: str, api_key: str,
                  start: str = DEFAULT_START, end: str | None = None) -> tuple:
    """The ENTITY's adjusted daily closes, oldest first, stitched across
    every symbol it has traded under in the window (symbol_spans), and a
    note when the seams look wrong.

    Meta: FB from 2012-05-18, META from 2022-06-09; asked for 2016 on,
    FB is fetched to 2022-06-08 and META from 2022-06-09. Callaway: ELY,
    MODG, CALY. An entity whose events begin after `start` (Core Natural
    Resources lists only its 2025 change to CNR) has no history before its
    first known symbol, and none is fetched: a stranger's prices under
    the same symbol are worse than a shorter line. An entity with no
    events at all is fetched by its symbol as before.

    Each span comes split-adjusted by the feed for that symbol. A split
    after a symbol change would not be applied to the older symbol's
    span, so adjacent spans are compared where they meet and a jump is
    reported in the note rather than corrected: nothing here computes a
    ratio and applies it.
    -> (points, note)
    """
    end = end or dt.date.today().isoformat()
    spans = symbol_spans(client, ticker, api_key)
    if not spans:
        return fetch_daily(client, ticker, api_key, start, end), ""
    out, note, prev_close = [], "", None
    for symbol, frm, to in spans:
        lo = max(frm, start)
        hi = min(to or end, end)
        if lo > hi:
            continue
        pts = fetch_daily(client, symbol, api_key, lo, hi)
        if pts and prev_close is not None:
            ratio = pts[0][1] / prev_close if prev_close else 1.0
            if ratio > 1.5 or ratio < 0.67:
                note = (f"{ticker}: the line jumps {ratio:.2f}x at the {symbol} seam on "
                        f"{pts[0][0]}; a split may not be applied to the earlier symbol")
        if pts:
            prev_close = pts[-1][1]
        out.extend(pts)
    seen, dedup = set(), []
    for day, close in out:
        if day in seen:
            continue
        seen.add(day)
        dedup.append((day, close))
    dedup.sort()
    return dedup, note


def merge(stored: list, fresh: list) -> list:
    """Keep every day ever fetched; trust the newest fetch where they meet.

    RESTATEMENTS RESCALE THE TAIL. After a split every close in the new
    fetch shifts by the split factor; the preserved days before its window
    would keep the old basis and put a cliff at the seam. The ratio at the
    earliest shared day is applied to every preserved day before it.
    """
    if not stored or not fresh:
        return list(fresh or stored or [])
    fresh_by = dict(fresh)
    keep = [(d, c) for d, c in stored if d < fresh[0][0]]
    overlap = next(((d, c) for d, c in stored if d in fresh_by), None)
    if keep and overlap and overlap[1]:
        ratio = fresh_by[overlap[0]] / overlap[1]
        if abs(ratio - 1.0) > 1e-9:
            keep = [(d, c * ratio) for d, c in keep]
    return keep + list(fresh)


# A close that is less than half or more than double the previous one is
# either a split the store has not been told about or news; either way the
# ticker is re-asked in full. Wide enough that ordinary crashes pass.
SUSPECT_RATIO = 2.0


def append_day(series: list, day: str, close: float) -> bool:
    """Add (or replace) one day's close in place. Returns True when the move
    from the previous stored day is suspect and the series should be
    refetched rather than trusted."""
    if series and series[-1][0] == day:
        series[-1] = (day, close)
        return False
    if series and series[-1][0] > day:
        # an older day arriving late: put it in order
        i = next((k for k, (d, _) in enumerate(series) if d >= day), len(series))
        if i < len(series) and series[i][0] == day:
            series[i] = (day, close)
        else:
            series.insert(i, (day, close))
        return False
    prev = series[-1][1] if series else None
    series.append((day, close))
    if prev and close > 0:
        r = close / prev
        return r > SUSPECT_RATIO or r < 1 / SUSPECT_RATIO
    return False


def month_ends(series: list) -> list:
    """The last close of each calendar month as (YYYY-MM, close)."""
    out, cur = [], None
    for d, c in series:
        m = d[:7]
        if cur and cur[0] == m:
            cur = (m, c)
        else:
            if cur:
                out.append(cur)
            cur = (m, c)
    if cur:
        out.append(cur)
    return out


# ------------------------------------------------------------ the folder

def _path(folder: str, ticker: str) -> str:
    return os.path.join(folder, f"{ticker.upper()}.csv")


def read_one(folder: str, ticker: str) -> list:
    try:
        with open(_path(folder, ticker), encoding="utf-8", newline="") as fh:
            rd = csv.reader(fh)
            next(rd, None)
            return [(d, float(c)) for d, c in rd if d]
    except (OSError, ValueError):
        return []


def read_store(folder: str) -> dict:
    """Every ticker in the folder -> its series. Weekly-refresh scale only."""
    out = {}
    if not os.path.isdir(folder):
        return out
    for name in os.listdir(folder):
        if name.endswith(".csv"):
            tk = name[:-4]
            pts = read_one(folder, tk)
            if pts:
                out[tk] = pts
    return out


def write_one(folder: str, ticker: str, series: list) -> None:
    os.makedirs(folder, exist_ok=True)
    final = _path(folder, ticker)
    tmp = f"{final}.{os.getpid()}.tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "close"])
        for d, c in series:
            w.writerow([d, f"{c:.4f}"])
    os.replace(tmp, final)


def write_store(folder: str, series_by_ticker: dict) -> int:
    n = 0
    for tk, pts in series_by_ticker.items():
        if pts:
            write_one(folder, tk, pts)
            n += 1
    return n
