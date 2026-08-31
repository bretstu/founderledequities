"""What a Schedule 13D or 13G says a person beneficially owns.

Anyone crossing 5% of a registered class must file one, and the cover page
carries the answer in FIELDS rather than prose: aggregate amount owned, and
percent of class. When the stake changes materially, they amend.

Ariel Emanuel is why this exists. His Form 4 lists 114 million TKO Class B
shares held by Endeavor's entities and disclaims them in a footnote; we read
the number and put him at 62.65%. On 24 March 2025 he filed Amendment No. 6
saying his shared voting power had gone to zero, that he holds 66,179 shares,
and that this is 0.1% of the class.

That is the same fact, stated in a structured field, by the same person.

TWO SCHEMAS FOR THE SAME TWO NUMBERS.

  13D   issuerCIK   aggregateAmountOwned                        percentOfClass
  13G   issuerCik   reportingPersonBeneficiallyOwnedAggregate…  classPercent

And 'SC 13D' became 'SCHEDULE 13D' on 18 December 2024, the day the XML
mandate took effect. Matching only the old strings hid twenty months of
filings -- including the amendment above.

WHAT THIS IS NOT.

Not a correction. A schedule is a snapshot at its event date and covers ONE
class, so it cannot replace a Form 4 ledger. It is a second opinion from the
same person, and where the two disagree by a wide margin the row needs a
human.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

# Both the pre-mandate and post-mandate names.
SCHEDULES = ("SC 13D", "SC 13G", "SCHEDULE 13D", "SCHEDULE 13G")

ISSUER = ("issuerCIK", "issuerCik")
AGGREGATE = ("aggregateAmountOwned",
             "reportingPersonBeneficiallyOwnedAggregateNumberOfShares")
PERCENT = ("percentOfClass", "classPercent")


@dataclass
class Block:
    """One reporting person's cover page, from one schedule."""
    form: str = ""
    filed: str = ""
    accession: str = ""
    event: str = ""
    person_cik: str = ""
    person_name: str = ""
    security: str = ""
    shares: float | None = None
    pct: float | None = None
    sole_voting: float | None = None
    shared_voting: float | None = None
    ceased: str = ""              # the "ceased to be a 5% owner" statement

    @property
    def url(self) -> str:
        return self.accession


def _tag(node) -> str:
    return node.tag.split("}")[-1]


def _num(text):
    try:
        return float((text or "").replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _parents(root) -> dict:
    return {child: parent for parent in root.iter() for child in parent}


def read_schedule(raw: str, issuer_cik: int) -> list[Block]:
    """Every reporting person on this schedule, if it is about this issuer.

    A filing carries several person blocks -- Emanuel's Endeavor amendment
    has five -- so each is read separately. And Emanuel filed two amendments
    on the same day about DIFFERENT issuers, so the issuer is checked first.
    """
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []

    got = ""
    for node in root.iter():
        if _tag(node) in ISSUER and (node.text or "").strip():
            got = (node.text or "").strip()
            break
    if got and got.isdigit() and int(got) != int(issuer_cik):
        return []

    # Values that sit outside any person block, shared by all of them.
    shared: dict = {}
    for node in root.iter():
        t = _tag(node)
        if t in ("securitiesClassTitle", "securityTitle", "dateOfEvent",
                 "eventDateRequiresFilingThisStatement", "date5PercentOwnership",
                 "submissionType"):
            shared.setdefault(t, " ".join((node.text or "").split()))

    parents = _parents(root)
    out: list[Block] = []
    seen: set = set()
    for node in root.iter():
        if _tag(node) != "reportingPersonName":
            continue
        holder = parents.get(node)
        if holder is None or holder in seen:
            continue
        seen.add(holder)
        b = Block(
            form=shared.get("submissionType", ""),
            event=shared.get("dateOfEvent")
            or shared.get("eventDateRequiresFilingThisStatement", ""),
            security=shared.get("securitiesClassTitle")
            or shared.get("securityTitle", ""),
            ceased=shared.get("date5PercentOwnership", ""),
            person_name=" ".join((node.text or "").split()))
        for kid in holder.iter():
            t, v = _tag(kid), (kid.text or "").strip()
            if not v:
                continue
            if t == "reportingPersonCIK":
                b.person_cik = v.lstrip("0")
            elif t in AGGREGATE:
                b.shares = _num(v)
            elif t in PERCENT:
                b.pct = _num(v)
            elif t == "soleVotingPower":
                b.sole_voting = _num(v)
            elif t == "sharedVotingPower":
                b.shared_voting = _num(v)
        if b.shares is not None or b.pct is not None:
            out.append(b)
    return out


def all_for_person(client, issuer_cik: int, person_cik: str,
                   limit: int = 25, on_step=None) -> list:
    """Every XML schedule naming this person for this issuer, newest first."""
    if not person_cik:
        return []
    subs = client.submissions(int(issuer_cik))
    sched = [f for f in subs.get("_filings", [])
             if (f.get("form") or "").upper().startswith("SCHEDULE 13")]
    sched.sort(key=lambda f: (f.get("filingDate") or ""), reverse=True)

    out = []
    for n, f in enumerate(sched[:limit], 1):
        if on_step:
            on_step(n, min(len(sched), limit))
        acc = f.get("accessionNumber") or ""
        try:
            idx = client.filing_index(int(issuer_cik), acc)
            items = idx.get("directory", {}).get("item", [])
            name = next((i["name"] for i in items
                         if (i.get("name") or "").lower().endswith(".xml")), None)
            if not name:
                continue
            raw = client.primary_document(int(issuer_cik), acc, name)
        except Exception:  # noqa: BLE001
            continue
        for b in read_schedule(raw, issuer_cik):
            if b.person_cik and b.person_cik == str(person_cik).lstrip("0"):
                b.filed = f.get("filingDate") or ""
                b.accession = acc
                b.form = b.form or (f.get("form") or "")
                out.append(b)
    return out


def newest_for_person(client, issuer_cik: int, person_cik: str,
                      limit: int = 25, on_step=None) -> Block | None:
    """The most recent schedule naming this person for this issuer.

    ONLY THE XML ERA. 'SC 13D' filings predate the December 2024 mandate and
    are HTML with nothing structured to read, so fetching them costs two
    requests to learn there is no payload. Airbnb has 39 schedules and its
    chief executive is in none, which meant 78 requests to find that out.
    """
    if not person_cik:
        return None
    subs = client.submissions(int(issuer_cik))
    sched = [f for f in subs.get("_filings", [])
             if (f.get("form") or "").upper().startswith("SCHEDULE 13")]
    sched.sort(key=lambda f: (f.get("filingDate") or ""), reverse=True)

    for n, f in enumerate(sched[:limit], 1):
        if on_step:
            on_step(n, min(len(sched), limit))
        acc = f.get("accessionNumber") or ""
        try:
            idx = client.filing_index(int(issuer_cik), acc)
            items = idx.get("directory", {}).get("item", [])
            name = next((i["name"] for i in items
                         if (i.get("name") or "").lower().endswith(".xml")), None)
            if not name:
                continue          # pre-mandate HTML; nothing structured to read
            raw = client.primary_document(int(issuer_cik), acc, name)
        except Exception:  # noqa: BLE001
            continue
        for b in read_schedule(raw, issuer_cik):
            if b.person_cik and b.person_cik == str(person_cik).lstrip("0"):
                b.filed = f.get("filingDate") or ""
                b.accession = acc
                b.form = b.form or (f.get("form") or "")
                return b
    return None
