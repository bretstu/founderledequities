"""A chief executive's stake after every filing they made.

THE WALK IS ALREADY THE SERIES, RUN BACKWARDS.

    today   newest first, the FIRST filing to report a group settles it
    series  oldest first, each filing OVERWRITES the group it reports

Both end in the same place -- the newest filing per group. So the final
snapshot MUST equal the panel's figure, on every company. That is a free
correctness test, and `history` reports it per row rather than leaving it to
be discovered later.

The settling itself is untouched: last transaction plus every holding, keyed
on the class. Whatever is right for today is right for 2019, applied to
2019's filings with 2019's class list.

A POINT WHEN THE DENOMINATOR MOVES, NOT ONLY WHEN THE PERSON FILES. Musk
exercised on 16 June 2026 and Tesla's next cover page, dated 16 July,
carried the shares that exercise issued. Nobody filed a Form 4 on 16 July,
so the series ended on 16 June at 29.91%: his new shares over the old
count, exactly the error the metric was built to avoid. The panel said
28.44%, and was right. On 1,253 of 2,045 companies the last point divided
by an older count than the panel's. So the series now carries a point for
every cover page after its first filing: the same shares, the new count,
no trade (see add_cover_points). The last point equals the panel's figure
whichever side moved last, and the slope between filings is honest.

WHAT BECOMES TIME-VARYING, AND WHAT THAT COSTS.

  the class list      one annual report a year (see series.classes_by_year)
  the denominator     every cover page ever filed, forward-filled
  splits              NEITHER figure is immune. The share count is restated
                      to today's basis; the percentage needs the denominator
                      carried through the split too, because the cover page
                      restates its count months after the Form 4 does. So
                      both a reported and an adjusted count are emitted

WHAT IT INHERITS.

A group with no newer mention persists, exactly as it does in the panel. So
a stale group inflates every snapshot after it -- TKO's Class B would sit in
the series from February 2025 onward. The difference is that in a series it
looks like what it is: a step that never reverses.

WHERE IT STOPS. Cover-page tagging is reliable from about 2011, so a
denominator cannot honestly be built before then. Ten years is well inside
that. Filings BEFORE the window are still read -- a balance set in 2013 and
never restated is still the balance in 2016 -- they simply are not emitted.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import copy

from .ledger import (SECTION16, Group, _merge_same_day, _parse, _rows,
                     displace_amended,
                     class_letters,
                     is_share_class, issuer_of, match_class, SINGLE_CLASS,
                     vehicle_key)


@dataclass
class Snapshot:
    """The position after one filing."""
    date: str = ""
    form: str = ""
    accession: str = ""
    shares: float = 0.0            # as the filings reported it
    adjusted: float = 0.0          # restated to today's split basis
    outstanding: float | None = None
    traded: float = 0.0            # shares moved that day, signed
    traded_value: float | None = None   # what those shares actually fetched
    unpriced: int = 0              # transaction rows reporting no price
    unexplained: float = 0.0       # balance change no transaction accounts for
    pct: float | None = None
    codes: str = ""                # what moved in this filing
    groups: int = 0
    classes: str = ""
    restated: bool = False         # a later filing put this balance back
    cover: bool = False            # a cover page moved the count; no filing by the person


@dataclass
class History:
    snapshots: list = field(default_factory=list)
    read: int = 0
    skipped_issuer: int = 0
    matches_panel: bool | None = None
    note: str = ""


def _bridge(hist, splits, bal, dropped_when, row_index, seen_when) -> None:
    """Raise the rows between a vehicle's omission and its reattestation.

    Huang's four annuity trusts vanish from the September 2016 form and
    return in October at 769,705 each, untouched. Armstrong's co-founder
    trust is omitted for a YEAR of filings and comes back at 950,490 to the
    share. The later document is the evidence: a position that reappears at
    the balance it vanished at, with no transaction anywhere between, was
    held the whole time. Everything emitted during the gap is raised by it.

    The balance travels in the basis it was filed in, so each raised row
    converts it into its own basis, and the reconciliation of the omission
    row is repaired by the same amount it was distorted by.
    """
    adj = splits.adjust(bal, dropped_when) if splits else bal
    # Fires only for a vehicle benched by a filing's SILENCE and claimed
    # back by an arithmetic match -- the displacement path that manufactured
    # phantoms is gone, and with it the need for the day-net corroboration
    # guard, which proved too blunt: a day that loses one vehicle while a
    # chain arrives in another nets positive, and the guard refused true
    # repairs on exactly those days (Stankey's Benefit Plan, Zuckerberg's
    # comma pair, Sprecher's trusts).
    if row_index >= len(hist.snapshots):
        return
    first = hist.snapshots[row_index]
    if first.date != dropped_when:
        return
    for i in range(row_index, len(hist.snapshots)):
        row = hist.snapshots[i]
        raw = (adj / splits.factor_since(row.date)) if splits else bal
        row.shares += raw
        row.adjusted += adj
        if row.outstanding:
            row.pct = round(row.shares / row.outstanding * 100.0, 4)
    first.unexplained += adj
    # the row after the gap reconciles against the raised balance on its own


def _chain_into(acc, g) -> None:
    """Fold one period filing into the period's accumulated state.

    Segments link by arithmetic: X continues Y when X's opening balance is
    Y's closing balance. Processing order does not matter -- if the segment
    already held proves to be the CONTINUATION of the one arriving, the held
    one is kept and only its origin is extended. Linking under a different
    vehicle key requires the arriving segment to carry transactions, so two
    genuinely distinct vehicles that merely hold equal balances are never
    collapsed.
    """
    tol = 0.5
    balances = acc.vehicles()
    for vehicle, end in g.vehicles().items():
        op = g.opening.get(vehicle, end)
        transacted = vehicle in g.last_txn
        if vehicle in balances:
            held_end = balances[vehicle]
            held_op = acc.opening.get(vehicle, held_end)
            if abs(held_op - end) < tol and abs(op - held_end) >= tol:
                # the held segment CONTINUES the arriving one: keep the
                # held balance, extend the chain's origin backwards
                acc.opening[vehicle] = op
            else:
                # the arriving segment continues (or restates) the held one
                acc.hold_by_vehicle[vehicle] = end
                acc.last_txn.pop(vehicle, None)
                acc.opening[vehicle] = (held_op if abs(op - held_end) < tol
                                        else op)
            continue
        linked = False
        if transacted:
            for u, bal in list(balances.items()):
                if u == vehicle:
                    continue
                u_op = acc.opening.get(u, bal)
                if abs(bal - op) < tol:
                    # continuation under a new spelling: the new key
                    # replaces the old, keeping the chain's origin
                    for d in (acc.hold_by_vehicle, acc.last_txn, acc.opening):
                        d.pop(u, None)
                    acc.hold_by_vehicle[vehicle] = end
                    acc.opening[vehicle] = u_op
                    linked = True
                    break
                if abs(u_op - end) < tol and u in acc.last_txn:
                    # the held segment continues the arriving one, which
                    # arrived late under its own spelling: keep the held
                    # balance and extend its origin
                    acc.opening[u] = op
                    linked = True
                    break
        if not linked:
            acc.hold_by_vehicle[vehicle] = end
            acc.last_txn.pop(vehicle, None)
            acc.opening[vehicle] = op
    acc.holdings = sum(acc.hold_by_vehicle.values())
    acc.shares = sum(acc.vehicles().values())


def _period(f: dict) -> str:
    """The date a filing REPORTS ON, which is what makes two of them one
    moment. An amendment carries the period of the report it corrects, so it
    lands beside that report rather than beside whatever it was filed next
    to years later."""
    return (f.get("reportDate") or f.get("filingDate") or "")




def mark_restated(snaps: list, window: int = 12,
                  restore: float = 0.7, size: float = 0.2) -> None:
    """Mark snapshots depressed by a partial filing that a later filing put
    back.

    THE DETECTOR LIVES WHERE THE INFORMATION LIVES.

    The walk already computes `unexplained` -- the balance change no
    transaction accounts for. A partial filing (one that names only some of
    a person's vehicles) opens a large NEGATIVE unexplained; when a later
    filing lists the missing vehicles again, a compensating positive closes
    it. Akamai's chief executive has three such craters in a decade of
    otherwise steady 2%: single filings that name only his direct line,
    with the trusts restored days later. EchoStar's merger day is the same
    shape at 98 million shares.

    The frontend used to guess at these with a V-shape heuristic, which
    missed multi-row craters (two partial filings in a row are not a V) and
    could never see past its own window. Here the whole series is in hand:

      entry    |unexplained| >= size * the shares held before the jump,
               in EITHER direction -- a crater (partial filing) and a spike
               (double count) are the same artifact mirrored. The size bar
               is deliberately low: THE MIRROR IS THE GATE. A real sale
               lives in `traded`; an unexplained jump that reverses almost
               exactly within a few filings is an artifact by construction
               at 40%% of a position as surely as at 80%%. Ergen's May 2026
               row dropped 60.5M shares unexplained -- 41%% of the prior
               position, under the old 0.5 bar -- and was restored the next
               filing to within 1,828 shares of zero. Akamai's
               false 3.42% "peak" of 11 February 2016 was +3,039,226
               unexplained in and the identical amount out five days
               later: trusts re-listed while still being carried.
      exit     cumulative unexplained since entry returns to within
               (1 - restore) of zero, inside `window` rows
      marked   every row from entry to just before the exit

    A jump that is NEVER reversed is not marked -- at the trailing edge it
    is indistinguishable from a genuine change, and honesty there means
    showing it with a caution, not hiding it on a guess.
    """
    # THE SCAN WALKS FILINGS. A cover-page point carries the same balance
    # and no residue, so it can neither open nor close a range; counting it
    # toward the window would shorten it by however many 10-Qs fell inside.
    # A cover row between a marked filing and its restoration is marked
    # with it: it carries the depressed balance too.
    idx = [k for k, sn in enumerate(snaps) if not getattr(sn, "cover", False)]
    f = [snaps[k] for k in idx]
    n = len(f)
    i = 1
    while i < n:
        u0 = f[i].unexplained or 0.0
        prev_sh = f[i - 1].adjusted or 0.0
        if abs(u0) < size * max(prev_sh, 1.0):
            i += 1
            continue
        cum = u0
        closed_at = None
        for j in range(i + 1, min(i + 1 + window, n)):
            cum += f[j].unexplained or 0.0
            if abs(cum) <= (1 - restore) * abs(u0):
                for k in range(idx[i], idx[j]):
                    snaps[k].restated = True
                closed_at = j
                break
        # THE RESTORATION CANNOT OPEN THE NEXT ARTIFACT. The row that
        # closed this range is the balance being put back -- but judged on
        # its own, against the crater right before it, the put-back looks
        # like an enormous unexplained spike, opens a bogus artifact, and
        # waits for the NEXT real crater's entry to "close" it -- marking
        # every healthy month in between. Akamai's 2016: one real crater
        # in March manufactured nine false marks through December. So the
        # scan resumes past the closer, never on it.
        i = (closed_at + 1) if closed_at is not None else i + 1


# The forms a cover-page point carries. A row with one of these is the
# count moving, not the person filing; every reader that wants the
# person's last word (the trailing-edge confidence cap, the panel match)
# skips them.
COVER_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A")


def add_cover_points(hist, series, splits=None, since: str = "") -> int:
    """One snapshot per cover page that moved the count, after the first
    filing snapshot: the same shares, the new denominator, no trade.

    THE SHARES TRAVEL IN THE COVER DATE'S BASIS. A cover page after a
    split reports post-split shares, so the carried holding is restated to
    that date through the split table, the same way the walk restates a
    trade. Nothing else moves: `traded` is zero, `codes` empty,
    `unexplained` zero, and the page reads a step of that shape as
    "share count changed".

    A cover page that repeats the count is not a point; a cover page on a
    day the person filed is already the denominator of that day's
    snapshot; a cover page before the first emitted snapshot has no
    position to divide. -> how many points were added."""
    if not series or not hist.snapshots:
        return 0
    have = {sn.date for sn in hist.snapshots}
    first = hist.snapshots[0].date
    added = []
    for p in series.points:
        if not p.shares or p.as_of <= first or p.as_of in have:
            continue
        if since and p.as_of < since:
            continue
        prev = None
        for sn in hist.snapshots + added:
            if sn.date < p.as_of and (prev is None or sn.date >= prev.date):
                prev = sn
        if prev is None or (prev.outstanding and abs(prev.outstanding - p.shares) < 1):
            continue
        raw = (prev.adjusted / splits.factor_since(p.as_of)) if splits else prev.shares
        added.append(Snapshot(
            date=p.as_of, form=p.form or "10-Q", accession=p.accession,
            shares=raw, adjusted=prev.adjusted, outstanding=p.shares,
            pct=(raw / p.shares * 100) if p.shares else None,
            groups=prev.groups, classes=prev.classes, cover=True))
    if not added:
        return 0
    # filings first on a shared date can never arise (those dates are
    # skipped above), so a plain sort by date keeps every order
    hist.snapshots = sorted(hist.snapshots + added, key=lambda sn: sn.date)
    return len(added)

def _with_supplements(root, form, when, acc, exclude):
    """The history walk reads filings through the same door as the ledger:
    a supplement the filer stated in a remark is one more table line here too."""
    from .ledger import supplement_rows
    rows = _rows(root, form, when, acc)
    return rows + supplement_rows(root, rows, form, when, acc, exclude)


def mark_restated_rows(rows: list) -> None:
    """mark_restated for CSV row dicts, at write time.

    THE MARK BELONGS TO THE FILE, NOT TO THE WALK. The nightly reuses a
    company's prior rows whenever it has no new filings -- that is why a
    refresh takes minutes instead of hours -- so any marking done only
    inside the fresh walk silently skips almost every company almost every
    night. EchoStar and Akamai kept their craters for exactly this reason:
    no new filing, rows carried, marks never computed. Running the same
    detector over the assembled rows just before writing makes the column
    true for every company in the file, walked or reused, every night.
    """
    by = {}
    for r in rows:
        by.setdefault((r.get("cik"), r.get("owner_cik")), []).append(r)

    class _S:
        __slots__ = ("adjusted", "unexplained", "restated", "cover")

        def __init__(self, adj, unexp, cover=False):
            self.adjusted, self.unexplained, self.restated = adj, unexp, False
            self.cover = cover

    for group in by.values():
        group.sort(key=lambda r: r.get("date") or "")
        snaps = []
        for r in group:
            try:
                adj = float(r.get("shares_split_adjusted") or 0)
            except ValueError:
                adj = 0.0
            try:
                unexp = float(r.get("unexplained") or 0)
            except ValueError:
                unexp = 0.0
            snaps.append(_S(adj, unexp, (r.get("form") or "") in COVER_FORMS))
        mark_restated(snaps)
        for r, sn in zip(group, snaps):
            r["restated"] = "TRUE" if sn.restated else ""


def build_history(client, issuer_cik: int, owner_cik: str, mine: list,
                  series=None, splits=None, exclude=(), since: str = "",
                  on_step=None) -> History:
    """One snapshot per filing, oldest first.

    `mine` is the person's filings for this issuer -- the same list the
    ledger walks, so the two cannot diverge on which documents count.
    """
    hist = History()
    groups: dict = {}
    # THE PERIOD, NOT THE POSTMARK.
    #
    # Two filings sharing a filing date do not necessarily describe one
    # moment. Musk filed a Form 4 for his transactions of 8 March 2023 and,
    # the same morning, an amendment to the ANNUAL form for 31 December
    # 2022. Merged as a same-day pair -- which is what sharing a postmark
    # used to mean -- his position came out at 822,113,652 against a real
    # 411,062,076.
    #
    # `reportDate` is the period the document actually covers, and it is in
    # the feed. Huang's genuine pair keeps working: both his Forms 4 report
    # the transactions of 4 January 2021, so they share a period as well as
    # a postmark.
    # An amendment restates its whole report; the original beside it would
    # count the period twice. See displace_amended.
    mine = displace_amended(mine)
    # BY THE MOMENT EACH FILING SPEAKS FOR. A Form 4's reportDate is its
    # earliest transaction; a catch-up spanning February to June sorts by
    # June, or the Form 3 between them is taken as the newer word. See
    # ledger.period_end, which the panel uses for the same reason.
    from .ledger import period_end
    ends: dict = {}
    ordered = sorted(mine, key=lambda f: (period_end(client, issuer_cik, f, ends),
                                          f.get("filingDate") or "",
                                          f.get("accessionNumber") or ""))

    period_acc: dict = {}        # class -> the period's filings, chained
    period_prev: dict = {}       # class -> the group as it stood BEFORE
    current_period = None
    # THE BENCH: vehicles a supersede removed, kept aside with the balance
    # they vanished at. If a later document lists the same vehicle at the
    # same balance, the removal was an omission, not a disposal -- the
    # position was held straight through -- and the emitted rows in between
    # are raised back. If it never returns, it stays gone: Musk's emptied
    # direct line is dropped once and no document ever contradicts that.
    bench: dict = {}             # class -> {vehicle: (balance, when, row_index)}

    day_codes: dict = {}
    day_traded: dict = {}
    day_value: dict = {}
    day_unpriced: dict = {}

    for i, f in enumerate(ordered, 1):
        if on_step:
            on_step(i, len(ordered))
        root = _parse(client, issuer_cik, f)
        if root is None:
            continue
        got = issuer_of(root)
        if got and got != str(int(issuer_cik)):
            hist.skipped_issuer += 1
            continue

        when = period_end(client, issuer_cik, f, ends)
        if when != current_period:
            current_period = when
            period_acc, period_prev = {}, {}
        acc = f.get("accessionNumber") or ""
        hist.read += 1

        # THE CLASS LIST AS IT WAS THEN. Block's "Common Stock" was the class
        # in 2019 and is not one now; keying on today's list would drop the
        # whole position.
        members = series.classes_at(when) if series else {}
        letters = class_letters(members)
        one_class = len(members) == 1

        here: dict = {}
        # WHAT THE DAY'S TRADES WERE WORTH.
        #
        # A share count says a chief executive sold forty thousand shares. It
        # does not say whether that was a rounding error or fourteen million
        # dollars, and the second is the fact a reader actually wants.
        #
        # Form 4 carries transactionPricePerShare on every priced row, so the
        # value is the filing's own arithmetic -- the price it executed at,
        # not today's close applied to an old trade, which would be a
        # fabrication dressed as precision.
        #
        # Accumulated across every filing made on this date, because the day
        # may carry several and only the last one emits a snapshot.
        for r in _with_supplements(root, f.get("form") or "", when, acc, exclude):
            if not r.code:
                continue
            # The codes label the day, and a day can be split across two
            # documents. Huang's 6 January 2021 pair carries the exercise and
            # the sales on the FIRST form; reading only the last left the
            # day with no codes at all.
            day_codes.setdefault(when, set()).add(r.code)
            # A COUNTED CLASS IS RECONCILED WHEREVER IT IS REPORTED.
            #
            # Meta's Class B converts into Class A, so it is filed in Table
            # II -- as a derivative -- while its balance is counted as a
            # share class like any other. Skipping Table II here meant every
            # conversion moved the balance with no transaction to explain
            # it: 700 of 958 snapshots carried a phantom residue, and the
            # activity feed would have withheld Zuckerberg's daily sales as
            # artifacts. Option rows are still skipped, because their
            # balances are not counted either.
            if r.table != "I" and not is_share_class(r.security):
                continue
            moved = r.moved if r.acquired else -r.moved
            day_traded[when] = day_traded.get(when, 0.0) + moved
            if r.price and r.price > 0:
                day_value[when] = (day_value.get(when, 0.0)
                                   + abs(r.moved) * r.price)
            elif r.moved:
                # A grant or a gift reports no price. Counted, not guessed at.
                day_unpriced[when] = day_unpriced.get(when, 0) + 1
        for r in _with_supplements(root, f.get("form") or "", when, acc, exclude):
            if r.shares != r.shares:
                continue
            if r.table == "II" and not is_share_class(r.security):
                continue
            if one_class:
                title = SINGLE_CLASS
            elif letters:
                title = match_class(r.security, letters)
                if title is None:
                    # AN OLD NAME IS STILL THIS COMPANY'S STOCK.
                    #
                    # Robinhood's IPO week: Tenev's Form 3 and first Form 4
                    # title everything plain "Common Stock", because that is
                    # what the security was called before the A/B
                    # recapitalisation settled. The class list -- built from
                    # cover pages that begin months later -- says Class A and
                    # Class B, the match fails, and dropping the rows erased
                    # his entire opening position: the record began at 0%
                    # for him and for 92 other chief executives.
                    #
                    # The filings themselves resolve the rename: his filing
                    # of 2 August J-codes "Common Stock" down to zero and
                    # J-codes Class A and Class B up by the same shares, so
                    # a raw-title group carries the balance straight through
                    # the rename and empties when the filer says it did.
                    # Cross-issuer junk cannot ride in on this: issuer_of()
                    # already rejects whole documents about other companies.
                    title = r.security
            else:
                title = r.security       # no class list: keep the raw title
            # The class is the group; the ownership form belongs to the
            # vehicle. See the long note in ledger.build_ledger.
            key = title.lower()
            g = here.get(key)
            if g is None:
                g = Group(security=title, direct=r.direct, as_of=r.as_of,
                          accession=acc, table=r.table)
                here[key] = g
            # Per VEHICLE, not per group -- see the same block in
            # ledger.build_ledger. Zuckerberg converts out of two vehicles in
            # one filing; taking only the last left 7,504,308 of his
            # 361,603,542, and the series oscillated between the two.
            vehicle = vehicle_key(r.direct, r.nature)
            if r.code:
                # The balance BEFORE this document touched the vehicle: the
                # first row's balance minus the first row's own move. It is
                # what lets two documents be recognised as one running
                # balance -- the second one OPENS where the first one ended.
                if vehicle not in g.opening:
                    signed = (r.moved if r.acquired else -r.moved) or 0.0
                    g.opening[vehicle] = r.shares - signed
                g.last_txn[vehicle] = r.shares
                g.moved_here = True
            else:
                g.opening.setdefault(vehicle, r.shares)
                g.holdings += r.shares
                g.hold_by_vehicle[vehicle] = (
                    g.hold_by_vehicle.get(vehicle, 0.0) + r.shares)
            g.rows += 1
        for g in here.values():
            g.shares = sum(g.last_txn.values()) + g.holdings
            g.filed = when
        for key in list(here):
            if any(e.matches(here[key].security, here[key].direct)
                   for e in exclude if not getattr(e, "is_addition", False)):
                del here[key]

        # ONE RUNNING BALANCE CAN CROSS A DOCUMENT BOUNDARY.
        #
        # Musk's 21 December 2021: one form exercises options and sells down
        # to 1,505,344; the other OPENS at 1,505,344 and sells to 1,154,864.
        # Zuckerberg's 9 November 2020: one form restates "By CZI Holdings
        # LLC" at 355,799,225; the other converts 36,000 out of "By CZI
        # Holdings, LLC" -- comma -- landing on 355,763,225, which is
        # 355,799,225 minus 36,000 exactly.
        #
        # Read separately, the first pair collapses a position and the
        # second doubles one. What joins them is the same evidence trusted
        # WITHIN a document: a segment whose opening balance is another
        # segment's closing balance is the same position continuing, and
        # the end of the chain is the state of it. No spelling is compared,
        # no accession order is trusted (Musk's later transactions sit in
        # the EARLIER accession), and nothing is fitted to an expectation.
        for key, g in here.items():
            # A DOCUMENT LISTING A BENCHED VEHICLE SETTLES ITS GAP.
            #
            # The bench holds a LIST per name, because anonymity means one
            # name can be several positions -- Foroughi's two trusts and a
            # transaction chain all file as "See footnote". A sighting is
            # matched by ARITHMETIC: the entry whose balance meets the
            # document's opening (a chain resuming) or its balance (holdings
            # restated whole) is the one that returned; a namesake at some
            # other figure is left waiting. Only when a single entry waits
            # and nothing matches does the old rule apply -- sighted, alive
            # again, off the bench, its gap left standing in unexplained.
            for vehicle, bal in list(g.vehicles().items()):
                waiting = bench.get(key, {}).get(vehicle)
                if not waiting:
                    continue
                op = g.opening.get(vehicle, bal)
                hit = (next((w for w in waiting if abs(op - w[0]) < 0.5), None)
                       or next((w for w in waiting if abs(bal - w[0]) < 0.5),
                               None))
                if hit is not None:
                    waiting.remove(hit)
                    _bridge(hist, splits, hit[0], hit[1], hit[2], when)
                # An unmatched entry keeps waiting. The old rule cleared it
                # on any sighting -- and that discarded the chain's entry at
                # Foroughi's 12 June restatement, two months before its true
                # return. With every bridge now required to show its loss,
                # a waiting entry can never fire onto a day it does not
                # explain, so patience costs nothing and guessing is gone.
                if not waiting:
                    bench[key].pop(vehicle, None)

            if key not in period_prev:
                period_prev[key] = groups.get(key)
            # THE ACCUMULATOR IS NOT THE ACCESSION.
            # This local used to be called `acc`, shadowing the filing's
            # accession string from the top of the loop -- and the snapshot
            # below faithfully wrote repr(Group(...)) into the published
            # accession column for every filing that chained. A reader
            # following "sources & links" got our internals instead of a
            # document number. Renamed, the shadow is impossible.
            chained = period_acc.get(key)
            if chained is None:
                chained = g
                period_acc[key] = chained
            else:
                _chain_into(chained, g)
                chained.moved_here = chained.moved_here or g.moved_here
            chained.filed = when

            prev = period_prev[key]
            if prev is None or chained.moved_here:
                # A transaction was reported in this class, so the period's
                # filings jointly state the whole of it.
                if prev is not None:
                    have = chained.vehicles()
                    for u, u_bal in prev.vehicles().items():
                        if not u_bal:
                            continue
                        # ONLY SILENCE BENCHES. v2 also benched a standing
                        # position when a namesake chain arrived at a
                        # different opening -- and every phantom of the next
                        # three rounds traced back to it: Stankey's 321,867
                        # on a day short minus nine, Roberts's 22.7 million,
                        # Ergen's round-trips. The one real repair credited
                        # to it (Foroughi's trusts) turned out, in the
                        # filings, to resolve through this original path --
                        # the chain benched when its name went missing,
                        # matched by arithmetic on return, corroborated by
                        # the gap. What a document does not mention may be
                        # riding along; what it displaces has been decided.
                        if u not in have:
                            # ONCE PER BALANCE, HOWEVER MANY FILINGS SAY SO.
                            # This block runs for every filing of a period,
                            # and Musk's November 2021 days carry several. A
                            # vehicle absent from a five-filing day was
                            # benched five times over -- five entries, one
                            # balance -- and every restatement after the
                            # first bridged a duplicate: his 1,220,481
                            # direct shares, counted twice onto days the old
                            # walk had reconciled to zero. The list exists so
                            # DIFFERENT balances can wait together; the same
                            # balance waits once, as the dict always had it.
                            slot = bench.setdefault(key, {}).setdefault(u, [])
                            if not any(abs(w[0] - u_bal) < 0.5 for w in slot):
                                slot.append((u_bal, when, len(hist.snapshots)))
                groups[key] = chained
            else:
                # Holdings only: no claim to the total. The named vehicles
                # update; the rest of the class stands.
                merged = copy.deepcopy(prev)
                _merge_same_day(merged, chained, newest_first=False)
                merged.filed = when
                groups[key] = merged

        if since and when < since:
            continue                 # read it, do not emit it

        # ONE SNAPSHOT PER DAY, NOT PER FILING.
        #
        # Zuckerberg files two Forms 4 for the same day and splits the
        # vehicles between them. On 6 February 2024 the first reports four
        # Class B vehicles totalling 51,507,297; the second reports all five,
        # 348,093,309, and says so in its remarks: "the Class A and Class B
        # holdings for CZI Holdings, LLC are reported on the second of these
        # two forms."
        #
        # Both settle exactly right. Emitting after each one produced a
        # snapshot mid-day that is true of one document and false of the
        # position -- 46 of his 763 points swung between the two figures.
        #
        # The day's LAST filing settles the day, which is the same rule the
        # panel uses for the newest filing overall.
        if i < len(ordered) and _period(ordered[i]) == when:
            continue

        total = sum(g.shares for g in groups.values())
        prev_total = (hist.snapshots[-1].shares if hist.snapshots else None)
        adj_total = splits.adjust(total, when) if splits else total
        prev_adj = (hist.snapshots[-1].adjusted if hist.snapshots else None)
        point = series.at(when) if series else None
        out = point.shares if point else None

        # THE DENOMINATOR MUST BE ON THE SAME SIDE OF A SPLIT AS THE
        # NUMERATOR.
        #
        # A Form 4 filed the day after a split reports post-split shares
        # immediately. The cover page does not: it is restated only at the
        # next 10-Q, which can be three months later. Dividing one by the
        # other multiplies the percentage by the split factor.
        #
        # Nvidia is the clean case. The 10-for-1 split settled 7 June 2024;
        # the next cover page landed at the end of August. Every filing in
        # between divided ~867 million post-split shares by 2.46 billion
        # pre-split ones -- 35.3% for a man who owns 3.5%. The same happened,
        # four-fold, after the July 2021 split.
        #
        # So the forward-filled count is carried forward THROUGH any splits
        # between the cover date and this filing. The point knows its own
        # as_of date, which is what makes this computable rather than
        # guessable.
        if out and splits and point and point.as_of != when:
            here = splits.factor_since(when)
            if here:
                out *= splits.factor_since(point.as_of) / here
        codes = sorted(day_codes.get(when, set()))
        hist.snapshots.append(Snapshot(
            date=when, form=f.get("form") or "", accession=acc,
            shares=total,
            adjusted=splits.adjust(total, when) if splits else total,
            outstanding=out,
            pct=(total / out * 100) if out else None,
            traded=day_traded.get(when, 0.0),
            traded_value=day_value.get(when),
            unpriced=day_unpriced.get(when, 0),
            # DOES THE BALANCE CHANGE HAVE A TRANSACTION BEHIND IT?
            #
            # A Form 4 states balances for the vehicles it names and says
            # nothing about the rest. Huang's filing of 6 January 2021 lists
            # three trusts holding 2,746,730 and reports NO transactions --
            # so 81% of his position left our number without a share
            # changing hands.
            #
            # The tell is arithmetic: a real trade moves the balance by
            # exactly what it transacted. When the balance moves and the
            # transaction rows do not account for it, the filing is partial
            # and the difference is a reporting artifact, not activity.
            # BOTH SIDES IN TODAY'S BASIS.
            #
            # Computed on reported shares, a split looks like the largest
            # unexplained acquisition in the file: Huang's 10-for-1 showed
            # 780,774,507 shares appearing from nowhere, which would brand
            # the genuine 240,000-share sale filed that day an artifact and
            # withhold it. The split-adjusted balances are on one basis, and
            # the day's trades are restated onto it.
            unexplained=((adj_total - prev_adj) - (splits.adjust(
                day_traded.get(when, 0.0), when) if splits
                else day_traded.get(when, 0.0))
                if prev_adj is not None else 0.0),
            codes="".join(codes),
            groups=len(groups),
            classes="|".join(sorted(members)) if members else ""))
    add_cover_points(hist, series, splits, since)
    return hist

