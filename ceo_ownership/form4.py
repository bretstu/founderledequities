"""Form 3/4/5 ownership XML -- the independent second path to the same number.

Form 4 splits holdings across two tables:
  Table I  (nonDerivativeTable) -- common stock actually held
  Table II (derivativeTable)    -- options, RSUs, warrants, exchangeable units

Because an exercise is reported as a PAIRED transaction (code M disposing of
the derivative in Table II and simultaneously acquiring the underlying in
Table I), anything exercised, vested, settled or converted has already moved
into Table I. Reading Table I alone therefore captures all realised ownership
and none of the contingent kind -- exactly the project's metric, with no
footnote parsing required.

This gives a genuinely independent check on the proxy: different document,
different filer (the individual, not the company), different filing system.

Two traps handled here:
  * Cashless exercises land and leave the same day, so the last transaction
    by (date, sequence) is the true end-of-day balance, not the first.
  * Some filers put RSUs in Table I. securityTitle is matched against an
    allowlist, and anything unrecognised is logged and excluded.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from xml.etree import ElementTree as ET

from .config import COMMON_STOCK_PATTERNS, CONTINGENT_PATTERNS, UPC_PATTERNS
from .edgar import EdgarClient


def _name_tokens(raw: str) -> list[str]:
    import re as _re
    n = _re.sub(r"[^A-Za-z,\s'\-]", " ", raw or "")
    if "," in n:
        last, _, rest = n.partition(",")
        n = f"{rest} {last}"
    toks = [t.strip(".'-").lower() for t in n.split()]
    return [t for t in toks if len(t) > 1 and t not in
            {"jr", "sr", "ii", "iii", "iv", "phd", "md", "cpa", "esq"}]

CEO_TERM_RE = re.compile(
    r"\b(chief\s+exec\w*\s+officer|c\.?\s?e\.?\s?o\.?)\b", re.I
)
# Titles a company CEO may ALSO hold. Anything left over after removing these
# means the CEO-ship is qualified -- i.e. divisional.
CO_TITLE_RE = re.compile(
    r"\b(co|chairman|chairwoman|chairperson|chair|cob|president|pres|director|"
    r"founder|co-?founder|principal|executive|exec|officer|and|the|of|"
    r"member|board|interim|acting)\b",
    re.I,
)
SEGMENT_SPLIT_RE = re.compile(r"[,;/&]|\band\b", re.I)
CORP_SUFFIX_RE = re.compile(
    r"\b(inc|corp|corporation|company|co|ltd|limited|llc|lp|plc|holdings?|"
    r"group|nv|sa|ag)\b\.?", re.I,
)


def ceo_title_score(title: str | None) -> int:
    """How confident are we that this person is the COMPANY's chief executive?

    100  unqualified company CEO ("Chief Executive Officer", "COB and CEO",
         "President and Chief Executive Officer, Director")
     90  explicitly a co-CEO of the company
     40  divisional CEO ("CEO, Commercial Business", "CEO Walmart U.S.",
         "co-CEO Commercial & Investment Bank") -- a real officer, but NOT
         the person this dataset is about
      0  no CEO term at all

    This exists because matching any title containing "CEO" picked Microsoft's
    CEO of Commercial Business over Satya Nadella, and JPMorgan's co-CEO of
    the Commercial & Investment Bank over Jamie Dimon. Both produced
    confident, plausible-looking, wrong rows.
    """
    if not title:
        return 0

    def leftover(seg: str) -> str:
        r = CEO_TERM_RE.sub(" ", seg)
        r = CO_TITLE_RE.sub(" ", r)
        return re.sub(r"[^a-z]", " ", r, flags=re.I).strip()

    segments = [x.strip() for x in SEGMENT_SPLIT_RE.split(title)]
    segments = [x for x in segments if x]

    best = 0
    for i, seg in enumerate(segments):
        if not CEO_TERM_RE.search(seg):
            continue
        qualifier = leftover(seg)

        # "CEO, Commercial Business" splits into a CLEAN "CEO" segment, so the
        # qualifier lives in the NEXT segment. Check it -- unless it is just
        # the company's own name ("CEO, Acme Corporation"), which qualifies
        # nothing.
        if not qualifier and i + 1 < len(segments):
            nxt = segments[i + 1]
            if not CORP_SUFFIX_RE.search(nxt):
                nxt_left = leftover(nxt)
                if nxt_left and len(nxt_left.split()) <= 5:
                    qualifier = nxt_left

        if qualifier:
            score = 40  # divisional / qualified
        elif re.search(r"\bco[\s-]?ceo\b|\bco[\s-]chief", seg, re.I):
            score = 90
        else:
            score = 100
        best = max(best, score)
    return best


@dataclass
class Form4Holding:
    security_title: str
    shares_following: float | None
    direct_or_indirect: str | None
    nature_of_ownership: str | None = None
    counted: bool = False
    exclusion_reason: str | None = None


@dataclass
class Form4Record:
    accession: str
    filing_date: str
    period: str | None
    owner_name: str
    owner_cik: str | None
    officer_title: str | None
    is_officer: bool
    is_director: bool
    common_shares: float = 0.0            # Table I common
    derivative_common_shares: float = 0.0  # Table II convertible common (Class B)
    holdings: list[Form4Holding] = field(default_factory=list)
    derivative_holdings: list[Form4Holding] = field(default_factory=list)
    derivative_titles: list[str] = field(default_factory=list)
    has_exchangeable_units: bool = False
    has_convertible_common: bool = False
    co_ceo_detected: bool = False
    rejected_as_divisional: bool = False
    matched_peo_name: str | None = None
    unknown_titles: list[str] = field(default_factory=list)

    @property
    def total_common(self) -> float:
        """All real common stock: Table I plus convertible classes in Table II.

        Dual-class issuers report the super-voting class (typically Class B)
        as a DERIVATIVE, because it converts into Class A. It is nonetheless
        ordinary ownership -- not contingent compensation -- and excluding it
        understates founder-CEOs by orders of magnitude. Zuckerberg shows
        1.2M Class A in Table I and ~350M Class B in Table II.
        """
        return self.common_shares + self.derivative_common_shares

    @property
    def ceo_score(self) -> int:
        return ceo_title_score(self.officer_title)

    @property
    def looks_like_ceo(self) -> bool:
        return self.ceo_score >= 90

    def as_dict(self) -> dict:
        return asdict(self)


def classify_security(title: str) -> tuple[str, str | None]:
    """-> ('common' | 'contingent' | 'upc' | 'unknown', reason)."""
    t = (title or "").strip().lower()
    t = re.sub(r"\s+", " ", t)

    for pat in CONTINGENT_PATTERNS:
        if re.search(pat, t):
            return "contingent", f"matched contingent pattern {pat!r}"
    for pat in UPC_PATTERNS:
        if re.search(pat, t):
            return "upc", f"matched exchangeable-unit pattern {pat!r}"
    for pat in COMMON_STOCK_PATTERNS:
        if re.match(pat, t):
            return "common", None
    return "unknown", f"unrecognised securityTitle {title!r}"


def _txt(node, path: str) -> str | None:
    el = node.find(path)
    if el is None:
        return None
    val = el.find("value")
    target = val if val is not None else el
    return (target.text or "").strip() or None


def _num(node, path: str) -> float | None:
    raw = _txt(node, path)
    if raw is None:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", raw)
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_ownership_xml(xml_text: str, accession: str, filing_date: str) -> Form4Record:
    root = ET.fromstring(xml_text)

    owner = root.find("reportingOwner")
    owner_name = owner_cik = officer_title = None
    is_officer = is_director = False
    if owner is not None:
        owner_name = _txt(owner, "reportingOwnerId/rptOwnerName")
        owner_cik = _txt(owner, "reportingOwnerId/rptOwnerCik")
        rel = owner.find("reportingOwnerRelationship")
        if rel is not None:
            officer_title = _txt(rel, "officerTitle")
            is_officer = (_txt(rel, "isOfficer") or "0") in ("1", "true")
            is_director = (_txt(rel, "isDirector") or "0") in ("1", "true")

    rec = Form4Record(
        accession=accession,
        filing_date=filing_date,
        period=_txt(root, "periodOfReport"),
        owner_name=owner_name or "",
        owner_cik=owner_cik,
        officer_title=officer_title,
        is_officer=is_officer,
        is_director=is_director,
    )

    # ---- Table I: non-derivative holdings ------------------------------
    # Sum the LAST reported balance per (securityTitle, direct/indirect) line.
    # Document order is chronological, so later entries supersede earlier ones
    # -- which is what makes same-day cashless exercises resolve correctly.
    lines: dict[tuple, Form4Holding] = {}
    nd = root.find("nonDerivativeTable")
    if nd is not None:
        for node in list(nd.findall("nonDerivativeTransaction")) + list(
            nd.findall("nonDerivativeHolding")
        ):
            title = _txt(node, "securityTitle") or ""
            shares = _num(node, "postTransactionAmounts/sharesOwnedFollowingTransaction")
            d_or_i = _txt(node, "ownershipNature/directOrIndirectOwnership")
            nature = _txt(node, "ownershipNature/natureOfOwnership")
            kind, reason = classify_security(title)

            holding = Form4Holding(
                security_title=title,
                shares_following=shares,
                direct_or_indirect=d_or_i,
                nature_of_ownership=nature,
                counted=(kind == "common"),
                exclusion_reason=None if kind == "common" else reason,
            )
            if kind == "unknown":
                rec.unknown_titles.append(title)
            if kind == "upc":
                rec.has_exchangeable_units = True
            lines[(title.lower(), d_or_i, nature)] = holding

    rec.holdings = list(lines.values())
    rec.common_shares = sum(
        h.shares_following or 0.0 for h in rec.holdings if h.counted
    )

    # ---- Table II: options and RSUs are excluded, but a convertible
    # class of COMMON stock is genuine ownership and must be counted.
    dv = root.find("derivativeTable")
    dlines: dict[tuple, Form4Holding] = {}
    if dv is not None:
        for node in list(dv.findall("derivativeTransaction")) + list(
            dv.findall("derivativeHolding")
        ):
            title = _txt(node, "securityTitle") or ""
            rec.derivative_titles.append(title)
            kind, reason = classify_security(title)
            if kind == "upc":
                rec.has_exchangeable_units = True
            if kind != "common":
                continue

            # A common-stock class sitting in Table II == convertible class.
            shares = _num(
                node, "postTransactionAmounts/sharesOwnedFollowingTransaction"
            )
            if shares is None:
                shares = _num(node, "underlyingSecurity/underlyingSecurityShares")
            d_or_i = _txt(node, "ownershipNature/directOrIndirectOwnership")
            nature = _txt(node, "ownershipNature/natureOfOwnership")
            rec.has_convertible_common = True
            dlines[(title.lower(), d_or_i, nature)] = Form4Holding(
                security_title=title,
                shares_following=shares,
                direct_or_indirect=d_or_i,
                nature_of_ownership=nature,
                counted=True,
                exclusion_reason=None,
            )

    rec.derivative_holdings = list(dlines.values())
    rec.derivative_common_shares = sum(
        h.shares_following or 0.0 for h in rec.derivative_holdings
    )
    return rec


def filing_for_person(
    client: EdgarClient,
    issuer_cik: int,
    candidate_names: list[str],
    before: str | None = None,
    max_filings: int = 250,
) -> "Form4Record | None":
    """Find the Section 16 filing belonging to one of `candidate_names`.

    Preferred over title matching: the names come from the proxy's tagged
    ecd:PeoName facts, so "principal executive officer" is settled by the
    filing itself and divisional CEOs cannot be confused for the real one.
    """
    from .validate import names_match  # local import avoids a cycle

    if not candidate_names:
        return None

    subs = client.submissions(issuer_cik)
    filings = [
        f for f in subs.get("_filings", [])
        if f.get("form") in ("3", "4", "5", "4/A", "3/A", "5/A")
        and (before is None or f.get("filingDate", "") <= before)
    ]
    filings.sort(key=lambda f: f.get("filingDate", ""), reverse=True)

    # Candidate order encodes source priority: the Section 302 signature comes
    # first because it is current and quarterly, while a proxy's tagged PEO is
    # retrospective by up to a fiscal year. At Walmart both are correct for
    # their own period -- Furner succeeded McMillon -- and taking whichever
    # filing appeared first picked the outgoing CEO.
    best: tuple[int, Form4Record] | None = None

    for f in filings[:max_filings]:
        rec = _load_record(client, issuer_cik, f)
        if rec is None or not rec.owner_name:
            continue
        for rank, cand in enumerate(candidate_names):
            if names_match(rec.owner_name, cand) >= 0.7:
                rec.matched_peo_name = cand
                if rank == 0:
                    return rec          # top-priority name: done
                if best is None or rank < best[0]:
                    best = (rank, rec)
                break

    return best[1] if best else None


def _load_record(client: EdgarClient, issuer_cik: int, f: dict):
    """Fetch and parse one ownership filing, or None."""
    acc = f["accessionNumber"]
    xml_name = f.get("primaryDocument", "")
    # For ownership forms, primaryDocument is the XSL-RENDERED document, e.g.
    # "xslF345X05/wf-form4_123.xml". That path serves HTML, not XML. The raw
    # ownership XML sits at the same basename in the filing root.
    if "/" in xml_name:
        xml_name = xml_name.rsplit("/", 1)[-1]
    if not xml_name.endswith(".xml"):
        try:
            index = client.filing_index(issuer_cik, acc)
        except Exception:  # noqa: BLE001
            return None
        xml_name = next(
            (item["name"] for item in index.get("directory", {}).get("item", [])
             if item["name"].endswith(".xml")
             and not item["name"].endswith("_slug.xml")),
            "",
        )
    if not xml_name:
        return None
    try:
        xml = client.primary_document(issuer_cik, acc, xml_name)
        return parse_ownership_xml(xml, acc, f.get("filingDate", ""))
    except Exception:  # noqa: BLE001
        return None


def latest_ceo_filing(
    client: EdgarClient,
    issuer_cik: int,
    before: str | None = None,
    max_filings: int = 250,
) -> Form4Record | None:
    """Most recent Form 3/4/5 filed by the company's chief executive.

    Depth matters: a 40-filing window missed Walmart's CEO entirely, because
    large issuers have dozens of Section 16 filers and the CEO may not have
    traded recently. Every CEO files a Form 3 within ten days of appointment,
    so the record always exists -- you just have to look far enough back.

    Divisional CEOs are rejected outright rather than accepted as a fallback.
    Microsoft's CEO of Commercial Business and JPMorgan's co-CEO of the
    Commercial & Investment Bank both scored a confident, wrong row before
    this check existed.
    """
    subs = client.submissions(issuer_cik)
    filings = [
        f
        for f in subs.get("_filings", [])
        if f.get("form") in ("3", "4", "5", "4/A", "3/A", "5/A")
        and (before is None or f.get("filingDate", "") <= before)
    ]
    filings.sort(key=lambda f: f.get("filingDate", ""), reverse=True)

    best: Form4Record | None = None
    divisional: Form4Record | None = None
    seen_owners: set[str] = set()

    for f in filings[:max_filings]:
        acc = f["accessionNumber"]

        # primaryDocument is the XSL-rendered path ("xslF345X05/...xml"),
        # which serves HTML. Strip the directory to reach the raw XML.
        xml_name = f.get("primaryDocument", "")
        if "/" in xml_name:
            xml_name = xml_name.rsplit("/", 1)[-1]
        if not xml_name.endswith(".xml"):
            try:
                index = client.filing_index(issuer_cik, acc)
            except Exception:  # noqa: BLE001
                continue
            xml_name = next(
                (
                    item["name"]
                    for item in index.get("directory", {}).get("item", [])
                    if item["name"].endswith(".xml")
                    and not item["name"].endswith("_slug.xml")
                ),
                "",
            )
        if not xml_name:
            continue

        try:
            xml = client.primary_document(issuer_cik, acc, xml_name)
            rec = parse_ownership_xml(xml, acc, f.get("filingDate", ""))
        except Exception:  # noqa: BLE001
            continue

        score = rec.ceo_score
        if score >= 90:
            if best is None:
                best = rec
            if rec.owner_cik:
                seen_owners.add(rec.owner_cik)
            # Co-CEO: keep scanning briefly to detect a second one, then stop.
            if score == 100 and len(seen_owners) <= 1:
                return best
        elif score == 40 and divisional is None:
            divisional = rec

    if best is not None:
        if len(seen_owners) > 1:
            best.co_ceo_detected = True
        return best
    if divisional is not None:
        # Deliberately NOT returned as the CEO. Surfaced so the caller can say
        # why nothing was found instead of reporting a plausible wrong person.
        divisional.rejected_as_divisional = True
        return None
    return None
