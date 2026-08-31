"""Restating historical share counts in today's shares.

A split is not a transaction. No Form 4 reports one; the balance simply
multiplies, so a figure filed in 2010 and a figure filed in 2026 are in
different units. Musk's Tesla Form 3 records about 28 million shares against
a holding of 1.12 billion, and Tesla split 5-for-1 in 2020 and 3-for-1 in
2022 -- fifteen times.

Left alone this does not merely blur the flow columns, it BIASES them, and in
the worst possible direction: a founder who bought early has their purchases
shrunk fifteenfold while an executive granted stock last year is counted at
face value. The column would understate exactly the people the product is
about.

    adjusted = reported x (product of every split factor since that date)

THE FACTORS COME FROM A SPLITS FEED, not from the filings. Inferring a ratio
from a balance that jumped means a missed filing and a split look identical,
and the whole point of this module is to stop guessing. Massive publishes
execution_date, split_from and split_to per ticker; a 5-for-1 is
split_from=1, split_to=5, so a share held before it becomes five.

AND THE ANSWER CHECKS ITSELF. After adjustment the flows must reconcile:

    opening + acquired - disposed  ==  what they hold now

A row that reconciles has had every split applied correctly. One that does
not is still flagged, and its columns still must not be summed. So this is
not trusted because the feed is authoritative -- it is trusted because the
arithmetic closes.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Split:
    date: str                      # execution date, YYYY-MM-DD
    factor: float                  # shares held before become this many


@dataclass
class Splits:
    ticker: str = ""
    events: list = field(default_factory=list)
    note: str = ""

    def factor_since(self, date: str) -> float:
        """How many of today's shares one share on `date` has become.

        A transaction ON the execution date is already in post-split shares,
        so only splits strictly after it apply.
        """
        f = 1.0
        for s in self.events:
            if date and s.date > date:
                f *= s.factor
        return f

    def adjust(self, shares: float, date: str) -> float:
        return shares * self.factor_since(date)

    @property
    def ok(self) -> bool:
        return not self.note

    def describe(self) -> str:
        if not self.events:
            return "no splits"
        return "|".join(f"{s.date}:{s.factor:g}x" for s in
                        sorted(self.events, key=lambda x: x.date))


def fetch_splits(client, ticker: str, api_key: str | None = None) -> Splits:
    """Every split this ticker has had, newest irrelevant, all of them kept."""
    out = Splits(ticker=ticker)
    if not ticker:
        out.note = "no ticker, so no split history"
        return out
    if not api_key:
        out.note = "no POLYGON_API_KEY, so historical amounts are unadjusted"
        return out

    url = (f"https://api.polygon.io/v3/reference/splits?ticker={ticker}"
           f"&limit=1000&apiKey={api_key}")
    try:
        data = client.get_json(url)
    except Exception as exc:  # noqa: BLE001
        out.note = f"could not read splits: {exc}"
        return out

    for row in data.get("results", []) or []:
        when = (row.get("execution_date") or "")[:10]
        frm, to = row.get("split_from"), row.get("split_to")
        try:
            frm, to = float(frm), float(to)
        except (TypeError, ValueError):
            continue
        if not when or frm <= 0 or to <= 0:
            continue
        # A reverse split has split_from > split_to and a factor below one,
        # which the same arithmetic handles: GE's 1-for-8 is 0.125.
        out.events.append(Split(date=when, factor=to / frm))
    out.events.sort(key=lambda s: s.date)
    return out
