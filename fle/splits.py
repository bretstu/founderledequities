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

    doubts: list = field(default_factory=list)   # (date, factor, why): splits the covers do not corroborate; applied anyway

    def corroborate(self, series) -> list:
        """THE COVER PAGES ARE READ AGAINST THE FEED, AND THE FEED STANDS
        (2026-09-15). A first version refused a split when the first cover
        after it was not roughly the last cover before it times the factor.
        Strive proved that rule cannot decide: its 1-for-20 of February 6 is
        real (the 10-Q says so in words), and the covers around it go 16.6M
        to 69.2M because the company issued fifty times its share count in
        the same quarter. A refused real split sends the company straight
        back to the mixed-units error this work exists to end, so nothing is
        refused here: a split the covers do not corroborate is applied and
        named on the panel as a doubt, with both counts and dates, for a
        person to read against the filing. Each cover is dated by the
        instant its count is as of (Point.counted), never the period end.
        Returns the doubts."""
        day = lambda p: getattr(p, "counted", "") or p.as_of  # noqa: E731
        pts = sorted((p for p in getattr(series, "points", []) or [] if day(p) and p.shares), key=day)
        out = []
        for ev in self.events:
            before = [p for p in pts if day(p) < ev.date]
            after = [p for p in pts if day(p) >= ev.date]
            if not before or not after:
                continue
            b, a = before[-1], after[0]
            observed = a.shares / b.shares if b.shares else None
            if observed is not None and not (0.5 <= observed / ev.factor <= 2.0):
                out.append((ev.date, ev.factor, f"the feed says {ev.factor:g}x on {ev.date}; the cover pages go {b.shares:,.0f} "
                                                f"(as of {day(b)}) to {a.shares:,.0f} (as of {day(a)}), {observed:.2f}x: applied, "
                                                f"read the filing"))
        self.doubts = out
        return out

    disowned: list = field(default_factory=list)   # (date, factor, why): events that are not this registrant's

    def disown_before_first_cover(self, series) -> list:
        """A TICKER'S SPLIT HISTORY CAN BELONG TO ANOTHER COMPANY (2026-09-15,
        Hut 8). The feed keys events to a ticker, and a ticker can pass from
        one registrant to another. HUT went from Hut 8 Mining to Hut 8 Corp
        (CIK 1964789, a new company) at the merger of 30 November 2023; the
        feed's "5 -> 1 on 2023-12-04" is the ratio at which the OLD
        registrant's shares were exchanged (0.2, the Hut 8 Exchange Ratio of
        the closing 8-K), recorded on the new ticker's first day the only
        way the feed's schema allows. Genoot's 3,308,850 were Hut 8 Corp
        shares issued to him for USBTC stock on the day the company was
        born; the first cover page, 88,962,964, is the two exchanges added
        and nothing divided. Applying the event published 0.54% for a 2.68%
        stake.

        THE KEY IS THE REGISTRANT'S FIRST COVER PAGE, on the date its count
        is as of (Point.counted). An event dated before it has no count of
        this registrant on its far side: nothing of this company's could
        have split, because as a public company it did not yet exist. A
        first version keyed on the person's first ownership filing and
        missed this very case: Genoot's Form 3 is dated 9 November, when
        the registration went effective, three weeks before the merger and
        the event. Strive, Carvana and every long-standing registrant have
        covers years before their splits and are untouched. Returns the
        events not applied; the panel names them."""
        day = lambda p: getattr(p, "counted", "") or p.as_of  # noqa: E731
        pts = [day(p) for p in getattr(series, "points", []) or [] if day(p) and p.shares]
        if not pts:
            return []
        first = min(pts)
        keep, out = [], []
        for ev in self.events:
            if ev.date < first:
                out.append((ev.date, ev.factor, f"the feed's {ev.factor:g}x on {ev.date} predates this registrant's first cover page "
                                                f"(as of {first}): a predecessor's event on the same ticker, not a split of this stock; "
                                                f"not applied"))
            else:
                keep.append(ev)
        self.events = keep
        self.disowned = out
        return out

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
        # A LIST OF WHAT HAS HAPPENED SO FAR, so it ages (2026-10-09): the
        # cached copy is reread within a day, refetched after. Frozen at the
        # first walk, a split executed later was never seen.
        from .config import SPLITS_MAX_AGE
        data = client.get_json(url, max_age=SPLITS_MAX_AGE)
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
