"""How a stake was acquired: bought, or paid.

Every Form 4 row carries a transaction code saying what happened. We have
been reading the resulting balance and discarding the code -- but the code is
what separates a chief executive who owns three per cent because they BOUGHT
it from one who owns three per cent because they were PAID it. For a product
about founder ownership, that distinction is arguably the whole point.

    P   open-market purchase        their own money
    A   grant or award              the company's
    M   exercise of a derivative    a grant, one step removed
    C   conversion                  a grant, or a unit exchange at an up-C
    S   open-market sale
    F   withheld for tax or strike  never a sale, and often mistaken for one
    D   disposition to the issuer   forfeiture
    G   gift, either direction

TWO THINGS TO BE CAREFUL ABOUT.

An OPTION grant is code A in Table II; the shares arrive years later as code
M in Table I. Counting both would double the compensation. Only Table I is
read here, so A is stock granted directly and M is stock from exercising.

And these are LIFETIME acquisitions, not the current holding. Someone can buy
a million shares and sell a million. "How they acquired" and "what they still
own" are different questions, and this answers only the first -- so the fields
are named for flows, never for a position.

A FOUNDING STAKE IS NEITHER. It appears in no transaction: it is simply
there on the Form 3, the initial statement filed on becoming an insider.
Musk held about 449.6 million Tesla shares at his -- a third of everything
he has ever had -- and none of it was bought or granted.

Counting only transactions reported him as buying 0.6% of his stake, which
describes a founder as though he were a hired executive. The opening
position is its own source, and for this product it is the most interesting
one: it is what "founder-led" actually means.

THE FLOWS SHOULD RECONCILE TO THE HOLDING, and when they do not, a split is
the usual reason:

    opening + acquired - disposed  ==  what they hold now

A split is not a transaction. No Form 4 reports one; the balance simply
multiplies, so a 2010 figure and a 2026 figure are in different units and
adding them is meaningless. Musk's Form 3 records about 28 million Tesla
shares and the reconciliation implies 449.6 million -- 16.1x, against the
15x of a 5-for-1 and a 3-for-1.

The current holding is unaffected: it comes from the newest filing, entirely
in today's units. Only the lifetime flows cross split boundaries, so the
residual is reported rather than hidden, and a row that does not reconcile
is one whose flow columns should not be summed.

AMENDMENTS RESTATE. A 4/A repeats the original's rows, and reading both would
count a transaction twice, so identical rows are collapsed on what identifies
a transaction: its date, code, security and size.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Acquisitions, grouped by where the shares came from.
PURCHASE = {"P"}                      # bought on the open market
GRANT = {"A"}                         # awarded by the company
FROM_DERIVATIVE = {"M", "C", "X"}     # an option or unit becoming stock
GIFT = {"G"}
# Dispositions worth separating: a sale is a decision, withholding is not.
SALE = {"S"}
SURRENDER = {"D", "F", "U"}


@dataclass
class Flows:
    """Lifetime share movements by code, acquisitions and disposals apart."""
    opening: float = 0.0          # held at the Form 3, before any transaction
    bought: float = 0.0
    granted: float = 0.0
    from_derivative: float = 0.0
    gifted_in: float = 0.0
    other_in: float = 0.0
    sold: float = 0.0
    surrendered: float = 0.0
    gifted_out: float = 0.0
    other_out: float = 0.0
    by_code: dict = field(default_factory=dict)
    seen: set = field(default_factory=set)

    @property
    def acquired(self) -> float:
        """Transactions only. The opening position is not an acquisition."""
        return (self.bought + self.granted + self.from_derivative
                + self.gifted_in + self.other_in)

    @property
    def sourced(self) -> float:
        """Everything the stake ever came from, opening balance included."""
        return self.opening + self.acquired

    @property
    def founded_share(self) -> float | None:
        """How much was already held on becoming an insider.

        For a founder this is the whole story and no transaction shows it.
        None when there was no Form 3 to read, which is not the same as zero.
        """
        return (self.opening / self.sourced * 100) if self.sourced > 0 else None

    @property
    def bought_share(self) -> float | None:
        """Of everything ever acquired, what fraction was bought outright.

        None rather than zero when nothing was ever acquired -- a chief
        executive appointed last quarter has no answer yet, and reporting
        0% would say they chose not to buy.
        """
        total = self.sourced
        return (self.bought / total * 100) if total > 0 else None

    def add(self, code: str, acquired: bool, shares: float,
            date: str, security: str, direct: str, splits=None) -> None:
        if not code or shares is None or shares != shares or shares <= 0:
            return
        # Dedupe on what was REPORTED, before adjusting -- an amendment
        # restates the original's figures, not the adjusted ones.
        raw = shares
        if splits is not None:
            shares = splits.adjust(shares, date)
        # An amendment restates the original's rows; this is what identifies
        # one transaction rather than one filing.
        key = (date, code, security.lower(), direct, round(raw, 4), acquired)
        if key in self.seen:
            return
        self.seen.add(key)

        c = code.upper()[:1]
        n, up, down = self.by_code.get(c, (0, 0.0, 0.0))
        self.by_code[c] = (n + 1, up + (shares if acquired else 0.0),
                           down + (0.0 if acquired else shares))

        if acquired:
            if c in PURCHASE:
                self.bought += shares
            elif c in GRANT:
                self.granted += shares
            elif c in FROM_DERIVATIVE:
                self.from_derivative += shares
            elif c in GIFT:
                self.gifted_in += shares
            else:
                self.other_in += shares
        else:
            if c in SALE:
                self.sold += shares
            elif c in SURRENDER:
                self.surrendered += shares
            elif c in GIFT:
                self.gifted_out += shares
            else:
                self.other_out += shares

    @property
    def disposed(self) -> float:
        return (self.sold + self.surrendered + self.gifted_out + self.other_out)

    def reconcile(self, holding: float) -> tuple[float, float | None]:
        """-> (residual, residual as a share of the holding).

        Zero means every share is accounted for. A large residual means the
        flows span a split, or a filing was missed -- either way the columns
        should not be added together for that row.
        """
        residual = holding - (self.opening + self.acquired - self.disposed)
        pct = (abs(residual) / holding * 100) if holding else None
        return residual, pct

    def tally(self) -> str:
        """"A=12:450,000" -- code, how many transactions, how many shares."""
        out = []
        for c, (n, up, down) in sorted(self.by_code.items(),
                                       key=lambda kv: -(kv[1][1] + kv[1][2])):
            moved = up + down
            out.append(f"{c}={n}:{moved:,.0f}")
        return "|".join(out)
