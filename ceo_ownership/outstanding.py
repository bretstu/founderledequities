"""The denominator: shares outstanding.

Source is dei:EntityCommonStockSharesOutstanding from the XBRL companyfacts
API -- the cover-page share count, free and machine-readable.

Two things to know.

1. Multi-class filers report this once PER CLASS on the cover page, but
   companyfacts does not preserve the class dimension. The classes therefore
   surface as several facts sharing an `end` date and `accn`. Summing within
   that group reconstructs total shares outstanding; the group size tells you
   how many classes there are.

2. companyfacts keeps only the LATEST value -- a restatement overwrites
   history. For a backtest this is fatal, so `snapshot()` freezes the values
   at ingest. Never re-pull a denominator for a historical period.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, asdict

from .edgar import EdgarClient

TAG = "EntityCommonStockSharesOutstanding"
FALLBACK_TAGS = ["CommonStockSharesOutstanding", "CommonStockSharesIssued"]


@dataclass
class OutstandingSnapshot:
    cik: int
    end_date: str
    filed_date: str
    accession: str
    form: str
    total_shares: float
    class_count: int
    per_class: list[float]
    tag_used: str
    captured_at: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _collect(facts: dict, taxonomy: str, tag: str) -> list[dict]:
    return (
        facts.get("facts", {})
        .get(taxonomy, {})
        .get(tag, {})
        .get("units", {})
        .get("shares", [])
    )


def outstanding_series(client: EdgarClient, cik: int) -> list[OutstandingSnapshot]:
    """Every cover-page share count, newest first, classes summed."""
    facts = client.company_facts(cik)

    entries: list[dict] = []
    tag_used = TAG
    entries = _collect(facts, "dei", TAG)
    if not entries:
        for alt in FALLBACK_TAGS:
            entries = _collect(facts, "us-gaap", alt)
            if entries:
                tag_used = alt
                break
    if not entries:
        return []

    # Group by (end, accession): one group == one cover page == all classes.
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for e in entries:
        groups[(e.get("end"), e.get("accn"))].append(e)

    out: list[OutstandingSnapshot] = []
    for (end, accn), members in groups.items():
        vals = [float(m["val"]) for m in members if m.get("val") is not None]
        if not vals:
            continue
        first = members[0]
        out.append(
            OutstandingSnapshot(
                cik=cik,
                end_date=end or "",
                filed_date=first.get("filed", ""),
                accession=accn or "",
                form=first.get("form", ""),
                total_shares=sum(vals),
                class_count=len(vals),
                per_class=sorted(vals, reverse=True),
                tag_used=tag_used,
            )
        )

    out.sort(key=lambda s: (s.filed_date, s.end_date), reverse=True)
    return out


def outstanding_as_of(
    client: EdgarClient, cik: int, as_of: str | None = None
) -> OutstandingSnapshot | None:
    """Share count available as of a date, keyed on FILED date.

    Keying on `filed` rather than `end` is the look-ahead guard: a Q1 cover
    page dated March is not knowable until the 10-Q is filed in May.
    """
    series = outstanding_series(client, cik)
    if not series:
        return None
    if as_of is None:
        return series[0]
    eligible = [s for s in series if s.filed_date and s.filed_date <= as_of]
    return eligible[0] if eligible else None


def snapshot(series: list[OutstandingSnapshot], captured_at: str) -> list[dict]:
    """Freeze denominators at ingest so restatements cannot rewrite history."""
    frozen = []
    for s in series:
        d = s.as_dict()
        d["captured_at"] = captured_at
        frozen.append(d)
    return frozen


# ---------------------------------------------------------------------------
# Denominator from the proxy document itself.
#
# companyfacts is unusable for multi-class issuers: they report share counts
# as DIMENSIONED facts (one per class), companyfacts strips dimensions, and
# nothing survives. Meta's companyfacts contains no dei tag and no
# CommonStockSharesOutstanding at all -- and multi-class is exactly the
# founder-led population that matters most here.
#
# The proxy states the number in plain text, on the same record date as the
# ownership table. That is a better source than the XBRL cover page anyway,
# because it removes a date mismatch between numerator and denominator.
# ---------------------------------------------------------------------------

import re as _re

_SHARE_COUNT = r"([\d]{1,3}(?:,\d{3})+)"

_NUM_RE = _re.compile(r"\b(\d{1,3}(?:,\d{3}){2,})\b")
_CLASS_RE = _re.compile(r"Class\s+([A-Z])\b", _re.I)


def shares_outstanding_from_proxy(text: str, window: int | None = None) -> dict:
    """Scrape total shares outstanding out of proxy prose.

    Sentence-based rather than one big regex, because the phrasings vary far
    more than a pattern list can anticipate: "there were X shares ...
    outstanding", "X shares of Class A common stock and Y shares of Class B
    common stock were outstanding", "based on X shares outstanding".

    Scans the WHOLE document. An earlier version looked only at the first
    400k characters and missed Meta entirely, because Meta puts its
    record-date share counts in the Q&A section at the end of a 1.3M-char
    proxy.

    Returns {"total": float|None, "per_class": {...}, "matches": [...]}.
    Takes the largest figure per class; proxies quote smaller partial counts
    alongside the record-date total.
    """
    haystack = text if window is None else text[:window]
    per_class: dict[str, float] = {}
    matches: list[str] = []

    for sentence in _re.split(r"(?<=[.;])\s+", haystack):
        low = sentence.lower()
        if "outstanding" not in low or "share" not in low:
            continue
        if len(sentence) > 1200:
            continue
        # Skip option/plan sentences -- those counts are not shares outstanding.
        if _re.search(r"option|award|rsu|restricted|reserved for issuance|"
                      r"available for (?:future )?(?:grant|issuance)", low):
            continue

        # "6,659,444,154 shares of Class A common stock and Class B common
        # stock issued and outstanding, consisting of 5,823,665,113 shares of
        # Class A ..." -- the leading figure is a TOTAL of the classes that
        # follow. Counting both double-counts Alphabet by ~836M shares.
        consisting_at = sentence.lower().find("consisting of")

        for m in _NUM_RE.finditer(sentence):
            if consisting_at != -1 and m.start() < consisting_at:
                continue
            try:
                val = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            if val < 1_000_000:
                continue
            # Which class does this number belong to? Look just after it,
            # then just before, taking the nearest mention.
            after = sentence[m.end(): m.end() + 70]
            before = sentence[max(0, m.start() - 70): m.start()]
            cm = _CLASS_RE.search(after) or _CLASS_RE.search(before)
            key = f"Class {cm.group(1).upper()}" if cm else "Common"
            if val > per_class.get(key, 0):
                per_class[key] = val
                matches.append(_re.sub(r"\s+", " ", sentence)[:160])

    # A bare "Common" alongside named classes is usually a restatement of one
    # of them, not an extra class -- drop it to avoid double counting.
    if len(per_class) > 1 and "Common" in per_class:
        per_class.pop("Common")

    total = sum(per_class.values()) if per_class else None
    return {"total": total, "per_class": per_class, "matches": matches[:4]}


def implied_outstanding(shares: float | None, pct: float | None,
                        options_60d: float | None = None) -> float | None:
    """Back out the denominator from a row that states both shares and percent.

    Always available when any row shows a real percentage, and it is the
    filer's own arithmetic, so it needs no external source. Rule 13d-3(d)(1)(i)
    puts that holder's own options in their denominator, so remove them to
    recover plain shares outstanding.
    """
    if not shares or not pct or pct <= 0:
        return None
    denom_for_row = shares / (pct / 100.0)
    out = denom_for_row - (options_60d or 0)
    return out if out > 0 else None
