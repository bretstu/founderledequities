"""Who is the CEO? Read it from tagged data instead of guessing from titles.

Form 4's `officerTitle` is a free-text box with no taxonomy, so title matching
is unbounded maintenance -- and it fails in the worst way, picking Microsoft's
CEO of Commercial Business over Satya Nadella and producing a confident wrong
row rather than an error.

Item 402(v) requires the pay-versus-performance disclosure to be tagged in
Inline XBRL, and the ECD taxonomy defines `ecd:PeoName` for the principal
executive officer. "Principal executive officer" is a regulatory concept, not
a job title, so divisional CEOs cannot collide with it by construction.

Where each individual's facts are dimensionally qualified, the
`ecd:IndividualAxis` member distinguishes them -- which also means mid-year
CEO transitions appear as two named PEOs with different periods, exactly what
a point-in-time panel needs.

Known limits, all handled by the caller ranking sources rather than trusting
this one blindly:
  * Nothing before the 2023 proxy season (fiscal years ending on or after
    16 Dec 2022).
  * Emerging growth companies, foreign private issuers and registered
    investment companies are exempt.
  * Smaller reporting companies had an iXBRL phase-in.
  * Some filers mis-tag every NEO with ecd:PeoName, so a filing can appear to
    have five PEOs. `suspect_overtagged` flags that.
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field, asdict

from bs4 import BeautifulSoup

try:
    from bs4 import XMLParsedAsHTMLWarning

    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
except ImportError:  # pragma: no cover
    pass

PEO_NAME_RE = re.compile(r"(?:^|:)PeoName$", re.I)
PEO_FLAG_RE = re.compile(r"(?:^|:)PeoFlag$", re.I)
INDIVIDUAL_AXIS_RE = re.compile(r"IndividualAxis", re.I)
# A plausible personal name. Commas MUST be allowed: a tagged PEO of
# "Jerry E. Gahlhoff, Jr." or "Markus Warmuth, M.D." was previously discarded
# outright, because the character class had no comma in it.
NAME_SHAPE_RE = re.compile(
    r"^[A-Z][\w.'\-]*(?:[,]?\s+[A-Za-z][\w.'\-]*){1,5}$"
)


@dataclass
class PeoFact:
    name: str
    context_ref: str | None = None
    period_end: str | None = None
    individual_member: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class PeoResult:
    names: list[str] = field(default_factory=list)   # most recent first
    facts: list[PeoFact] = field(default_factory=list)
    suspect_overtagged: bool = False
    transition_detected: bool = False
    source: str = "ixbrl_peoname"

    @property
    def primary(self) -> str | None:
        return self.names[0] if self.names else None

    def as_dict(self) -> dict:
        return {
            "names": self.names,
            "suspect_overtagged": self.suspect_overtagged,
            "transition_detected": self.transition_detected,
            "source": self.source,
        }


def _parse_contexts(soup: BeautifulSoup) -> dict[str, dict]:
    """contextRef -> {period_end, individual_member}.

    Namespaces survive as part of the tag name under an HTML parser
    (`xbrli:context`), and some filers emit them unprefixed, so match on the
    suffix rather than an exact tag name.
    """
    contexts: dict[str, dict] = {}
    for node in soup.find_all(lambda t: t.name and t.name.split(":")[-1] == "context"):
        cid = node.get("id")
        if not cid:
            continue
        end = None
        for child in node.find_all(
            lambda t: t.name and t.name.split(":")[-1] in ("enddate", "instant")
        ):
            end = (child.get_text() or "").strip() or end
        member = None
        for child in node.find_all(
            lambda t: t.name and t.name.split(":")[-1] == "explicitmember"
        ):
            if INDIVIDUAL_AXIS_RE.search(child.get("dimension", "")):
                member = (child.get_text() or "").strip()
        contexts[cid] = {"period_end": end, "individual_member": member}
    return contexts


HONORIFIC_RE = re.compile(
    r"^(mr|mrs|ms|miss|dr|prof|sir|hon|rev)\.?\s+", re.I
)


def _clean_name(raw: str) -> str:
    name = re.sub(r"\s+", " ", raw or "").strip()
    name = name.strip(" .,;:")
    # Tesla tags its PEO as "Mr. Musk", which then fails to match the
    # certification's "Elon Musk" and raises a spurious disagreement.
    name = HONORIFIC_RE.sub("", name).strip()
    # Filers sometimes run a middle initial into the surname: "Ron M.Vachris".
    # Split ONLY after a period -- an earlier version split before any capital
    # and turned "McMillon" into "Mc Millon", which then failed to match the
    # Form 4 name "McMillon C Douglas".
    name = re.sub(r"(?<=\.)(?=[A-Z][a-z])", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def extract_peo(html: str) -> PeoResult:
    """Pull tagged PEO names out of a proxy's inline XBRL."""
    soup = BeautifulSoup(html, "lxml")
    contexts = _parse_contexts(soup)

    facts: list[PeoFact] = []
    for node in soup.find_all(attrs={"name": True}):
        attr = node.get("name") or ""
        if not PEO_NAME_RE.search(attr.split(":")[-1] and attr or ""):
            # match on the local part, e.g. "ecd:PeoName" -> "PeoName"
            if not PEO_NAME_RE.search(attr):
                continue
        text = _clean_name(node.get_text(" ", strip=True))
        if not text or not NAME_SHAPE_RE.match(text):
            continue
        ctx = contexts.get(node.get("contextref") or node.get("contextRef") or "", {})
        facts.append(
            PeoFact(
                name=text,
                context_ref=node.get("contextref") or node.get("contextRef"),
                period_end=ctx.get("period_end"),
                individual_member=ctx.get("individual_member"),
            )
        )

    result = PeoResult(facts=facts)
    if not facts:
        return result

    # Most recent period first; undated facts sort last but keep document order.
    dated = [f for f in facts if f.period_end]
    undated = [f for f in facts if not f.period_end]
    dated.sort(key=lambda f: f.period_end or "", reverse=True)
    ordered = dated + undated

    seen: set[str] = set()
    names: list[str] = []
    for f in ordered:
        key = f.name.lower()
        if key not in seen:
            seen.add(key)
            names.append(f.name)
    result.names = names

    # Several distinct names is normally a CEO transition. But some filers tag
    # every NEO with ecd:PeoName, which looks identical -- if the SAME period
    # carries several names, that is a tagging error, not a transition.
    by_period: dict[str, set[str]] = {}
    for f in ordered:
        by_period.setdefault(f.period_end or "", set()).add(f.name.lower())
    if any(len(v) > 2 for v in by_period.values()):
        result.suspect_overtagged = True
    elif len(names) > 1:
        result.transition_detected = True

    return result


def peo_names(html: str) -> list[str]:
    """Convenience: just the names, most recent first."""
    return extract_peo(html).names
