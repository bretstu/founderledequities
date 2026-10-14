"""Holdings a filing reports that the company itself says are not the
chief executive's.

WHY THIS EXISTS.

Ariel Emanuel's February 2025 Form 4 lists 114 million TKO Class B shares
held by Endeavor's entities, and in the same footnote disclaims them: he sits
on Endeavor's governing body, so the rules deem him to share ownership, and
he says plainly that the shares are not his. TKO's own proxy agrees --
143,850 Class A, zero Class B, under one per cent.

We read the number and not the sentence beside it, and reported him at
62.65%: the second largest founder stake in the index, and wrong.

WHY THERE IS NO RULE FOR IT.

Every structured field is identical whether shares are yours or merely
attributed to you. Musk's trust holds 413 million and it is his; Endeavor's
entities hold 114 million and it is not. The rows look the same. The only
difference is a sentence of boilerplate.

Schedule 13D was the last structural idea and it failed on the case it was
built for -- Emanuel HAS 13Ds for TKO -- while missing Lachlan Murdoch, whose
Fox stake sits in a family trust that files separately. It flagged the honest
and cleared the attributed.

WHAT THIS IS INSTEAD.

The same thing S&P Global does, which is what Simply Wall St resells: a
person reads the filing and records the decision. Smaller, and more honest,
because the reasoning is written down where it can be checked.

THE SAME FILE RUNS THE OTHER WAY: SUPPLEMENTS.

Musk's SpaceX Forms 3 and 4 both state, in a remark, that 1,302,072,285
restricted Class B shares "issued to and held of record by the Reporting
Person" are not in their tables -- shares the prospectus counts as
outstanding. The tables under-report; a sentence says by how much. No regex
or model turns that sentence into a number here. A person reads it once and
records the number in this file, with the filing as source, as a SUPPLEMENT:
an entry with a `shares` column and the owner's CIK. The walk then treats
every one of that owner's filings that still states the figure in its
remark AS IF the filer had written one more table line: the class, held
directly, that many shares. Every stage downstream -- the panel, the
history, the events, the split adjustments -- inherits it the way it
would a real line. The row is labelled `manual` and carries the receipt.

It stops on its own. A filing whose remark no longer states the figure
gets no line (a vested tranche, a typo, a change of position); a filing
whose tables already report the class held directly gets no line (the
tables win); and a filing by anyone else gets nothing (a successor does
not inherit). No prose is interpreted: the rule matches a recorded digit
string, it never extracts one.

RULES FOR ENTRIES.

  - a source URL is required. Not "we decided" but "the proxy says".
  - the panel reports every entry applied; nothing is silently adjusted.
  - an entry names ONE class at ONE company. It cannot affect anything else.
  - an exclusion (no `shares`) does not expire: the filing will not change.
  - a COUNTED DERIVATIVE (`ratio` set, above 0) counts the Table II rows
    titled `security` as shares of the class they convert into, at that
    ratio (2026-10-14, Rocket Lab). Peter Beck's trust exchanged 50,951,250
    common for a Series A Convertible Participating Preferred that converts
    one for one at his option, votes as common and takes dividends as
    common; the walk leaves every "preferred" in Table II out, because the
    usual one is a pre-IPO preferred that converted at the listing and
    lingers in an old Form 3, and the balance field cannot tell that relic
    from a live instrument (AMC's units were converted in 2023 and never
    restated). A person reads the terms once and records them; the walk
    then reads those rows as lines of the underlying class, so the chain,
    the history, the events and the page all carry them. The nightly names
    every live preferred it is NOT counting (ownership.py), so the next one
    is seen the week it is filed.
  - a FRACTION (`fraction` set, between 0 and 1) counts that share of the
    line instead of removing it (2026-10-14). Venture Global's Class B is
    held by Venture Global Partners II, LLC, which the Department of Energy's
    change-in-control notice states is "50% owned and controlled by each of
    the two Principals" (Sabel and Pender); the SEC filings attribute the
    whole block to each founder, as shared control requires, and state no
    split. Half the line is Sabel's pecuniary interest. The source carries
    the split; the row ages like any other and is reviewed by hand.
  - a supplement (`shares` set) is injected only into filings by the named
    owner whose remark still states the figure and whose tables do not
    already report the class held directly.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT = "universe/exclusions.csv"

COLUMNS = ["cik", "ticker", "security", "direct", "reason", "source", "shares", "owner_cik", "since", "vehicle", "decided", "fraction", "ratio"]


def class_key(security: str) -> str:
    """A security title reduced to what names the class."""
    t = (security or "").lower()
    t = re.sub(r"\(the company's only class\)", " ", t)
    t = re.sub(r",?\s*(\$?[0-9.]+\s*)?par value(\s*per share)?", " ", t)
    t = re.sub(r"\bshares\b", "stock", t)
    t = re.sub(r"[^a-z0-9]+", " ", t).strip()
    return t


@dataclass(frozen=True)
class Exclusion:
    cik: str
    ticker: str
    security: str                  # the class, as the ledger labels it
    direct: str = ""               # "D", "I", or blank for both
    reason: str = ""
    source: str = ""
    shares: float | None = None    # set: a SUPPLEMENT the tables leave out; unset: an exclusion
    owner_cik: str = ""            # a supplement belongs to a PERSON; only that owner's filings get it
    since: str = ""                # informational: the filing that first stated it
    # ONE VEHICLE, NOT A CLASS (2026-09-19, phase two of the footnote reader).
    # The nature text of the line to remove, as the filing writes it ("By
    # Chan Zuckerberg Biohub, Inc."); matched by the ledger's own vehicle
    # key (case, punctuation and a leading "By" folded, then exact). Blank
    # means the whole class-and-direction, as before (TKO).
    vehicle: str = ""
    decided: str = ""              # blank for a hand row; "reader YYYY-MM-DD" for a row the decisions file produced
    fraction: float | None = None  # set: the share of the line that is the person's (a co-owned vehicle); unset: the whole line goes
    ratio: float | None = None     # set: Table II rows titled `security` are counted as shares of their underlying class, at this ratio

    @property
    def is_counted(self) -> bool:
        return self.ratio is not None

    @property
    def is_addition(self) -> bool:
        return self.shares is not None

    def same_class(self, security: str) -> bool:
        """The class match, by meaning (2026-09-20): the ledger labels a
        single-class company "Common Stock (the company's only class)" while
        a register row carries the filing's title ("Common Stock, $.001 par
        value", "Common Shares"); the parenthetical, the par-value clause and
        shares/stock are not differences."""
        return class_key(self.security) == class_key(security)

    def matches(self, security: str, direct: str) -> bool:
        """The class-and-direction match (a whole-class row). A vehicle row
        needs the line: see matches_line."""
        if not self.same_class(security):
            return False
        return not self.direct or self.direct.upper() == (direct or "").upper()

    def matches_line(self, security: str, direct: str, nature: str | None) -> bool:
        """Whether this row removes the given line. A whole-class row: the
        class and the direction. A vehicle row: the class and the vehicle's
        canonical text; the direction is not consulted, since filers put a
        named trust in the direct column as often as the indirect one (AAOI,
        Urban Outfitters) and the text is the identity."""
        if not self.vehicle:
            return self.matches(security, direct)
        if not self.same_class(security):
            return False
        from .ledger import vehicle_key   # local: ledger imports this module
        return vehicle_key(direct, nature)[1].split("#", 1)[0] == vehicle_key(direct, self.vehicle)[1]


@dataclass
class Exclusions:
    by_cik: dict = field(default_factory=dict)
    path: str = ""

    def for_issuer(self, cik) -> list:
        """Every entry for an issuer: exclusions (what the walk removes) and
        supplements (what the walk injects); each stage picks its kind."""
        return list(self.by_cik.get(str(int(cik)), []))

    def additions_for(self, ticker: str) -> list:
        """The additions for a ticker -- what the panel adds after the walk."""
        t = (ticker or "").strip().upper()
        return [e for es in self.by_cik.values() for e in es if e.is_addition and e.ticker == t]

    def __bool__(self) -> bool:
        return bool(self.by_cik)


def read_exclusions(path: str | None = None) -> Exclusions:
    """Load the list, or an empty one if there is no file."""
    p = Path(path or DEFAULT)
    out = Exclusions(path=str(p))
    if not p.exists():
        return out
    with p.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            cik = (row.get("cik") or "").strip()
            if not cik.isdigit():
                continue
            src = (row.get("source") or "").strip()
            if not src:
                # A source is the whole point. An entry without one is a
                # guess with a CSV around it.
                raise ValueError(
                    f"{p}: {row.get('ticker') or cik} has no source URL")
            shares = None
            raw = (row.get("shares") or "").strip().replace(",", "")
            if raw:
                try:
                    shares = float(raw)
                except ValueError:
                    raise ValueError(f"{p}: {row.get('ticker') or cik} has a non-numeric shares value {raw!r}")
                if not (row.get("reason") or "").strip():
                    # an addition's reason IS the sentence it came from
                    raise ValueError(f"{p}: {row.get('ticker') or cik} adds shares without quoting the filing")
                if not (row.get("owner_cik") or "").strip().isdigit():
                    # a PERSON holds the shares; a new chief executive must not inherit them
                    raise ValueError(f"{p}: {row.get('ticker') or cik} adds shares without the owner's CIK")

            fraction = None
            rawf = (row.get("fraction") or "").strip()
            if rawf:
                try:
                    fraction = float(rawf)
                except ValueError:
                    raise ValueError(f"{p}: {row.get('ticker') or cik} has a non-numeric fraction {rawf!r}")
                if not (0 < fraction < 1):
                    raise ValueError(f"{p}: {row.get('ticker') or cik} has a fraction outside (0, 1): {rawf!r}; a whole line is an exclusion, not a fraction")
                if shares is not None:
                    raise ValueError(f"{p}: {row.get('ticker') or cik} sets both shares and fraction; a supplement is whole")
            ratio = None
            rawr = (row.get("ratio") or "").strip()
            if rawr:
                try:
                    ratio = float(rawr)
                except ValueError:
                    raise ValueError(f"{p}: {row.get('ticker') or cik} has a non-numeric ratio {rawr!r}")
                if ratio <= 0:
                    raise ValueError(f"{p}: {row.get('ticker') or cik} has a ratio at or below zero: {rawr!r}")
                if shares is not None or fraction is not None:
                    raise ValueError(f"{p}: {row.get('ticker') or cik} sets ratio beside shares or fraction; a counted derivative is its own kind of row")
            out.by_cik.setdefault(str(int(cik)), []).append(Exclusion(
                cik=str(int(cik)),
                ticker=(row.get("ticker") or "").strip().upper(),
                security=(row.get("security") or "").strip(),
                direct=(row.get("direct") or "").strip().upper(),
                reason=(row.get("reason") or "").strip(),
                source=src, shares=shares,
                owner_cik=str(int(row.get("owner_cik"))) if shares is not None else "",
                since=(row.get("since") or "").strip(),
                vehicle=(row.get("vehicle") or "").strip(),
                decided=(row.get("decided") or "").strip(),
                fraction=fraction, ratio=ratio))
    return out


def figure_stated(text: str, n: float) -> bool:
    """Is the recorded figure asserted in the text? Commas, spaces and thin
    spaces between digits are ignored; the match must be a whole number,
    not a substring of a longer one. String matching, never interpretation."""
    if not text:
        return False
    flat = re.sub(r"(?<=\d)[,\s\u202f\u00a0](?=\d)", "", text)
    return re.search(rf"(?<!\d){int(n)}(?!\d)", flat) is not None
