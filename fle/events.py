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

ONE TRADE IS MANY ROWS, AND ONE FILING IS ONE TRADE. Olivier Pomel's
10 November 2021 sale is 23 rows at 23 weighted-average prices, because
that is how a broker fills a large order. Pemble's is 29 rows for a single
5,000-share disposal. And a 10b5-1 plan or a block sale executes over a
few days but is one instruction, filed once: Lacerte's September 2026
Bill.com filing is 257,243 shares over two days. So rows fold into ONE
EVENT PER (accession, code). The event carries the first and last trade
day (Commvault's reads 17 to 19 August), the total shares and value, and
the weighted average price.

WHY NOT PER DAY, WHICH IS WHAT THIS REPLACED. History states the position
once per filing, on the filing's last trade day. An event per day gave
the earlier days no position of their own, and the code handed them the
nearest earlier snapshot's holding and net change -- a number about a
different trade. A quarter of all trades sat on such days; 341 filings
carried days that contradicted each other. Commvault's three-day sale
read "position unchanged" on two days because the PREVIOUS filing netted
to zero; ADPT's two-day exercise-and-sell read "discretionary sale,
12.8% of stake" on day one because the previous filing had a real sale
in it; John May was shown as having sold Deere six times, when every
sale of his was exercised shares. The question "did the stake move" is a
question about the filing, because the filing is the unit the balance is
reported at. Asking it of the day was asking the wrong record.

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

GROSS SOLD AND NET CHANGE ARE DIFFERENT NUMBERS, AND THE PERCENT IS THE
NET. Deere sold $2.69m and the position did not move. Pomel sold $39.4m and
the position genuinely fell by 206,223, because his conversion took Class B
out of Table II while the sale took Class A out of Table I. From Table I
alone the two look identical. The dollars are what they sold (gross); the
"% of stake" is what the filing did to the position: after against before,
signed. It was gross shares over the position before, which read "-40.4%
of stake" on a May filing that exercised 25,130, sold 19,907 and left him
5,223 shares RICHER. Unchanged (an exercise-and-sell) and not stated (a
partial filing, with residue) now fall out of the number instead of being
special cases beside it.

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

from dataclasses import dataclass

from .ledger import (SECTION16, _doc_url, _parse, _rows,
                     displace_amended, period_end, issuer_of, is_share_class)
from .history import COVER_FORMS

# A market trade, and nothing else. See the module docstring.
TRADE_CODES = ("P", "S")
# A FILING WITH NO TRADE STILL MOVES THE STAKE. Musk's Held stepped from
# 423M to 509M between a December 2022 sale and a September 2025 purchase
# with nothing in the table to say why: the option exercises and awards in
# between were not rows. A filing with no purchase or sale but a
# transaction in a counted class becomes one row of its own, named for what
# it was, in this order of precedence when a filing carries several.
COMP_CODES = ("M", "A", "C", "G", "F", "J", "D", "I", "W", "L", "Z", "K", "H", "O", "X", "U")
COMP_LABELS = {"M": "options exercised", "A": "award vested", "C": "converted", "G": "gift",
               "F": "shares withheld for tax", "J": "other transaction"}

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
    traded: str = ""                   # the filing's LAST trade day for this code
    traded_from: str = ""              # and its first; equal for a one-day filing
    code: str = ""
    buy: bool = False
    shares: float = 0.0                # gross shares this code moved, whole filing
    value: float | None = None         # sum of shares x price, as filed
    avg_price: float | None = None
    avg_price_adjusted: float | None = None   # in today's shares, for the price chart
    rows: int = 0                      # lines folded into this event
    unpriced_rows: int = 0
    securities: str = ""
    direct: str = ""
    plan: str = "unknown"
    holding_after: float | None = None  # the day's total, raw, from history
    net_change: float | None = None     # what THIS filing did: its own rows, acquired less disposed, counted classes
    outstanding: float | None = None    # shares outstanding on record for the day (the last cover page), from history
    pct_after: float | None = None      # the stake at the end of the day, as history published it
    day_net: float | None = None        # what the day did on record, all its filings and any residue, from history
    residue: float | None = None        # history's `unexplained` for the day
    other_codes: str = ""              # A/M/F/C/G in the same filing
    price_flag: str = ""
    url: str = ""
    registered: str = ""               # the issuer's first Section 16 filing date

    @property
    def pre_registration(self) -> bool:
        """A trade dated before the issuer's first Section 16 filing.

        Section 16 reporting begins at registration, and the first Form 4
        after the Form 3 catches up on everything since: tenders,
        conversions, the odd sale at the private price. Musk's 11,390
        SpaceX shares went on 2 April 2026, seven weeks before the S-1, on
        a Form 4 filed 17 June. Real, on a filing he signed, and nothing to
        do with what he has done as a public-company chief executive -- so
        it is recorded, badged, and kept out of every summary, like a sale
        that did not move the stake. For a company public since the 2003
        electronic filings the date is ancient and nothing is touched.
        """
        return bool(self.registered) and bool(self.traded) \
            and self.traded < self.registered

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
        if self.code not in TRADE_CODES:
            # a filing with no trade: named for its principal code (see
            # COMP_CODES); an exercise that came with withholding says so
            base = COMP_LABELS.get(self.code, "other transaction")
            if self.code in ("M", "A") and "F" in self.other_codes:
                base += ", tax withheld"
            return base
        if self.buy:
            # THE SAME RULE, BOTH DIRECTIONS. A purchase after which the
            # position on record is exactly what it was -- Schwarzman's
            # $27m of Blackstone common in August 2026, where the walk
            # counts his common at zero before and after -- is a trade
            # this measurement did not register, and the page must not rank
            # it as a stake going up. Said as such; where the shares went is
            # the walk's question (Blackstone's is on the repair list).
            if self.stake_unchanged and not self.residue:
                return "purchase, position unchanged"
            return ("scheduled purchase" if self.plan == "plan"
                    else "open-market purchase")
        # A SALE THAT DID NOT REDUCE THE STAKE IS NOT "SOLD". Xu, 1 October
        # 2025: two M rows bring in 553,116 shares and six sales dispose of
        # 34,166; nothing he held before was sold and the stake rose by
        # 518,950. Badged SOLD beside "stake +5.3%" the row read as
        # nonsense. The badge answers what he did on the market, the number
        # what the filing did to the stake; when the filing brought shares
        # in and the stake did not fall, the sale is compensation cashed and
        # the badge says which kind. The number stays: "unchanged" when it
        # was, the rise when he kept some.
        if not self.residue and self.net_change is not None and self.net_change > -0.5:
            kept = self.net_change >= 1.0     # some of what came in was kept
            if "M" in self.other_codes:
                # Musk exercised 2,105,171 and sold 340,564: "exercise and
                # sell" undersold it. The sale of the whole exercise leaves
                # the stake unchanged and says so; a part kept says that.
                return "exercise, part sold" if kept else "exercise and sell"
            if "A" in self.other_codes:
                return "vested and sold"
            if "C" in self.other_codes:
                return "convert and sell"
        if self.stake_unchanged and not self.residue:
            # The claim "position unchanged" is only made when history could
            # account for the whole day. A day carrying unexplained residue
            # gets the plain label and the residue flag instead.
            #
            # AND "EXERCISE" IS ONLY CLAIMED WHEN THE FILING SHOWS ONE. A
            # sale that left the common position where it was used to be
            # called exercise-and-sell on that fact alone. Blackstone's
            # chief executive holds no common at all: his sales are
            # partnership units exchanged into shares and sold the same
            # day, the common position is zero before and after, and the
            # site called $649m of units "options cashed" and, on the page,
            # "compensation". The codes in the same filing tell the three
            # cases apart: M is an option exercise, C a conversion or
            # exchange, and neither means the shares came from somewhere
            # this filing does not show -- said as such, not guessed.
            if "M" in self.other_codes:
                return "exercise and sell"
            if "C" in self.other_codes:
                return "convert and sell"
            return "sale, position unchanged"
        return {"plan": "scheduled sale",
                "discretionary": "discretionary sale"}.get(self.plan, "sale")

    @property
    def unchanged_kind(self) -> str:
        """"exercise", "vest", "convert", "bought", "" -- or None when the
        filing reduced the stake (or the day carries residue)."""
        if self.code not in TRADE_CODES:
            return {"M": "exercised", "A": "award", "C": "convert", "G": "gift", "F": "withheld"}.get(self.code, "other")
        return {"exercise and sell": "exercise", "exercise, part sold": "exercise", "vested and sold": "vest",
                "convert and sell": "convert", "sale, position unchanged": "",
                "purchase, position unchanged": "bought"}.get(self.label)

    @property
    def stake_unchanged(self) -> bool:
        """Shares changed hands and the position did not.

        Rounding tolerance, not exact zero: a filing can settle fractional
        shares. Anything under one share is not a change in a stake.
        """
        return self.net_change is not None and abs(self.net_change) < 1.0

    @property
    def _before(self) -> float | None:
        """The position before the day's trades, in the filed units: the
        closing balance history states for the day, less what the day did.
        Several filings on one day share it; each is measured against the
        stake as the day opened."""
        if self.holding_after is None or self.net_change is None:
            return None
        day = self.day_net if self.day_net is not None else self.net_change
        before = self.holding_after - day
        return before if before > 0 else None

    @property
    def pct_of_holding(self) -> float | None:
        """WHAT THE FILING DID TO THE STAKE, as a share of the stake before
        it, signed: a sale that halved the position is -50.0; an exercise
        that sold most and kept some is a small positive number beside a
        SOLD badge, which is the truth of that filing.

        None when the filing's own position is not in the record (net is
        None), when the day carries residue the walk could not attribute,
        or when the position before computes to zero: a chief executive
        who buys their first shares opened at zero, and a percentage of
        nothing is not a number. A stake that did not move gets no
        percentage either; the label says "unchanged" instead, because
        28.43% of a stake that did not move is arithmetically right and
        communicatively false (John May's January 2026 exercise-and-sell).
        """
        if self.net_change is None or self.stake_unchanged or self.residue:
            return None
        before = self._before
        if before is None:
            return None
        return 100.0 * self.net_change / before

    # A RESIDUE TOO SMALL TO CHANGE THE ANSWER. Under one percent of the
    # trade AND under a tenth of a percent of the position: whichever way
    # the unexplained shares resolve, the percentage rounds the same.
    IMMATERIAL_RESIDUE = (0.01, 0.001)

    @property
    def pct_approx(self) -> float | None:
        """The percentage, stated with a caution, when the day's residue
        cannot move it: the net less the residue, over the position before.

        Lip-Bu Tan's $10m Intel purchase: 105,263 shares bought, 561 shares
        the walk could not attribute (a grant on the same filing). The
        strict rule declined the percentage over 561 shares -- half a
        percent of the trade, four hundredths of a percent of the position
        -- and printed "not stated" beside the largest purchase on the
        page. Across the feed, 783 of 4,087 residue days are this shape;
        the rest (a median residue of 38% of the trade, and splits the walk
        did not absorb at the top) stay unstated until the walk is fixed.
        """
        if not self.residue or self.net_change is None \
                or self.stake_unchanged or not self.shares:
            return None
        before = self._before
        if before is None:
            return None
        res = abs(self.residue)
        if res / self.shares >= self.IMMATERIAL_RESIDUE[0]:
            return None
        if res / max(before, self.holding_after) >= self.IMMATERIAL_RESIDUE[1]:
            return None
        return 100.0 * self.net_change / before


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
            # FILINGS ONLY. History also carries a row per cover page
            # (history.add_cover_points): same holding, new denominator, no
            # trade. A trade on a day with no snapshot of its own borrows
            # the nearest earlier row's net (see _position), and a cover
            # row's net is zero by construction -- so a sale two days into
            # a three-day filing that followed a 10-Q would have read
            # "position unchanged" and left the feed. A quarter of all
            # trades sit on such days. The holding is the same either way.
            if (r.get("form") or "") in COVER_FORMS:
                continue
            try:
                cik = int(r.get("cik") or 0)
                row = ((r.get("date") or ""),
                       float(r.get("shares") or 0),
                       float(r.get("shares_split_adjusted") or r.get("shares") or 0),
                       float(r.get("unexplained") or 0),
                       # the day's denominator and stake, as history published them
                       float(r["outstanding"]) if r.get("outstanding") else None,
                       float(r["pct"]) if r.get("pct") else None)
            except ValueError:
                continue
            out.setdefault(cik, []).append(row)
    for v in out.values():
        v.sort()
    return out


def _split_factor(hist_rows: list, day: str) -> float | None:
    """How many of today's shares one share on `day` has become, read off
    history's own snapshot (shares_split_adjusted / shares) rather than a
    second splits fetch. The snapshot ON the day carries exactly the
    factor the day's trade needs; failing that, the next snapshot after
    it (a split between the two would be missed, and is rare enough that
    re-asking the feed here would be a second mechanism for one job).
    None when history has nothing to say."""
    if not hist_rows:
        return None
    pick = None
    for row in hist_rows:
        d, raw, adj = row[0], row[1], row[2]
        if d >= day:
            pick = (raw, adj)
            break
    if pick is None:
        raw, adj = hist_rows[-1][1], hist_rows[-1][2]
    else:
        raw, adj = pick
    if not raw or not adj:
        return None
    return adj / raw


def _position(hist_rows: list, day: str):
    """-> (holding_after_raw, net_change_adj, residue, outstanding, pct) for
    one filing day. The last two are history's own for the day, None when
    the day has no snapshot.

    net_change is the difference of SPLIT-ADJUSTED totals between this day's
    snapshot and the previous one, so a split between two filings never reads
    as a trade. holding_after is the day's RAW total -- the same units the
    filed trade is in, which is what a percent-of-stake needs.

    THE NET IS THE FILING'S OWN OR NOTHING. A day history has no snapshot
    for gets the forward-filled holding, no net and no residue. It used to
    get the nearest earlier snapshot's net -- a number about a different
    filing -- and since the event's verdict is decided from the net, a
    quarter of all trades were labelled by their neighbour. Absence of
    evidence is its own answer, and it is not zero either.

    residue is history's `unexplained` for the day: the amount the total
    moved that the day's transactions do not account for. Adam Foroughi's
    June 2026 filings are the standing example -- several same-day Form 4s,
    a trust reported in one, omitted in the next, restated at a different
    balance in the third. History cannot attribute that cleanly and says so;
    an event on such a day inherits the flag instead of asserting a net.
    """
    if not hist_rows:
        return None, None, None, None, None
    idx = None
    for i, row in enumerate(hist_rows):
        d = row[0]
        if d == day:
            idx = i
            break
        if d > day:
            idx = i - 1
            break
    else:
        idx = len(hist_rows) - 1
    if idx is None or idx < 0:
        return None, None, None, None, None
    row = hist_rows[idx]
    d, raw, adj, resid = row[:4]
    outstanding = row[4] if len(row) > 4 else None
    pct = row[5] if len(row) > 5 else None
    if d != day:
        return raw, None, None, None, None
    if idx == 0:
        return raw, None, resid, outstanding, pct
    # THE DAY'S NET IN THE DAY'S UNITS. The difference is taken between
    # split-adjusted totals so a split between two filings never reads as
    # a trade, then converted back into the units the day was filed in,
    # which is what holding_after and the filing's own net are in. In
    # adjusted units it read +3,513,240 on a day Musk's position moved
    # 1,171,080, and "before the day" came out 2.4M short.
    day_adj = adj - hist_rows[idx - 1][2]
    day_raw = day_adj * (raw / adj) if adj else day_adj
    return raw, day_raw, resid, outstanding, pct


def build_events(client, issuer_cik: int, owner_cik: str, ticker: str = "",
                 ceo: str = "", since: str = "", max_filings: int | None = None,
                 history: dict | None = None, exclude=()) -> list[Event]:
    """Every P/S event for one chief executive, oldest first.

    Trade detail -- code, shares, price, value, the plan checkbox -- comes
    from the filing rows, where it has been verified to the cent against
    history's independent arithmetic (traded_value for AppLovin, 10 June
    2026: 14,605,503.64 there, 14,605,504 here; the cent is rounding).

    THE POSITION IS LOOKED UP ON THE FILING'S OWN DAY: the newest
    transaction in the document (ledger.period_end), which is the day
    history dated its snapshot for this filing by. One function decides the
    date on both sides, so the join cannot drift.

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
    # continuation documents of one filing are one filing: one event for
    # Foroughi's three-day sale, not seven (ledger.batch_continuations)
    from .ledger import batch_continuations
    mine = batch_continuations(client, issuer_cik, mine)
    # when Section 16 reporting began for this issuer: the earliest such
    # filing on its feed, amendments and all -- the boundary that tells a
    # public-company trade from a pre-registration catch-up
    registered = min((f.get("filingDate") or "" for f in subs.get("_filings", [])
                      if f.get("form") in SECTION16 and f.get("filingDate")),
                     default="")
    if max_filings:
        mine = mine[-max_filings:]
    hist_rows = (history or {}).get(int(issuer_cik), [])
    ends: dict = {}

    out: list[Event] = []
    for f in mine:
        root = _parse(client, issuer_cik, f)
        if root is None:
            continue
        # A FILING IN BOTH FEEDS THAT IS ABOUT ANOTHER COMPANY. Blackstone
        # is a 10% owner of the companies it controls and Schwarzman signs
        # those Form 4s as the controlling person, so 587 of the 605
        # filings in both his feed and Blackstone's are about Viper, Gates,
        # Cheniere, Hilton, Bumble, Kodak and a hundred more; 18 are about
        # Blackstone, the newest from 2023. The ledger and history read the
        # filing's own <issuer> and skip the rest (ledger.issuer_of); the
        # feed only ever had this check missing here, and $547M of other
        # companies' stock headed the Sold column as his.
        got = issuer_of(root)
        if got and got != str(int(issuer_cik)):
            continue
        acc = f.get("accessionNumber") or ""
        form = f.get("form") or ""
        when = f.get("reportDate") or f.get("filingDate") or ""
        lines = _rows(root, form, when, acc)
        if not lines:
            continue
        plan = plan_state(root)
        others = sorted({r.code for r in lines if r.code in COMPANY_CODES})
        # the day history stated this filing's position on
        period = period_end(client, issuer_cik, f, ends)

        # WHAT THE FILING DID TO THE STAKE, FROM ITS OWN ROWS. Acquired less
        # disposed across every counted row, all codes. History states the
        # position once per DAY, and Musk's 21 December 2021 has two
        # filings: one exercises and sells (net positive), one sells
        # outright. Handed a share of the day's net by gross shares, the
        # outright sale read "stake +0.74%". The filing says what it did;
        # history supplies only the day's position and the residue flag.
        own_net = sum((r.moved if r.acquired else -r.moved) for r in lines
                      if r.code and r.shares == r.shares
                      and (r.table == "I" or is_share_class(r.security))
                      and not any(e.matches(r.security, r.direct) for e in exclude))
        groups: dict = {}
        counted = [r for r in lines if r.code and r.shares == r.shares
                   and (r.table == "I" or is_share_class(r.security))
                   and not any(e.matches(r.security, r.direct) for e in exclude)]
        has_trade = any(r.code in TRADE_CODES for r in counted)
        comp_code = next((c for c in COMP_CODES if any(r.code == c for r in counted)), None) if not has_trade else None
        for r in lines:
            if r.code not in TRADE_CODES and not (comp_code and r.code == comp_code):
                continue
            if any(e.matches(r.security, r.direct) for e in exclude):
                continue
            if r.code == comp_code and r.shares != r.shares:
                continue
            day = (r.as_of or when)[:10]
            g = groups.setdefault(r.code, {
                "shares": 0.0, "value": 0.0, "rows": 0, "unpriced": 0,
                "secs": set(), "dirs": set(), "first": day, "last": day})
            g["shares"] += abs(r.moved)
            g["rows"] += 1
            g["secs"].add(r.security.strip())
            g["dirs"].add(r.direct)
            g["first"] = min(g["first"], day)
            g["last"] = max(g["last"], day)
            if r.price and r.price > 0:
                g["value"] += abs(r.moved) * r.price
            else:
                g["unpriced"] += 1

        for code, g in groups.items():
            day = g["last"]
            if since and day < since:
                continue
            shares, value = g["shares"], g["value"]
            priced = g["rows"] - g["unpriced"]
            if code not in TRADE_CODES:
                # a compensation row: the shares are what the stake changed
                # by, and a strike price or nothing is not a market value
                shares, value, priced = abs(own_net), 0.0, 0
            after, day_net, resid, outstanding, pct_after = _position(hist_rows, period)
            # a day history never saw carries a stale position: the filing's
            # own net is known but nothing to measure it against is, so no
            # verdict, as before
            net = own_net if day_net is not None else None
            price = (value / shares) if (priced and shares) else None
            # THE CHART NEEDS TODAY'S UNITS. A Tesla sale filed at $1,000
            # in 2021 sits at $333 against a split-adjusted price line;
            # drawn as filed it would float above the whole chart. The
            # filed figure is kept beside it, untouched.
            factor = _split_factor(hist_rows, day) if price else None
            out.append(Event(
                ticker=ticker, issuer_cik=issuer_cik, ceo=ceo,
                owner_cik=str(owner_cik), accession=acc, form=form,
                filed=(f.get("filingDate") or "")[:10], traded=day,
                traded_from=g["first"], code=code,
                buy=(code == "P") or (code not in TRADE_CODES and own_net > 0), shares=shares,
                value=value if priced else None,
                avg_price=price,
                avg_price_adjusted=(price / factor) if (price and factor) else None,
                rows=g["rows"], unpriced_rows=g["unpriced"],
                securities=" | ".join(sorted(g["secs"])),
                direct="".join(sorted(g["dirs"])), plan=plan,
                holding_after=after, net_change=net, day_net=day_net, residue=resid,
                outstanding=outstanding, pct_after=pct_after,
                other_codes="".join(others),
                url=_doc_url(issuer_cik, acc, f.get("primaryDocument") or ""),
                registered=registered,
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
