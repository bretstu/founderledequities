"""Orchestration: ticker (or CIK) -> one validated ownership record.

Output metric, restated so it lives next to the code that computes it:

    pct_owned = common shares beneficially owned by the CEO
                (direct + indirect, disclaimed excluded, derivatives excluded)
                / total shares outstanding, all classes

Derivatives are excluded because an unexercised option is a right to buy, not
ownership, and an underwater one is worth nothing. Nothing real is lost: an
exercise moves the underlying into common on the same Form 4, so anything that
has become ownership is already counted.

Two percentages are emitted and they are not interchangeable:
  pct_reported   -- as printed by the filer. Auditable, but NOT comparable
                    across companies, because each row's denominator is
                    inflated by that person's own options.
  pct_comparable -- our number, single denominator for everyone. Sort and
                    rank on this one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import date

from .edgar import EdgarClient
from .extract import OwnershipRow, extract_ownership, extract_target, table_to_text
from .freepath import try_free_path, parse_table_heuristic
from .form4 import latest_ceo_filing, filing_for_person, Form4Record
from .peo import extract_peo
from .certification import peo_from_certification
from .continuity import check_continuity
from .outstanding import (outstanding_as_of, shares_outstanding_from_proxy,
                          implied_outstanding)
from .proxy import find_proxy_filing, load_proxy_html, locate_ownership_tables, location_confidence
from .validate import (
    Check,
    ValidationReport,
    assign_confidence,
    cross_document,
    group_bound,
    names_match,
    reconcile_percentage,
)


@dataclass
class OwnershipRecord:
    cik: int
    ticker: str | None
    company: str | None
    ceo_name: str | None
    ceo_source: str | None

    shares_13d3: float | None = None
    shares_source: str | None = None      # proxy_item403 | form4_all_classes
    column_used: str | None = None
    options_60d: float | None = None
    options_60d_implied: float | None = None
    prior_year_shares: float | None = None
    yoy_change_pct: float | None = None
    unvested_awards: float | None = None
    exchangeable_units: float | None = None
    shares_pledged: float | None = None

    shares_outstanding: float | None = None
    share_class_count: int | None = None
    denominator_source: str | None = None

    pct_reported: float | None = None
    pct_comparable: float | None = None
    pct_voting_power: float | None = None

    as_of_date: str | None = None
    filing_date: str | None = None
    source_form: str | None = None
    source_url: str | None = None
    used_fallback_form: bool = False

    form4_common_shares: float | None = None
    form4_filing_date: str | None = None

    sic: str | None = None
    sic_description: str | None = None
    ceo_identity_source: str | None = None  # sox302_ex31 | ixbrl_peoname | form4_title
    ceo_identity_evidence: str | None = None
    peo_names: str | None = None
    resolution: str | None = None       # "free_path" | "llm_extraction"
    escalation_reason: str | None = None
    confidence: str = "UNKNOWN"
    flags: list[str] = field(default_factory=list)
    validation: dict = field(default_factory=dict)
    error: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _pick_ceo_row(
    rows: list[OwnershipRow],
    f4: Form4Record | None,
    candidate_names: list[str] | None = None,
) -> tuple[OwnershipRow | None, str, str]:
    """Identify the CEO's row. Returns (row, source, diagnostic).

    Preference order reflects strength of evidence:
      1. Name match against the Form 4 filer whose officerTitle names a CEO.
         Independent document, strongest evidence.
      2. A title stated in the proxy table itself.
    Deliberately no positional fallback -- picking row 1 and hoping is the
    single worst failure mode, because a wrong human looks entirely plausible
    downstream and every other check still passes.

    When both routes fail, the diagnostic reports what WAS found so the
    failure is debuggable without another API call.
    """
    people = [r for r in rows if not r.is_group_row and not r.is_five_percent_holder]

    if not rows:
        return None, "unidentified", "extraction returned zero rows"

    # The tagged PEO name is the strongest evidence available: it is the
    # regulator's identification, printed in this same document.
    for cand in (candidate_names or []):
        hits = sorted(((names_match(r.name_raw, cand), r) for r in people),
                      key=lambda t: t[0], reverse=True)
        if hits and hits[0][0] >= 0.7:
            return hits[0][1], "peo_name_match", ""

    scored: list[tuple[float, OwnershipRow]] = []
    if f4 and f4.owner_name:
        scored = [(names_match(r.name_raw, f4.owner_name), r) for r in people]
        scored.sort(key=lambda t: t[0], reverse=True)
        if scored and scored[0][0] >= 0.7:
            return scored[0][1], "form4_name_match", ""

    titled = [r for r in people if r.title and "chief exec" in r.title.lower()]
    titled += [r for r in people if r.title and "ceo" in r.title.lower()]
    if titled:
        return titled[0], "proxy_table_title", ""

    # Failure: say exactly what was seen.
    names = [r.name_raw for r in people][:8]
    bits = [
        f"{len(rows)} rows extracted, {len(people)} non-group/non-5% candidates",
        f"names seen: {names}",
        f"form4 owner: {f4.owner_name!r}" if f4 else "no form4 record",
    ]
    if scored:
        bits.append(f"best name score: {scored[0][0]:.2f} for {scored[0][1].name_raw!r}")
    if not any(r.title for r in people):
        bits.append("no title column in table")
    return None, "unidentified", "; ".join(bits)


def _group_row(rows: list[OwnershipRow]) -> OwnershipRow | None:
    return next((r for r in rows if r.is_group_row), None)


def build_record(
    client: EdgarClient,
    cik: int,
    ticker: str | None = None,
    as_of: str | None = None,
    model: str | None = None,
    llm_mode: str = "auto",
    with_form4: bool = False,
    continuity: bool = True,
) -> OwnershipRecord:
    rec = OwnershipRecord(cik=cik, ticker=ticker, company=None, ceo_name=None, ceo_source=None)

    # ---- 1. locate the proxy ------------------------------------------
    try:
        filing = find_proxy_filing(client, cik, before=as_of)
    except Exception as exc:  # noqa: BLE001
        rec.error = f"proxy discovery failed: {exc}"
        rec.confidence = "LOW"
        return rec

    # Roughly a fifth of proxy filers are closed-end funds, ETF trusts and
    # similar registered investment companies. They file DEF 14A but have no
    # CEO ownership in the corporate sense, and they are exempt from the
    # pay-versus-performance tagging too. Flag them so the universe can be
    # filtered rather than silently producing nonsense rows.
    try:
        subs_meta = client.submissions(cik)
        rec.company = subs_meta.get("name") or None
        rec.sic = str(subs_meta.get("sic") or "")
        rec.sic_description = subs_meta.get("sicDescription") or ""
        # SIC is often blank for closed-end funds and ETF trusts, so the
        # reliable test is structural: registered investment companies report
        # on N-CSR, not 10-K/10-Q. No periodic report means no Section 302
        # certification exists to find -- and no CEO ownership in the
        # corporate sense either. Five of thirty sampled filers were these.
        periodic = [
            x for x in subs_meta.get("_filings", [])
            if x.get("form") in ("10-K", "10-Q", "10-K/A", "10-Q/A")
        ]
        if not periodic:
            rec.flags.append("no_periodic_reports_not_an_operating_company")
        if (
            rec.sic in ("6726", "6722", "6770")
            or re.search(r"investment offices?|unit investment trust|blank check",
                         rec.sic_description, re.I)
            or not periodic
        ):
            rec.flags.append("likely_investment_company")
    except Exception:  # noqa: BLE001
        pass

    rec.filing_date = filing["filing_date"]
    rec.source_form = filing["form"]
    rec.used_fallback_form = filing["fallback"]
    rec.source_url = (
        f"{EdgarClient.filing_dir(cik, filing['accession'])}/{filing['primary_document']}"
    )
    if filing["fallback"]:
        rec.flags.append(f"no_def14a_used_{filing['form']}")

    # ---- 2. locate the table ------------------------------------------
    try:
        html = load_proxy_html(client, filing)
    except Exception as exc:  # noqa: BLE001
        rec.error = f"document fetch failed: {exc}"
        rec.confidence = "LOW"
        return rec

    candidates = locate_ownership_tables(html)
    loc_conf = location_confidence(candidates)
    if not candidates:
        rec.error = "no ownership table located"
        rec.confidence = "LOW"
        return rec
    if loc_conf == "MEDIUM":
        rec.flags.append("ambiguous_table_location")

    top = candidates[0]

    # ---- 3. WHO is the CEO? -------------------------------------------
    # Priority: the Section 302 certification signature, because the signer
    # IS the principal executive officer by statute -- quarterly, back to
    # 2002, and no filer exemptions. The tagged ecd:PeoName is kept as a free
    # second opinion (the proxy HTML is already in hand). Free-text titles are
    # the last resort and always flagged.
    candidate_names: list[str] = []
    cert = None
    try:
        cert = peo_from_certification(client, cik, before=as_of)
    except Exception:  # noqa: BLE001
        pass
    if cert:
        rec.ceo_identity_source = "sox302_ex31"
        rec.ceo_identity_evidence = (
            f"{cert.exhibit_type or 'EX-31'} to {cert.form} filed "
            f"{cert.filing_date}"
        )
        candidate_names.append(cert.name)
        if cert.combined_certification:
            rec.flags.append("combined_certification_multiple_signers")

    peo = extract_peo(html)
    if peo.names:
        if not candidate_names:
            rec.ceo_identity_source = "ixbrl_peoname"
            rec.ceo_identity_evidence = "ecd:PeoName (proxy inline XBRL)"
        elif not any(
            names_match(cert.name, n) >= 0.7
            or len(n.split()) < 2          # bare surname, e.g. Tesla's "Mr. Musk"
            for n in peo.names
        ):
            # Two independent sources naming different people. Cheap to
            # detect, and exactly the kind of disagreement worth surfacing
            # rather than silently resolving.
            rec.flags.append("ceo_identity_sources_disagree")
        for n in peo.names:
            if not any(names_match(n, c) >= 0.7 for c in candidate_names):
                candidate_names.append(n)
        if peo.transition_detected:
            rec.flags.append("ceo_transition_in_period")
        if peo.suspect_overtagged:
            rec.flags.append("peoname_overtagged_by_filer")

    rec.peo_names = "|".join(candidate_names[:4]) or None

    # Form 4 is opt-in. Section 16 reports under Rule 16a-1(a)(2) (pecuniary
    # interest), a DIFFERENT legal test from 13d-3, so it is not a like-for-
    # like check on the proxy figure. It is also the slowest step by far --
    # up to 250 filings scanned. Enable with --with-form4 to compare.
    f4 = None
    if with_form4:
        try:
            if candidate_names:
                f4 = filing_for_person(client, cik, candidate_names, before=as_of)
            if f4 is None:
                f4 = latest_ceo_filing(client, cik, before=as_of)
                if f4 is not None and rec.ceo_identity_source is None:
                    rec.ceo_identity_source = "form4_title"
                    rec.ceo_identity_evidence = f"officerTitle {f4.officer_title!r}"
                    rec.flags.append("ceo_from_title_heuristic")
        except Exception:  # noqa: BLE001
            pass
        if f4:
            rec.form4_common_shares = f4.total_common
            rec.form4_filing_date = f4.filing_date

    if not candidate_names:
        if "likely_investment_company" in rec.flags:
            rec.error = ("registered investment company or similar: files no "
                         "10-K/10-Q, so no Section 302 certification exists "
                         "and there is no CEO ownership to report -- exclude "
                         "from the universe")
        else:
            rec.error = ("could not identify the CEO: no Section 302 "
                         "certification and no tagged PEO name")
        rec.confidence = "LOW"
        return rec
        if f4.has_exchangeable_units:
            rec.flags.append("upc_exchangeable_units_excluded")
        if f4.unknown_titles:
            rec.flags.append(f"unknown_security_titles:{'|'.join(f4.unknown_titles[:3])}")

    # ---- 4. try to settle it without an API call -----------------------
    table_text = table_to_text(top.html)
    ceo_row = None
    extraction = None

    voting_only_resolved = False
    if llm_mode in ("auto", "never"):
        free = try_free_path(table_text, top.trailing_context, candidate_names)
        rec.escalation_reason = "; ".join(free.reasons) if free.reasons else None
        if free.reasons and "VOTING shares only" in (free.reasons[0] or ""):
            rec.flags.append("proxy_reports_voting_classes_only")
            # The proxy does not contain the answer, so escalating to a model
            # cannot help -- it would read the same incomplete table. Form 4
            # reports every class, including non-voting ones, so use it.
            # Alphabet is the case: Pichai's Class A alone is 227,560 against
            # roughly 3,006,750 once Class C is counted.
            try:
                alt = filing_for_person(client, cik, candidate_names, before=as_of)
            except Exception:  # noqa: BLE001
                alt = None
            if alt and alt.total_common:
                rec.shares_13d3 = alt.total_common
                rec.shares_source = "form4_all_classes"
                rec.ceo_name = alt.owner_name
                rec.ceo_source = "form4_name_match"
                rec.form4_common_shares = alt.total_common
                rec.form4_filing_date = alt.filing_date
                rec.resolution = "form4_fallback"
                rec.flags.append("shares_from_form4_not_proxy")
                free.escalate = False   # settled -- do not fall through to error
                voting_only_resolved = True
        if voting_only_resolved:
            pass  # shares already set from Form 4; skip the proxy row path
        elif not free.escalate:
            ceo_row = free.row
            rec.resolution = "free_path"
            rec.ceo_source = "peo_name_match"
        elif llm_mode == "never":
            rec.resolution = "free_path_failed"
            rec.error = f"free path could not settle it -- {rec.escalation_reason}"
            rec.confidence = "LOW"
            return rec

    # ---- 5. escalate to the model only where genuinely ambiguous -------
    if ceo_row is None and not voting_only_resolved:
        # Targeted extraction when Form 4 named the CEO: one row instead of
        # sixteen, which is where the cost actually lives.
        if f4 and f4.owner_name:
            extraction = extract_target(table_text, top.trailing_context,
                                        f4.owner_name, model=model)
            rec.resolution = "llm_targeted"
        else:
            extraction = extract_ownership(table_text, top.trailing_context,
                                           model=model, pre_rendered=True)
            rec.resolution = "llm_extraction"
        if extraction.error:
            rec.error = f"extraction failed: {extraction.error}"
            rec.confidence = "LOW"
            return rec
        rec.as_of_date = extraction.as_of_date
        if len(extraction.share_classes) > 1:
            rec.flags.append("multi_class")
        if extraction.salvaged:
            rec.flags.append("extraction_truncated_partial_rows")

        ceo_row, source, diagnostic = _pick_ceo_row(
            extraction.rows, f4, candidate_names=candidate_names)
        rec.ceo_source = source
        if ceo_row is None:
            rec.error = f"could not identify CEO row -- {diagnostic}"
            rec.confidence = "LOW"
            return rec

    # The voting-only path took its figure from Form 4, so there is no proxy
    # row to read. Finish the record here rather than falling through to code
    # that dereferences one.
    if voting_only_resolved and ceo_row is None:
        scraped = shares_outstanding_from_proxy(html)
        if scraped["total"]:
            rec.shares_outstanding = scraped["total"]
            rec.share_class_count = len(scraped["per_class"])
            rec.denominator_source = "proxy_text"
        else:
            snap = outstanding_as_of(
                client, cik, as_of=as_of or filing["filing_date"]
            )
            if snap:
                rec.shares_outstanding = snap.total_shares
                rec.share_class_count = snap.class_count
                rec.denominator_source = f"companyfacts:{snap.tag_used}"
        if rec.shares_outstanding:
            rec.pct_comparable = 100.0 * rec.shares_13d3 / rec.shares_outstanding
        # MEDIUM, never HIGH: the figure comes from Form 4, which reports under
        # Rule 16a-1(a)(2) rather than 13d-3, and nothing cross-checks it.
        rec.confidence = "MEDIUM"
        rec.validation = {
            "note": "shares taken from Form 4 because the proxy table reports "
                    "voting classes only; measured under Section 16's "
                    "pecuniary-interest test, not Rule 13d-3"
        }
        return rec

    rec.ceo_name = ceo_row.name_raw
    rec.shares_13d3 = ceo_row.shares_reported
    rec.shares_source = "proxy_item403"
    rec.column_used = ceo_row.notes
    rec.options_60d = ceo_row.options_60d
    rec.unvested_awards = ceo_row.unvested_awards
    rec.exchangeable_units = ceo_row.exchangeable_units
    rec.shares_pledged = ceo_row.shares_pledged
    rec.pct_reported = ceo_row.pct_reported
    rec.pct_voting_power = ceo_row.pct_voting_power
    if ceo_row.shares_pledged:
        rec.flags.append("shares_pledged")
    if ceo_row.exchangeable_units:
        rec.flags.append("holds_exchangeable_units")

    all_rows = extraction.rows if extraction else parse_table_heuristic(table_text)

    # ---- 6. denominator -------------------------------------------------
    # The proxy states the record-date count in prose, on the SAME date as the
    # ownership table. Preferred over companyfacts, which drops the class
    # dimension and so returns nothing at all for multi-class issuers.
    scraped = shares_outstanding_from_proxy(html)
    if scraped["total"]:
        rec.shares_outstanding = scraped["total"]
        rec.share_class_count = len(scraped["per_class"])
        rec.denominator_source = "proxy_text"
    else:
        snap = outstanding_as_of(client, cik, as_of=as_of or filing["filing_date"])
        if snap:
            rec.shares_outstanding = snap.total_shares
            rec.share_class_count = snap.class_count
            rec.denominator_source = f"companyfacts:{snap.tag_used}"
        else:
            # Last resort: back it out of the filer's own arithmetic. Any row
            # stating both a share count and a real percentage implies the
            # denominator, and it needs no external source at all.
            implied = None
            for r in all_rows:
                implied = implied_outstanding(
                    r.shares_reported, r.pct_reported, None
                )
                if implied:
                    break
            if implied:
                rec.shares_outstanding = implied
                rec.denominator_source = "implied_from_table"
                rec.flags.append("denominator_implied")
            else:
                rec.flags.append("no_shares_outstanding")

    if rec.shares_13d3 is not None and rec.shares_outstanding:
        rec.pct_comparable = 100.0 * rec.shares_13d3 / rec.shares_outstanding

    # ---- 7. validate -----------------------------------------------------
    report = ValidationReport()
    # Year-over-year continuity. This is the only numeric check that works on
    # sub-1% holders, whose rows print an asterisk instead of a percentage --
    # which is most large-cap CEOs.
    if continuity:
        cont = check_continuity(
            client, cik, rec.shares_13d3, rec.filing_date, candidate_names
        )
        rec.prior_year_shares = cont.prior_shares
        if cont.change_ratio is not None:
            rec.yoy_change_pct = (cont.change_ratio - 1.0) * 100.0
        report.add(Check(
            "yoy_continuity",
            {"stable": True, "plausible": True,
             "suspicious": False, "skipped": None}[cont.verdict],
            cont.detail,
            value=rec.yoy_change_pct,
        ))
        if cont.verdict == "suspicious":
            rec.flags.append("yoy_discontinuity")

    recon = reconcile_percentage(ceo_row, rec.shares_outstanding)
    report.add(recon)
    # The reconciliation gap measures the 60-day option component, which was
    # previously only obtainable by having a model read the footnotes.
    if recon.passed and recon.value:
        rec.options_60d_implied = recon.value
    report.add(group_bound(ceo_row, _group_row(all_rows)))

    # Identity: does the table row match the name on the Section 302
    # certification? That is the check that confirms the right human, and it
    # needs no Form 4 -- the certification and the proxy are already two
    # independent documents.
    id_score = max(
        (names_match(ceo_row.name_raw, c) for c in candidate_names), default=0.0
    )
    report.add(Check(
        "identity_match",
        id_score >= 0.7,
        f"table row {ceo_row.name_raw!r} vs {rec.ceo_identity_source} "
        f"{candidate_names[0]!r} (score {id_score:.2f})",
        value=id_score,
    ))
    if f4:
        _, divergence = cross_document(ceo_row, f4)
        divergence.name = "form4_divergence_informational"
        report.add(divergence)

    report.confidence = assign_confidence(report, loc_conf)
    if f4 and f4.unknown_titles and report.confidence == "HIGH":
        # An unrecognised security title means shares were EXCLUDED from the
        # numerator without anyone deciding they should be. Alphabet scored
        # HIGH while dropping its Class C Capital Stock.
        report.confidence = "MEDIUM"
        rec.flags.append("excluded_unknown_securities")
    if f4 and f4.co_ceo_detected:
        rec.flags.append("co_ceo_detected")
    if rec.pct_comparable is None and report.confidence == "HIGH":
        # Everything verified but there is no denominator, so there is no
        # output. A row with no percentage cannot be high confidence.
        report.confidence = "MEDIUM"
        rec.flags.append("verified_but_no_percentage")
    report.flags = rec.flags
    rec.confidence = report.confidence
    rec.validation = report.as_dict()
    return rec


def run_tickers(
    tickers: list[str],
    ciks: list[int] | None = None,
    as_of: str | None = None,
    user_agent: str | None = None,
    model: str | None = None,
    llm_mode: str = "auto",
    with_form4: bool = False,
    continuity: bool = True,
) -> list[OwnershipRecord]:
    client = EdgarClient(user_agent=user_agent)
    out: list[OwnershipRecord] = []

    targets: list[tuple[str | None, int | None]] = [(t, None) for t in tickers]
    targets += [(None, c) for c in (ciks or [])]

    for ticker, cik in targets:
        if cik is None:
            try:
                cik = client.resolve_cik(ticker)
            except KeyError as exc:
                out.append(
                    OwnershipRecord(
                        cik=0, ticker=ticker, company=None, ceo_name=None,
                        ceo_source=None, error=str(exc), confidence="LOW",
                    )
                )
                continue
        try:
            rec = build_record(
                client, cik, ticker=ticker, as_of=as_of, model=model,
                llm_mode=llm_mode, with_form4=with_form4, continuity=continuity,
            )
        except Exception as exc:  # noqa: BLE001
            rec = OwnershipRecord(
                cik=cik, ticker=ticker, company=None, ceo_name=None,
                ceo_source=None, error=f"unhandled: {exc}", confidence="LOW",
            )
        out.append(rec)
    return out
