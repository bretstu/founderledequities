"""When an issuer's filing history lives under a different CIK.

ExxonMobil redomiciled from New Jersey to Texas on 1 July 2026. The new
entity, CIK 2115436, files 10-Qs -- we read a certification from one, naming
Darren Woods -- but has no Section 16 filings at all. Every Form 4 he has
ever filed sits under CIK 34088, and nothing in the submissions JSON has a
"predecessor" field.

THE LINK IS IN THE ACCESSION NUMBER. An accession is formed as
{transmitter}-{year}-{sequence}, and the new entity's 10-Q is

    0000034088-26-000093

-- transmitted by the predecessor. So the candidate is already in data we
fetch, with no list to maintain and no company names to compare.

BUT A TRANSMITTER IS NOT ALWAYS THE PREDECESSOR. Most of ExxonMobil Holdings'
filings carry 0001193125, which is a filing agent. So a candidate is never
trusted, only tested:

    does it have Section 16 filings, and is THIS company's certified chief
    executive among the people who filed them?

Point it at an agent and Darren Woods is not there, so it refuses. That gate
is what makes an inferred pointer safe, and it is the same reasoning that
governs everything else here: take the structural signal, then verify it
against a fact that cannot be coincidence.
"""
from __future__ import annotations

from dataclasses import dataclass

from .names import names_match


@dataclass
class Predecessor:
    cik: int | None = None
    name: str = ""
    matched_owner: str = ""
    considered: list = None
    note: str = ""

    def __post_init__(self):
        if self.considered is None:
            self.considered = []


def needs_predecessor(subs: dict) -> bool:
    """Does this issuer file periodic reports but no insider filings?

    EDGAR states it outright -- `insiderTransactionForIssuerExists` is 0 --
    which is better than counting Section 16 filings ourselves, because it is
    the filing system's own answer rather than our inference from a list we
    may have paged wrongly.
    """
    if subs.get("insiderTransactionForIssuerExists") not in (0, "0", False):
        return False
    forms = {f.get("form") for f in subs.get("_filings", [])}
    return bool(forms & {"10-K", "10-Q", "10-K/A", "10-Q/A"})


def candidates_from_accessions(subs: dict, self_cik: int) -> list[int]:
    """CIKs that transmitted this issuer's filings, most frequent last.

    Ordered by how FEW filings each transmitted. An agent files everything;
    a predecessor typically transmits one or two while the changeover
    settles, so the rare one is the likelier candidate -- and being wrong
    only costs a wasted check, since each is verified.
    """
    counts: dict = {}
    for f in subs.get("_filings", []):
        acc = f.get("accessionNumber") or ""
        head = acc.split("-")[0]
        if not head.isdigit():
            continue
        cik = int(head)
        if cik == int(self_cik):
            continue
        counts[cik] = counts.get(cik, 0) + 1
    return [cik for cik, _ in sorted(counts.items(), key=lambda kv: kv[1])]


def find_predecessor(client, self_cik: int, ceo_name: str,
                     subs: dict | None = None) -> Predecessor:
    """-> the CIK whose insiders include this company's chief executive."""
    from .ledger import SECTION16, _owners, _parse

    out = Predecessor()
    subs = subs or client.submissions(int(self_cik))
    if not needs_predecessor(subs):
        out.note = "this issuer has its own Section 16 filings"
        return out
    if not ceo_name:
        out.note = "no certified chief executive to verify a candidate against"
        return out

    for cik in candidates_from_accessions(subs, self_cik):
        try:
            other = client.submissions(cik)
        except Exception:  # noqa: BLE001
            continue
        s16 = [f for f in other.get("_filings", []) if f.get("form") in SECTION16]
        out.considered.append((cik, other.get("name") or "", len(s16)))
        if not s16:
            continue                    # a filing agent has none of its own

        # THE GATE. Being transmitted by someone proves nothing; having this
        # company's chief executive among your insiders is not coincidence.
        s16.sort(key=lambda f: (f.get("filingDate") or ""), reverse=True)
        threes = [f for f in s16 if (f.get("form") or "").startswith("3")]
        for f in (threes + s16)[:150]:
            root = _parse(client, cik, f)
            if root is None:
                continue
            for _c, name, _t, _o in _owners(root):
                if names_match(ceo_name, name) >= 0.7:
                    out.cik = cik
                    out.name = other.get("name") or ""
                    out.matched_owner = name
                    return out
    out.note = ("no transmitting CIK has Section 16 filings that include "
                f"{ceo_name}")
    return out
