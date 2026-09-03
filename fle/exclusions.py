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

THE SAME FILE RUNS THE OTHER WAY.

Musk's SpaceX Forms 3 and 4 both state, in a remark, that 1,302,072,285
restricted Class B shares "issued to and held of record by the Reporting
Person" are not in their tables -- shares the prospectus counts as
outstanding. The tables under-report; a sentence says by how much. No regex
or model turns that sentence into a number here. A person reads it once and
records the number in this file, with the filing as source, as an ADDITION:
an entry with a `shares` column. The panel adds it after the walk, labels
the row's source `manual`, keeps the tables' figure beside it, and writes
the receipt into the row's cautions. An addition lapses on its own the day
the newest filing stops carrying a remark (see panel.apply_additions), so
a hand-recorded number can never outlive its source.

RULES FOR ENTRIES.

  - a source URL is required. Not "we decided" but "the proxy says".
  - the panel reports every entry applied; nothing is silently adjusted.
  - an entry names ONE class at ONE company. It cannot affect anything else.
  - an exclusion (no `shares`) does not expire: the filing will not change.
  - an addition (`shares` set) applies only while the newest filing carries
    a remark, and says so on the row when it lapses.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT = "universe/exclusions.csv"

COLUMNS = ["cik", "ticker", "security", "direct", "reason", "source", "shares", "owner_cik", "since"]


@dataclass(frozen=True)
class Exclusion:
    cik: str
    ticker: str
    security: str                  # the class, as the ledger labels it
    direct: str = ""               # "D", "I", or blank for both
    reason: str = ""
    source: str = ""
    shares: float | None = None    # set: an ADDITION the tables leave out; unset: an exclusion
    owner_cik: str = ""            # an addition belongs to a PERSON; it applies only to that owner's row
    since: str = ""                # an addition applies from this date (the filing that stated it)

    @property
    def is_addition(self) -> bool:
        return self.shares is not None

    def matches(self, security: str, direct: str) -> bool:
        if self.security.strip().lower() != (security or "").strip().lower():
            return False
        return not self.direct or self.direct.upper() == (direct or "").upper()


@dataclass
class Exclusions:
    by_cik: dict = field(default_factory=dict)
    path: str = ""

    def for_issuer(self, cik) -> list:
        """The exclusions for an issuer -- what the walk removes."""
        return [e for e in self.by_cik.get(str(int(cik)), []) if not e.is_addition]

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
                if not re.match(r"\d{4}-\d{2}-\d{2}$", (row.get("since") or "").strip()):
                    raise ValueError(f"{p}: {row.get('ticker') or cik} adds shares without a since date (the filing that stated them)")
            out.by_cik.setdefault(str(int(cik)), []).append(Exclusion(
                cik=str(int(cik)),
                ticker=(row.get("ticker") or "").strip().upper(),
                security=(row.get("security") or "").strip(),
                direct=(row.get("direct") or "").strip().upper(),
                reason=(row.get("reason") or "").strip(),
                source=src, shares=shares,
                owner_cik=str(int(row.get("owner_cik"))) if shares is not None else "",
                since=(row.get("since") or "").strip()))
    return out
