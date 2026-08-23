"""Year-over-year continuity: the numeric check that works on asterisk rows.

The percentage reconciliation is the strongest numeric validator available,
but it only runs when the filer prints a real percentage -- and most large-cap
CEOs hold under 1%, so their row shows an asterisk. For those companies
nothing currently verifies the share COUNT at all; `identity_match` confirms
the person and `group_bound` is nearly always satisfied.

Continuity fills that gap. Pull last year's proxy, extract the same person's
holding the same way, and compare. A CEO's stake moves gradually -- grants
vest, options are exercised, shares are sold under 10b5-1 plans -- so a large
unexplained jump is far more likely to be a parsing error than a real event.

It is also nearly free: one extra proxy fetch, cached, with no model call.

What it catches that nothing else does:
  * a wrong column chosen this year but not last (or vice versa)
  * digits dropped or a scale error, which shows up as a clean 10x/100x ratio
  * a filer changing table layout between years
  * the denominator drifting while the numerator did not

What it cannot catch:
  * an error made consistently in both years -- continuity confirms stability,
    not correctness
  * anything in a CEO's first year, where there is no prior filing
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from .certification import peo_from_certification
from .edgar import EdgarClient
from .freepath import parse_table_heuristic
from .extract import table_to_text
from .proxy import find_proxy_filing, load_proxy_html, locate_ownership_tables
from .validate import names_match

# Thresholds are ASYMMETRIC on purpose. A holding can plausibly double: a
# grant vests, options are exercised, shares are bought. It cannot plausibly
# collapse by 97% without a specific event -- a large sale, a transition, or a
# misparse. Oracle slipped through a symmetric band because abs(0.027 - 1) is
# 0.973, just under a ceiling designed to catch increases.
STABLE_BAND = 0.25          # +/- 25%: ordinary drift
MAX_PLAUSIBLE_INCREASE = 1.00   # up to +100%
MAX_PLAUSIBLE_DECREASE = 0.50   # down to -50%
# Ratios near a power of ten almost always mean digits were lost or gained.
SCALE_RATIOS = (10.0, 100.0, 1000.0)
SCALE_TOLERANCE = 0.02


@dataclass
class ContinuityResult:
    prior_shares: float | None = None
    prior_filing_date: str | None = None
    prior_matched_name: str | None = None
    change_ratio: float | None = None
    verdict: str = "skipped"          # stable | plausible | suspicious | skipped
    detail: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _looks_like_scale_error(ratio: float) -> float | None:
    """Return the power of ten if the ratio is suspiciously close to one."""
    for scale in SCALE_RATIOS:
        for candidate in (scale, 1.0 / scale):
            if abs(ratio - candidate) / candidate < SCALE_TOLERANCE:
                return candidate
    return None


def check_continuity(
    client: EdgarClient,
    cik: int,
    current_shares: float | None,
    current_filing_date: str | None,
    candidate_names: list[str],
) -> ContinuityResult:
    """Compare this year's holding against the same person's a year earlier."""
    res = ContinuityResult()

    if not current_shares or not current_filing_date or not candidate_names:
        res.detail = "no current figure or CEO name to compare"
        return res

    # The prior proxy is simply the most recent one filed before this one.
    day_before = _minus_one_day(current_filing_date)
    try:
        prior = find_proxy_filing(client, cik, before=day_before)
    except Exception:  # noqa: BLE001
        res.detail = "no prior proxy found"
        return res

    res.prior_filing_date = prior["filing_date"]
    if prior["filing_date"] >= current_filing_date:
        res.detail = "prior filing is not older than the current one"
        return res

    # Was this person actually CEO a year ago? Matching on name alone is not
    # enough: Furner appears in Walmart's prior table as a director and
    # executive officer, and Oracle's prior figure belonged to a different
    # chief executive. Comparing across a transition measures the wrong thing.
    try:
        prior_cert = peo_from_certification(
            client, cik, before=prior["filing_date"]
        )
    except Exception:  # noqa: BLE001
        prior_cert = None
    if prior_cert and not any(
        names_match(prior_cert.name, c) >= 0.7 for c in candidate_names
    ):
        res.verdict = "skipped"
        res.detail = (
            f"CEO changed: {prior_cert.name!r} certified the "
            f"{prior['filing_date']} period, not {candidate_names[0]!r} -- "
            f"nothing comparable"
        )
        return res

    try:
        html = load_proxy_html(client, prior)
        cands = locate_ownership_tables(html)
    except Exception as exc:  # noqa: BLE001
        res.detail = f"prior proxy could not be read: {exc}"
        return res
    if not cands:
        res.detail = "no ownership table located in the prior proxy"
        return res

    rows = parse_table_heuristic(table_to_text(cands[0].html))
    people = [r for r in rows if not r.is_group_row]
    match = None
    for cand in candidate_names:
        scored = sorted(
            ((names_match(r.name_raw, cand), r) for r in people),
            key=lambda t: t[0],
            reverse=True,
        )
        if scored and scored[0][0] >= 0.7:
            match = scored[0][1]
            break

    if match is None or not match.shares_reported:
        # Usually a CEO transition: last year's table lists someone else.
        res.detail = (
            f"CEO not found in the {prior['filing_date']} proxy -- most likely "
            f"a transition, so there is nothing to compare"
        )
        return res

    res.prior_shares = float(match.shares_reported)
    res.prior_matched_name = match.name_raw
    ratio = current_shares / res.prior_shares if res.prior_shares else None
    res.change_ratio = ratio

    if ratio is None:
        res.detail = "prior holding was zero"
        return res

    change = abs(ratio - 1.0)
    scale = _looks_like_scale_error(ratio)

    if scale is not None:
        res.verdict = "suspicious"
        res.detail = (
            f"{res.prior_shares:,.0f} -> {current_shares:,.0f} is almost "
            f"exactly {scale:g}x -- that is the signature of dropped or "
            f"duplicated digits, not a real change"
        )
    elif change <= STABLE_BAND:
        res.verdict = "stable"
        res.detail = (
            f"{res.prior_shares:,.0f} ({prior['filing_date']}) -> "
            f"{current_shares:,.0f}, {(ratio - 1) * 100:+.1f}%"
        )
    elif ratio > 1.0 and (ratio - 1.0) <= MAX_PLAUSIBLE_INCREASE:
        res.verdict = "plausible"
        res.detail = (
            f"{res.prior_shares:,.0f} -> {current_shares:,.0f}, "
            f"{(ratio - 1) * 100:+.1f}% -- large but within what grants and "
            f"exercises can produce"
        )
    elif ratio < 1.0 and (1.0 - ratio) <= MAX_PLAUSIBLE_DECREASE:
        res.verdict = "plausible"
        res.detail = (
            f"{res.prior_shares:,.0f} -> {current_shares:,.0f}, "
            f"{(ratio - 1) * 100:+.1f}% -- a large sale would explain this"
        )
    elif ratio < 1.0:
        res.verdict = "suspicious"
        res.detail = (
            f"{res.prior_shares:,.0f} -> {current_shares:,.0f}, "
            f"{(ratio - 1) * 100:+.1f}% in one year. A collapse this size "
            f"needs a specific cause -- a disposal, a transition, or a "
            f"misparse. Verify before trusting"
        )
    else:
        res.verdict = "suspicious"
        res.detail = (
            f"{res.prior_shares:,.0f} -> {current_shares:,.0f}, "
            f"{(ratio - 1) * 100:+.1f}% in one year -- verify before trusting"
        )
    return res


def _minus_one_day(date_str: str) -> str:
    from datetime import date, timedelta

    try:
        y, m, d = (int(x) for x in date_str.split("-"))
        return (date(y, m, d) - timedelta(days=1)).isoformat()
    except Exception:  # noqa: BLE001
        return date_str
