"""What a chief executive actually bought and sold, one row per trade.

WHY THIS IS NOT THE HISTORY FEED. The activity feed on the dashboard derives
its events from consecutive history snapshots -- it subtracts one day's total
from the last and calls the difference a trade. That is why an `unexplained`
column had to exist: a split, a restatement, or a vehicle appearing in one
filing and not the next all move the total without anyone trading. Here the
transaction rows ARE the source. The filer said "I sold 2,900 shares at
185.46", and that is what gets reported. The whole class of artifact goes away.

WHAT COUNTS AS A TRADE. Only P and S. An award (A), an option exercise (M),
shares withheld for tax (F), a gift (G) and a conversion (C) are not somebody
going to the market. Verified against Deere: John May exercised 16,468 options
at $100.55 and sold 16,468 at $163.21 the same day, and his balance went
44,082 -> 60,550 -> 44,082. Counting the M as a purchase would invent a
$1.66m buy that never happened.

ONE TRADE IS MANY ROWS. Olivier Pomel's 10 November 2021 sale is 23 rows at
23 weighted-average prices, because that is how a broker fills a large order.
Pemble's is 29 rows for a single 5,000-share disposal. Emitting a row per
line would make one sale look like twenty-nine, so rows are folded into one
event per (accession, code, transaction date). Not per accession alone:
CoStar's April 2018 filing reports sales on the 26th, 27th and 30th, and
collapsing those into one event would date two of them wrongly.

WHERE THE HOLDING COMES FROM, AND WHY NOT FROM THE ROW. The obvious thing --
take `sharesOwnedFollowingTransaction` from the last row -- is wrong, and
quietly so. Balances on Form 4 are per vehicle. Pomel's last row is a sale
inside a GRAT that ends at 865 shares; his actual position is 244,043 direct
plus that 865. Reading the last row would report that he sold 99.6% of his
stake on a day he sold none of it. Benioff's 2005 filing is worse: the last
row says 360,000, while two holding rows in the same document report 770,147
in an annuity trust and 25,724,520 in a revocable trust -- a position seventy
times larger than the number a row balance would give.

So every vehicle is carried, holding rows included, and the total is the sum
across all of them. Walking oldest-first means a vehicle mentioned once keeps
its balance until the filer mentions it again, which is the same rule the
ledger uses for the panel.

GROSS SOLD AND NET CHANGE ARE DIFFERENT NUMBERS. Deere sold $2.69m and the
position did not move. Pomel sold $39.4m and the position genuinely fell by
206,223, because his conversion took Class B out of Table II while the sale
took Class A out of Table I. From Table I alone the two look identical. Both
figures are reported, because the difference between them is the story: one
is compensation being cashed, the other is a stake being reduced.

PRICES ARE AS FILED, NEVER ADJUSTED. Value is split-invariant -- Jassy's 100
pre-split Amazon shares at $3,000 and 2,000 post-split shares at $150 are the
same $300,000 -- so shares and price are taken together off the same row and
never mixed with a split-adjusted count. Adjusting one without the other
inflates value by the split factor and produces a number that looks entirely
plausible.

BAD PRICES ARE FLAGGED, NOT FIXED. Two in 68,889 rows. Benioff's 2008 filing
reports a price of $682,827 on a $63 stock; a 2025 Carvana filing reports
$30.23 on one row and $300.23 on another for the same security the same day.
Both are the filer's error, faithfully reproduced. A flag says so and the
filed number still shows, because a figure a reader cannot trace back to the
document is worth less than a wrong one they can.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .ledger import (SECTION16, Line, _doc_url, _parse, _rows,
                     displace_amended)

# A market trade, and nothing else. See the module docstring.
TRADE_CODES = ("P", "S")

# The transaction codes that sit alongside a sale without being one. Reported
# so a reader can tell a stake being reduced from pay being cashed.
COMPANY_CODES = ("A", "M", "F", "C", "G")


def plan_state(root) -> str:
    """-> "plan" | "discretionary" | "unknown".

    `aff10b5One` is the Rule 10b5-1 checkbox, and it appears in four spellings
    across EDGAR: 1, 0, true, false. An earlier count that matched only [01]
    silently dropped 621 filings and produced the false result that no CEO
    purchase had ever been made under a plan; the real figure is 1 in 21.

    The checkbox did not exist before 1 April 2023, so absence is not a "no".
    Garmin 2007, Benioff 2005, Deere 2019 and Datadog 2021 all carry footnotes
    saying in plain English that the sale was made under a 10b5-1 plan, and
    all four have no checkbox at all. Calling those discretionary would
    manufacture seven years of signal out of a field that did not exist.
    """
    raw = (root.findtext(".//aff10b5One") or "").strip().lower()
    if raw in ("1", "true"):
        return "plan"
    if raw in ("0", "false"):
        return "discretionary"
    return "unknown"


@dataclass
class Event:
    """One chief executive, one code, one day."""
    ticker: str = ""
    issuer_cik: int = 0
    ceo: str = ""
    owner_cik: str = ""
    accession: str = ""
    form: str = ""
    filed: str = ""                    # when it became public
    traded: str = ""                   # when the trade happened
    code: str = ""
    buy: bool = False
    shares: float = 0.0                # gross shares this code moved
    value: float | None = None         # sum of shares x price, as filed
    avg_price: float | None = None
    rows: int = 0                      # lines folded into this event
    unpriced_rows: int = 0
    securities: str = ""
    direct: str = ""
    plan: str = "unknown"
    holding_after: float | None = None  # the day's total, raw, from history
    net_change: float | None = None     # split-adjusted day-over-day, from history
    residue: float | None = None        # history's `unexplained` for the day
    other_codes: str = ""              # A/M/F/C/G in the same filing
    price_flag: str = ""
    url: str = ""

    @property
    def label(self) -> str:
        """What actually happened, in the words a reader needs.

        `plan/CM` is not a sentence. And the two questions a reader has are
        independent: was this their decision (the checkbox), and did their
        stake move (net_change). John May's exercise-and-sell is a real
        $20.8m sale AND a position that did not move; dropping either fact
        misleads. Before April 2023 the checkbox did not exist, so a sale
        from then is neither scheduled nor discretionary -- it is unknown,
        and says so.
        """
        if self.buy:
            return ("scheduled purchase" if self.plan == "plan"
                    else "open-market purchase")
        if self.stake_unchanged and not self.residue:
            # The claim "position unchanged" is only made when history could
            # account for the whole day. A day carrying unexplained residue
            # gets the plain label and the residue flag instead.
            return "exercise and sell"
        return {"plan": "scheduled sale",
                "discretionary": "discretionary sale"}.get(self.plan, "sale")

    @property
    def stake_unchanged(self) -> bool:
        """Shares changed hands and the position did not.

        Rounding tolerance, not exact zero: a filing can settle fractional
        shares. Anything under one share is not a change in a stake.
        """
        return self.net_change is not None and abs(self.net_change) < 1.0

    @property
    def pct_of_holding(self) -> float | None:
        """Gross shares against the position before the trade.

        The number that keeps the feed from being a list of mega-caps: a chief
        executive selling 12% of what they own says more than one selling a
        larger dollar amount that is a rounding error to them.
        """
        if self.holding_after is None or self.stake_unchanged or self.residue:
            # 28.43% is what John May's January 2026 sale computes to, and it
            # is arithmetically right and communicatively false: he exercised
            # and sold the same 41,472 shares and owned exactly what he owned
            # before. A percentage of a stake that did not move is not a
            # number to print.
            return None
        # The position BEFORE the trade, rebuilt from the day's close: a sale
        # had the shares, a purchase did not. It can legitimately be zero --
        # a chief executive who sells out entirely closes at zero, and one
        # who buys their first shares opened at zero -- and a percentage of
        # nothing is not a number. Guarding only on `holding_after` missed
        # both, and 500 companies found what eight samples did not.
        before = self.holding_after + (self.shares if not self.buy
                                       else -self.shares)
        if before <= 0:
            return None
        return 100.0 * self.shares / before


def load_history(path: str) -> dict:
    """history.csv as {cik: [(date, raw_shares, adj_shares, unexplained)]}.

    The position column of the feed. Events used to compute holdings with a
    walk of its own, rediscovering -- badly, three patches running -- what
    history's walk already knows: balance chaining for vehicles that share a
    name, a bench for vehicles omitted and restated, replace-on-transaction
    and merge-on-holdings. The fix was never to finish a second state
    machine. It was to stop having one.
    """
    import csv
    out: dict = {}
    with open(path, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            try:
                cik = int(r.get("cik") or 0)
                row = ((r.get("date") or ""),
                       float(r.get("shares") or 0),
                       float(r.get("shares_split_adjusted") or r.get("shares") or 0),
                       float(r.get("unexplained") or 0))
            except ValueError:
                continue
            out.setdefault(cik, []).append(row)
    for v in out.values():
        v.sort()
    return out


def _position(hist_rows: list, day: str):
    """-> (holding_after_raw, net_change_adj, residue) for one trading day.

    net_change is the difference of SPLIT-ADJUSTED totals between this day's
    snapshot and the previous one, so a split between two filings never reads
    as a trade. holding_after is the day's RAW total -- the same units the
    filed trade is in, which is what a percent-of-stake needs.

    A day history has no snapshot for gets the forward-filled holding and
    residue None -- not the residue of whatever snapshot sits nearest. 366
    events inherited a neighbour's reconciliation that way, which suppressed
    their percentage and asserted a problem on a day nothing was known about.
    Absence of evidence is its own answer, and it is not zero either.

    residue is history's `unexplained` for the day: the amount the total
    moved that the day's transactions do not account for. Adam Foroughi's
    June 2026 filings are the standing example -- several same-day Form 4s,
    a trust reported in one, omitted in the next, restated at a different
    balance in the third. History cannot attribute that cleanly and says so;
    an event on such a day inherits the flag instead of asserting a net.
    """
    if not hist_rows:
        return None, None, None
    idx = None
    for i, (d, _r, _a, _u) in enumerate(hist_rows):
        if d == day:
            idx = i
            break
        if d > day:
            idx = i - 1
            break
    else:
        idx = len(hist_rows) - 1
    if idx is None or idx < 0:
        return None, None, None
    d, raw, adj, resid = hist_rows[idx]
    exact = (d == day)
    if idx == 0:
        return raw, None, (resid if exact else None)
    return raw, adj - hist_rows[idx - 1][2], (resid if exact else None)


def build_events(client, issuer_cik: int, owner_cik: str, ticker: str = "",
                 ceo: str = "", since: str = "", max_filings: int | None = None,
                 history: dict | None = None, exclude=()) -> list[Event]:
    """Every P/S event for one chief executive, oldest first.

    Trade detail -- code, shares, price, value, the plan checkbox -- comes
    from the filing rows, where it has been verified to the cent against
    history's independent arithmetic (traded_value for AppLovin, 10 June
    2026: 14,605,503.64 there, 14,605,504 here; the cent is rounding).

    `exclude` is the curated list the panel uses, and it must be honoured
    here for the same reason: TKO's proxy reports Ari Emanuel at zero Class
    B, and the panel drops those shares because the company itself says they
    are not his. A feed reporting him trading them would contradict the
    table beside it on the same page.

    Position -- holding, net change -- comes from `history`, the walk this
    codebase has spent its life hardening. Pass `load_history(path)`; without
    it the feed still works, with the position columns empty.
    """
    subs = client.submissions(issuer_cik)
    ordered = sorted(
        (f for f in displace_amended([f for f in subs.get("_filings", [])
                                      if f.get("form") in SECTION16])),
        key=lambda f: (f.get("reportDate") or f.get("filingDate") or "",
                       f.get("accessionNumber") or ""))
    try:
        own = client.submissions(int(str(owner_cik).lstrip("0")))
    except Exception:  # noqa: BLE001
        return []
    accs = {f.get("accessionNumber") for f in own.get("_filings", [])}
    mine = [f for f in ordered if f.get("accessionNumber") in accs]
    if max_filings:
        mine = mine[-max_filings:]
    hist_rows = (history or {}).get(int(issuer_cik), [])

    out: list[Event] = []
    for f in mine:
        root = _parse(client, issuer_cik, f)
        if root is None:
            continue
        acc = f.get("accessionNumber") or ""
        form = f.get("form") or ""
        when = f.get("reportDate") or f.get("filingDate") or ""
        lines = _rows(root, form, when, acc)
        if not lines:
            continue
        plan = plan_state(root)
        others = sorted({r.code for r in lines if r.code in COMPANY_CODES})

        groups: dict = {}
        for r in lines:
            if r.code not in TRADE_CODES:
                continue
            if any(e.matches(r.security, r.direct) for e in exclude):
                continue
            key = (r.code, (r.as_of or when)[:10])
            g = groups.setdefault(key, {
                "shares": 0.0, "value": 0.0, "rows": 0, "unpriced": 0,
                "secs": set(), "dirs": set()})
            g["shares"] += abs(r.moved)
            g["rows"] += 1
            g["secs"].add(r.security.strip())
            g["dirs"].add(r.direct)
            if r.price and r.price > 0:
                g["value"] += abs(r.moved) * r.price
            else:
                g["unpriced"] += 1

        for (code, day), g in groups.items():
            if since and day < since:
                continue
            shares, value = g["shares"], g["value"]
            priced = g["rows"] - g["unpriced"]
            after, net, resid = _position(hist_rows, day)
            out.append(Event(
                ticker=ticker, issuer_cik=issuer_cik, ceo=ceo,
                owner_cik=str(owner_cik), accession=acc, form=form,
                filed=(f.get("filingDate") or "")[:10], traded=day, code=code,
                buy=(code == "P"), shares=shares,
                value=value if priced else None,
                avg_price=(value / shares) if (priced and shares) else None,
                rows=g["rows"], unpriced_rows=g["unpriced"],
                securities=" | ".join(sorted(g["secs"])),
                direct="".join(sorted(g["dirs"])), plan=plan,
                holding_after=after, net_change=net, residue=resid,
                other_codes="".join(others),
                url=_doc_url(issuer_cik, acc, f.get("primaryDocument") or ""),
            ))
    return out


def flag_prices(events: list[Event], factor: float = 10.0,
                window: int = 180) -> None:
    """Mark prices wildly out of line with the ticker's own neighbours in time.

    Set, never applied. A handful of errors in thirteen thousand events does
    not justify a correction mechanism, and a reader who can open the filing
    and see $2,261,327 on a $226 stock for themselves is better served by a
    flag than by a number we quietly changed.

    Compared against the median of the same ticker's priced events within
    `window` days either side, not the calendar year. The year bucket was
    built for splits and failed at its own example: Amazon's 20-for-1 landed
    mid-2022, so that year's median stayed pre-split and every legitimate
    post-split trade in it read as an error. A rolling window heals itself --
    within weeks of a split the neighbourhood is post-split too. The first
    trade after a split can still carry a flag until a neighbour corroborates
    it (Booking, 15 April 2026), which fails in the tolerable direction: a
    caution on a true price for a while, never silence on a false one.
    """
    import statistics
    from datetime import date

    def day(d: str):
        try:
            return date.fromisoformat((d or "")[:10]).toordinal()
        except ValueError:
            return None

    bytk: dict = {}
    for e in events:
        t = day(e.traded)
        if t is not None and e.avg_price and e.avg_price > 0:
            bytk.setdefault(e.ticker, []).append((t, e.avg_price))
    for e in events:
        if not e.avg_price or e.avg_price <= 0:
            continue
        t = day(e.traded)
        if t is None:
            continue
        peers = [p for (u, p) in bytk.get(e.ticker, ())
                 if abs(u - t) <= window]
        if len(peers) < 3:
            continue
        med = statistics.median(peers)
        if med > 0 and (e.avg_price > med * factor or e.avg_price < med / factor):
            e.price_flag = f"price {e.avg_price:,.2f} vs {med:,.2f} median"
