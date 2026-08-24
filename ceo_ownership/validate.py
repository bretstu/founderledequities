"""Validation. This is where accuracy is actually earned.

Three independent checks, each proving something different:

  1. INTERNAL RECONCILIATION -- does shares / (outstanding + own options)
     reproduce the printed percentage? Rule 13d-3(d)(1)(i) deems a person's
     exercisable options outstanding for THEIR percentage only, so every row
     has its own denominator. If our arithmetic reproduces the filer's number,
     then the share count, the percentage, the denominator and the option
     decomposition are all simultaneously correct. Four confirmations, one
     check, zero labelling cost.

     What it CANNOT catch: a wrong-person error. Every row in the table
     reconciles internally, including the CFO's. Hence check 3.

  2. GROUP-ROW BOUND -- the CEO's holding must be <= the "all directors and
     executive officers as a group" line. Cheap, and it catches gross
     misparses. Also covers the case where the individual row shows only an
     asterisk (sub-1%), which is most large-cap CEOs and which silently
     removes them from check 1.

  3. CROSS-DOCUMENT IDENTITY -- does the proxy row agree with the Form 3/4
     filed by the person whose officerTitle names a CEO? Different document,
     different filer, different system. This is the only check that confirms
     we have the right human.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

from .config import SETTINGS
from .extract import OwnershipRow
from .form4 import Form4Record

NICKNAMES = {
    "robert": {"bob", "rob", "bobby"}, "william": {"bill", "will", "billy"},
    "richard": {"rick", "dick", "rich"}, "james": {"jim", "jimmy"},
    "john": {"jack", "johnny"}, "michael": {"mike"}, "thomas": {"tom", "tommy"},
    "charles": {"charlie", "chuck"}, "edward": {"ed", "eddie", "ted"},
    "daniel": {"dan", "danny"}, "christopher": {"chris"}, "joseph": {"joe", "joey"},
    "anthony": {"tony"}, "kenneth": {"ken"}, "steven": {"steve"},
    "stephen": {"steve"}, "andrew": {"andy", "drew"}, "matthew": {"matt"},
    "nicholas": {"nick"}, "benjamin": {"ben"}, "samuel": {"sam"},
    "patricia": {"pat", "patty"}, "elizabeth": {"liz", "beth", "betsy"},
    "katherine": {"kate", "kathy", "katie"}, "margaret": {"maggie", "peggy"},
    "jennifer": {"jen", "jenny"}, "deborah": {"deb", "debbie"},
    "susan": {"sue", "susie"}, "rebecca": {"becky"}, "jeffrey": {"jeff"},
    "gregory": {"greg"}, "lawrence": {"larry"}, "ronald": {"ron"},
    "donald": {"don"}, "timothy": {"tim"}, "frederick": {"fred"},
    "roland": {"ron"}, "lawrence2": set(), "francis": {"frank"},
    "theodore": {"ted", "teddy"}, "eugene": {"gene"}, "arthur": {"art"},
    "albert": {"al"}, "alexander": {"alex", "sandy"}, "vincent": {"vince"},
    "raymond": {"ray"}, "harold": {"hal", "harry"}, "henry": {"hank", "harry"},
    "leonard": {"len", "lenny"}, "walter": {"walt"}, "philip": {"phil"},
    "peter": {"pete"}, "douglas": {"doug"}, "russell": {"russ"},
    "bradley": {"brad"}, "cynthia": {"cindy"}, "barbara": {"barb"},
    "victoria": {"vicki", "vicky"}, "veronica": {"ronnie"},
    "kimberly": {"kim"}, "pamela": {"pam"}, "sandra": {"sandy"},
    "theresa": {"terry", "teri"}, "teresa": {"terry", "teri"},
}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v", "phd", "md", "cpa", "esq"}


SMART_PUNCT = str.maketrans({
    "\u2019": "'", "\u2018": "'", "\u02bc": "'",   # curly apostrophes
    "\u201c": '"', "\u201d": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-",
    "\u2013": "-", "\u2014": "-",
})


def normalize_name(raw: str) -> list[str]:
    """-> ordered list of lowercase name tokens, suffixes and initials dropped."""
    # Typographic punctuation first. Filings set apostrophes as U+2019, and a
    # curly one falls outside the allowed characters below and becomes a
    # SPACE -- so Gilead's "Daniel P. O\u2019Day" tokenised as ["o", "day"]
    # while the certification's straight-quoted "O'Day" gave ["oday"], and
    # the CEO was never found in his own ownership table.
    name = (raw or "").translate(SMART_PUNCT)
    name = re.sub(r"\([^)]*\)", " ", name)
    name = re.sub(r"[^A-Za-z,\s'\-]", " ", name)
    if "," in name:  # "Iger, Robert A." -> "Robert A. Iger"
        last, _, rest = name.partition(",")
        name = f"{rest} {last}"
    # Apostrophes are removed, not merely trimmed: EDGAR writes "DAmaro
    # Joshua W" while the certification says "Josh D'Amaro", and an internal
    # apostrophe made those different tokens. Same for O'Brien, O'Leary.
    tokens = [t.strip(".'-").replace("'", "").lower() for t in name.split()]
    # Single letters are KEPT. Proxy tables routinely abbreviate given names
    # to an initial -- Johnson & Johnson lists "J. Duato" for Joaquin Duato --
    # and dropping the initial collapsed the name to a lone surname, which
    # scored 0.60 and fell just under the 0.70 accept threshold. Five
    # companies failed that way, including J&J and GE.
    return [t for t in tokens if t and t not in SUFFIXES]


def _interpretations(tokens: list[str]) -> list[tuple[str, str]]:
    """Candidate (given_name, surname) readings of a token list.

    The two sources disagree on convention: proxies write "Ron M. Vachris"
    (surname last) while EDGAR's rptOwnerName writes "Vachris Roland Michael"
    -- surname FIRST, no comma, and the given name in the MIDDLE. An earlier
    version only paired the first and last tokens, so it read that as
    given="Michael" and never tried "Roland". Every three-token EDGAR name
    was silently unmatchable.

    So: fix each end as the surname in turn, and allow any other token to be
    the given name. The surname must still match exactly, which keeps this
    from collapsing distinct people together.
    """
    if not tokens:
        return []
    if len(tokens) == 1:
        return [(tokens[0], tokens[0])]
    out = []
    for g in tokens[:-1]:          # surname last  (proxy convention)
        out.append((g, tokens[-1]))
    for g in tokens[1:]:           # surname first (EDGAR convention)
        out.append((g, tokens[0]))
    return out


def _score_pair(fa: str, fb: str) -> float:
    """Confidence that two given names are the same person."""
    if fa == fb:
        return 1.0
    if fb in NICKNAMES.get(fa, set()) or fa in NICKNAMES.get(fb, set()):
        return 0.9
    # Diminutive by truncation: Ron/Roland, Tim/Timothy, Chris/Christopher,
    # Dan/Daniel, Greg/Gregory, Jeff/Jeffrey. Generalises past any fixed list.
    short, long_ = sorted((fa, fb), key=len)
    if len(short) >= 3 and long_.startswith(short):
        return 0.85
    # A bare initial, e.g. "R. Vachris" vs "Roland".
    if len(fa) == 1 or len(fb) == 1:
        return 0.75 if fa[0] == fb[0] else 0.0
    # Two different full names sharing a letter is weak -- deliberately below
    # the 0.7 accept threshold, so it surfaces as a near miss instead of a
    # false positive between, say, John and Jane Smith.
    return 0.5 if fa[0] == fb[0] else 0.0


def names_match(a: str, b: str) -> float:
    """0.0-1.0 confidence that two name strings refer to the same person.

    Both the surname and the given name must agree under some reading. That
    keeps family members at the same company from colliding, which matters --
    founder-controlled firms frequently have several relatives in the table.
    """
    ta, tb = normalize_name(a), normalize_name(b)
    if not ta or not tb:
        return 0.0
    if len(ta) == 1 or len(tb) == 1:
        # Genuinely only one usable token -- a surname alone. It can support
        # the match but cannot confirm it, so this stays below the threshold.
        lone = ta[0] if len(ta) == 1 else tb[0]
        other = tb if len(ta) == 1 else ta
        return 0.6 if lone in other else 0.0

    best = 0.0
    for given_a, sur_a in _interpretations(ta):
        for given_b, sur_b in _interpretations(tb):
            if sur_a != sur_b:
                continue
            best = max(best, _score_pair(given_a, given_b))
    return best


@dataclass
class Check:
    name: str
    passed: bool | None  # None == could not run
    detail: str
    value: float | None = None


@dataclass
class ValidationReport:
    checks: list[Check] = field(default_factory=list)
    confidence: str = "UNKNOWN"
    flags: list[str] = field(default_factory=list)

    def add(self, check: Check) -> None:
        self.checks.append(check)

    def as_dict(self) -> dict:
        return {
            "confidence": self.confidence,
            "flags": self.flags,
            "checks": [asdict(c) for c in self.checks],
        }


def _printed_precision(pct: float) -> float:
    """Half-width of the rounding band for a percentage as printed.

    "19.8" means the true value lies in [19.75, 19.85). Ignoring that band
    makes an inferred option count look wrong by a couple of percent.
    """
    text = f"{pct!r}"
    if "." in text:
        return 0.5 * (10 ** -len(text.split(".")[1]))
    return 0.5


def reconcile_percentage(
    row: OwnershipRow, outstanding: float | None, tolerance: float | None = None
) -> Check:
    """Compare our arithmetic to the filer's printed percentage.

    The two denominators differ ON PURPOSE. Rule 13d-3(d)(1)(i) deems a
    holder's own 60-day options outstanding for THEIR percentage and no one
    else's, so the filer divides by (outstanding + their options) while we
    divide by outstanding alone.

    That means the gap is not an error -- it MEASURES the option component:

        shares / pct  -  outstanding  =  the holder's 60-day options

    Tesla: 717,323,438 / 0.198 = 3,622,845,646, less 3,325,150,886 shares
    outstanding, implies ~297.7M options against a footnoted 303,960,630 --
    the difference being 19.8% rounded to one decimal.

    So a POSITIVE gap is expected and is reported as an inferred option
    count. A NEGATIVE gap is a real failure: it means our share count is too
    high or our denominator too low.
    """
    if row.pct_is_asterisk:
        return Check("pct_reconciliation", None, "filing shows asterisk (<1%)")
    if row.pct_reported is None or row.shares_reported is None or not outstanding:
        return Check("pct_reconciliation", None, "missing inputs")

    pct = row.pct_reported
    half = _printed_precision(pct)
    lo_pct, hi_pct = max(pct - half, 1e-9), pct + half

    # Denominator the filer must have used, as a band.
    denom_lo = row.shares_reported / (hi_pct / 100.0)
    denom_hi = row.shares_reported / (lo_pct / 100.0)
    implied_lo = denom_lo - outstanding
    implied_hi = denom_hi - outstanding

    if implied_hi < 0:
        # Filer's denominator is SMALLER than shares outstanding. Nothing in
        # 13d-3 explains that -- our number or our denominator is wrong.
        computed = 100.0 * row.shares_reported / outstanding
        return Check(
            "pct_reconciliation",
            False,
            f"computed {computed:.3f}% vs reported {pct:.3f}%; filer's implied "
            f"denominator is BELOW shares outstanding by "
            f"{abs(implied_hi):,.0f} -- share count or denominator is wrong",
            value=computed - pct,
        )

    if implied_lo <= 0 <= implied_hi:
        return Check(
            "pct_reconciliation",
            True,
            f"reported {pct:.3f}% reproduced with no option adjustment "
            f"(band allows 0 to {implied_hi:,.0f})",
            value=0.0,
        )

    midpoint = 0.5 * (implied_lo + implied_hi)
    # Hard logical bound: 13d-3 counts 60-day options INSIDE the reported
    # share figure, so the option component is a subset of it and cannot
    # exceed it. Anything larger means the share count or the denominator is
    # wrong, not that the CEO holds a vast option package.
    if midpoint > row.shares_reported:
        return Check(
            "pct_reconciliation",
            False,
            f"implied 60-day options {midpoint:,.0f} exceed the reported "
            f"holding of {row.shares_reported:,} -- impossible, since 13d-3 "
            f"counts options within that figure",
            value=midpoint,
        )

    return Check(
        "pct_reconciliation",
        True,
        f"reported {pct:.3f}% implies {midpoint:,.0f} 60-day options "
        f"(band {implied_lo:,.0f}-{implied_hi:,.0f}); consistent with "
        f"Rule 13d-3(d)(1)(i)",
        value=midpoint,
    )


def group_percentage_check(
    group: OwnershipRow | None, outstanding: float | None
) -> Check:
    """Reconcile the GROUP row's percentage against shares outstanding.

    Most CEOs hold under one percent, so their row prints an asterisk and the
    individual reconciliation cannot run -- 89 of 98 rows in a 100-company
    panel. But the "all directors and officers as a group" row often does
    carry a real figure, because the aggregate clears one percent.

    This cannot confirm the CEO's own holding. What it does confirm is the
    denominator and that the table's numbers are being read correctly, which
    are the two failures most likely to be silently wrong -- and it does so
    on rows where nothing else could.
    """
    if group is None or group.pct_is_asterisk:
        return Check("group_pct_reconciliation", None,
                     "group row absent or shows an asterisk")
    if group.pct_reported is None or group.shares_reported is None:
        return Check("group_pct_reconciliation", None, "missing inputs")
    if not outstanding:
        return Check("group_pct_reconciliation", None, "no denominator")

    computed = 100.0 * group.shares_reported / outstanding
    delta = computed - group.pct_reported
    # A positive gap is expected: the group's own 60-day options sit in their
    # denominator. Only a NEGATIVE gap beyond rounding is a real problem.
    if delta < -0.2:
        return Check(
            "group_pct_reconciliation", False,
            f"group {group.shares_reported:,} is {computed:.3f}% of "
            f"outstanding but the filing says {group.pct_reported:.3f}% -- "
            f"denominator or share count is wrong",
            value=delta,
        )
    return Check(
        "group_pct_reconciliation", True,
        f"group {group.shares_reported:,} -> {computed:.3f}% vs reported "
        f"{group.pct_reported:.3f}%; denominator confirmed",
        value=delta,
    )


def group_bound(ceo: OwnershipRow, group: OwnershipRow | None) -> Check:
    if group is None or group.shares_reported is None or ceo.shares_reported is None:
        return Check("group_bound", None, "no group row found")
    ok = ceo.shares_reported <= group.shares_reported
    return Check(
        "group_bound",
        ok,
        f"CEO {ceo.shares_reported:,} vs group {group.shares_reported:,}",
        value=float(ceo.shares_reported) / float(group.shares_reported or 1),
    )


def cross_document(
    ceo: OwnershipRow, f4: Form4Record | None, tolerance: float | None = None
) -> tuple[Check, Check]:
    tol = tolerance if tolerance is not None else SETTINGS.form4_divergence_tolerance
    if f4 is None:
        no = Check("identity_match", None, "no CEO Form 3/4/5 located")
        return no, Check("form4_divergence", None, "no CEO Form 3/4/5 located")

    score = names_match(ceo.name_raw, f4.owner_name)
    identity = Check(
        "identity_match",
        score >= 0.7,
        f"proxy {ceo.name_raw!r} vs form4 {f4.owner_name!r} (score {score:.2f}, "
        f"title {f4.officer_title!r})",
        value=score,
    )

    proxy_common = ceo.common_shares
    f4_total = f4.total_common
    if proxy_common is None or not f4_total:
        return identity, Check("form4_divergence", None, "missing share counts")
    rel = abs(proxy_common - f4_total) / max(f4_total, 1.0)
    divergence = Check(
        "form4_divergence",
        rel <= tol,
        f"proxy {proxy_common:,.0f} vs form4 {f4_total:,.0f} "
        f"({rel:.1%} apart, tol {tol:.0%})",
        value=rel,
    )
    return identity, divergence


def assign_confidence(report: ValidationReport, location_conf: str) -> str:
    """HIGH requires positive identity evidence, not merely absence of failure."""
    by_name = {c.name: c for c in report.checks}
    failed = [c.name for c in report.checks
              if c.passed is False and "informational" not in c.name]

    if failed:
        return "LOW"
    if location_conf in ("NONE", "LOW"):
        return "LOW"

    identity_ok = by_name.get("identity_match") and by_name["identity_match"].passed
    recon_ok = by_name.get("pct_reconciliation") and by_name["pct_reconciliation"].passed
    bound_ok = by_name.get("group_bound") and by_name["group_bound"].passed
    cont_ok = by_name.get("yoy_continuity") and by_name["yoy_continuity"].passed

    # A numeric confirmation means the share COUNT was corroborated, not just
    # the person. Reconciliation does it where a percentage is printed;
    # continuity does it everywhere else. group_bound alone is too weak to
    # count -- CEO <= group is satisfied by almost any misparse.
    grp_pct_ok = (by_name.get("group_pct_reconciliation")
                  and by_name["group_pct_reconciliation"].passed)
    # An independent read of the same section is the only check that does
    # not compare one of our readings against another of our readings.
    readers_ok = (by_name.get("readers_agree")
                  and by_name["readers_agree"].passed)
    numeric_ok = recon_ok or cont_ok or grp_pct_ok or readers_ok

    # Identity is mandatory: reconciliation passes just as happily on the
    # wrong person's row, so it can never substitute for confirming the human.
    # Informational-only checks never fail a record.
    if identity_ok and numeric_ok:
        return "HIGH"
    if identity_ok and bound_ok:
        return "MEDIUM"
    if identity_ok:
        return "MEDIUM"
    return "LOW"
