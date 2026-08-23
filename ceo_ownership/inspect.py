"""Diagnostics for a single company.

When `run` fails, this shows the three things that determine why: which
proxy was found, which tables scored highest and why, and what the
extraction actually returned. Use `--no-llm` to see table scoring with no
API call and no cost at all.
"""
from __future__ import annotations

from .edgar import EdgarClient
from .extract import extract_ownership, table_to_text
from .form4 import latest_ceo_filing, filing_for_person
from .peo import extract_peo
from .certification import peo_from_certification
from .outstanding import outstanding_as_of, shares_outstanding_from_proxy
from .proxy import (
    find_proxy_filing,
    load_proxy_html,
    locate_ownership_tables,
    location_confidence,
)
from .validate import names_match


def inspect_ticker(
    ticker: str,
    as_of: str | None = None,
    user_agent: str | None = None,
    use_llm: bool = True,
    table_index: int = 0,
    show_table: bool = False,
    footnote_chars: int = 2500,
    show_form4: bool = False,
) -> None:
    client = EdgarClient(user_agent=user_agent)
    cik = client.resolve_cik(ticker)
    print(f"\n{'=' * 70}\n{ticker}  (CIK {cik})\n{'=' * 70}")

    filing = find_proxy_filing(client, cik, before=as_of)
    print(f"\n1. PROXY")
    print(f"   form         {filing['form']}"
          + ("  [FALLBACK]" if filing["fallback"] else ""))
    print(f"   filed        {filing['filing_date']}")
    print(f"   url          {EdgarClient.filing_dir(cik, filing['accession'])}"
          f"/{filing['primary_document']}")

    html = load_proxy_html(client, filing)
    print(f"   size         {len(html):,} chars")

    cands = locate_ownership_tables(html, top_n=5)
    print(f"\n2. TABLE CANDIDATES  (confidence: {location_confidence(cands)})")
    if not cands:
        print("   none scored above zero -- the table locator failed outright")
        return
    for i, c in enumerate(cands):
        mark = "-->" if i == table_index else "   "
        print(f"{mark} [{i}] score {c.score:5.1f}  {' '.join(c.reasons)}")
        print(f"        text: {c.text[:110]}...")
        print(f"        footnote context: {len(c.trailing_context):,} chars")

    print(f"\n3. CEO IDENTITY")
    candidate_names = []
    cert = peo_from_certification(client, cik, before=as_of)
    if cert:
        print(f"   [PRIMARY] SOX 302 certification")
        print(f"     name       {cert.name!r}")
        print(f"     exhibit    {cert.exhibit_type or '(untyped)'}  {cert.exhibit}")
        print(f"     from       {cert.form} filed {cert.filing_date}"
              f"  (period {cert.period_end})")
        if cert.combined_certification:
            print(f"     NOTE       combined cert, other signers: "
                  f"{cert.other_names_in_doc}")
        candidate_names.append(cert.name)
    else:
        print("   [PRIMARY] SOX 302 certification: NOT FOUND")
        # Show why, so the failure is debuggable without guessing.
        from .certification import _pick_exhibits, PERIODIC_FORMS
        subs = client.submissions(cik)
        recent = [x for x in subs.get("_filings", [])
                  if x.get("form") in PERIODIC_FORMS]
        recent.sort(key=lambda x: x.get("filingDate", ""), reverse=True)
        for x in recent[:2]:
            try:
                idx = client.filing_index(cik, x["accessionNumber"])
            except Exception as exc:  # noqa: BLE001
                print(f"     {x['form']} {x['filingDate']}: index error {exc}")
                continue
            cands = _pick_exhibits(idx)
            print(f"     {x['form']} {x['filingDate']}: "
                  f"{len(cands)} ex-31 candidate(s) {[c[0] for c in cands[:4]]}")

    peo = extract_peo(html)
    if peo.names:
        agree = (not candidate_names) or any(
            names_match(cert.name, n) >= 0.7 for n in peo.names)
        print(f"   [CHECK]   ecd:PeoName -> {peo.primary!r}"
              f"   {'agrees' if agree else 'DISAGREES'}")
        if len(peo.names) > 1:
            print(f"             also tagged {peo.names[1:]}"
                  f"  transition={peo.transition_detected}"
                  f"  overtagged={peo.suspect_overtagged}")
        for n in peo.names:
            if not any(names_match(n, c) >= 0.7 for c in candidate_names):
                candidate_names.append(n)
    else:
        print("   [CHECK]   ecd:PeoName: none (pre-2023 proxy, exempt filer, "
              "or SRC phase-in)")
    print(f"   candidates {candidate_names}")

    print(f"\n4. FORM 4")
    f4 = None
    if candidate_names:
        f4 = filing_for_person(client, cik, candidate_names, before=as_of)
        if f4:
            print(f"   matched via  name {f4.matched_peo_name!r}")
    if f4 is None:
        f4 = latest_ceo_filing(client, cik, before=as_of)
        if f4:
            print(f"   matched via  officerTitle heuristic")
    if f4 is None:
        print("   no Form 3/4/5 found with a CEO-like officerTitle")
    else:
        print(f"   owner        {f4.owner_name!r}")
        print(f"   title        {f4.officer_title!r}")
        print(f"   filed        {f4.filing_date}")
        print(f"   table I      {f4.common_shares:,.0f}")
        print(f"   table II cvt {f4.derivative_common_shares:,.0f}")
        print(f"   TOTAL COMMON {f4.total_common:,.0f}")
        for h in f4.holdings:
            flag = "count" if h.counted else "SKIP "
            print(f"     [{flag}] {h.security_title!r} "
                  f"{h.shares_following} ({h.direct_or_indirect})"
                  + (f"  <- {h.exclusion_reason}" if h.exclusion_reason else ""))
        if f4.derivative_titles:
            print(f"   table II     {f4.derivative_titles[:8]}")
        else:
            print(f"   table II     (empty -- no derivative holdings reported)")
        print(f"   source       {EdgarClient.filing_dir(cik, f4.accession)}")
        for h in f4.holdings:
            if h.nature_of_ownership:
                print(f"     nature: {h.security_title!r} "
                      f"{h.shares_following:,.2f} -> {h.nature_of_ownership!r}")

        if show_form4:
            print(f"\n{'=' * 70}")
            print(f"RAW FORM 4 OWNERSHIP XML  ({f4.accession})")
            print("=" * 70)
            try:
                idx = client.filing_index(cik, f4.accession)
                xml_name = next(
                    (it["name"] for it in idx.get("directory", {}).get("item", [])
                     if it["name"].endswith(".xml")
                     and not it["name"].startswith("xsl")),
                    None,
                )
                if xml_name:
                    raw = client.primary_document(cik, f4.accession, xml_name)
                    print(raw[:20000])
                    if len(raw) > 20000:
                        print(f"\n... truncated, {len(raw) - 20000:,} more chars ...")
                else:
                    print("   could not locate the ownership XML in this filing")
            except Exception as exc:  # noqa: BLE001
                print(f"   error fetching XML: {exc}")
            print()

    print(f"\n5. DENOMINATOR")
    scraped = shares_outstanding_from_proxy(html)
    if scraped["total"]:
        print(f"   from proxy text: {scraped['total']:,.0f}")
        for k, v in scraped["per_class"].items():
            print(f"     {k:<10} {v:,.0f}")
        for m in scraped["matches"][:3]:
            print(f"     matched: ...{m}...")
    else:
        print("   proxy text: no match, falling back to companyfacts")
    snap = outstanding_as_of(client, cik, as_of=as_of or filing["filing_date"])
    if snap:
        print(f"   companyfacts: {snap.total_shares:,.0f} across {snap.class_count} class(es)"
              f"  [{snap.tag_used}, end {snap.end_date}, filed {snap.filed_date}]")
        if snap.class_count > 1:
            print(f"   per class    {[f'{v:,.0f}' for v in snap.per_class]}")
    else:
        print("   NOT FOUND -- listing available share-count tags:")
        try:
            facts = client.company_facts(cik)
            for tax in ("dei", "us-gaap"):
                for tag, body in facts.get("facts", {}).get(tax, {}).items():
                    if "shares" not in tag.lower() and "Shares" not in tag:
                        continue
                    units = list(body.get("units", {}).keys())
                    n = sum(len(v) for v in body.get("units", {}).values())
                    print(f"     {tax}:{tag}  units={units} facts={n}")
        except Exception as exc:  # noqa: BLE001
            print(f"     could not list tags: {exc}")

    if show_table:
        cand = cands[table_index]
        text = table_to_text(cand.html)
        print(f"\n{'=' * 70}")
        print(f"TABLE [{table_index}] AS THE EXTRACTOR SEES IT  "
              f"({len(text):,} chars)")
        print("=" * 70)
        print(text[:12000])
        if len(text) > 12000:
            print(f"\n... truncated, {len(text) - 12000:,} more chars ...")
        print(f"\n{'-' * 70}")
        print(f"FOOTNOTE CONTEXT (first {footnote_chars:,} chars)")
        print("-" * 70)
        print(cand.trailing_context[:footnote_chars])
        print()

    if not use_llm:
        print("\n6. EXTRACTION  (skipped, --no-llm)\n")
        return

    print(f"\n6. EXTRACTION  (table [{table_index}])")
    cand = cands[table_index]
    res = extract_ownership(cand.html, cand.trailing_context)
    if res.error:
        print(f"   ERROR: {res.error}")
        if res.raw_response:
            print(f"   raw response, first 600 chars:\n   {res.raw_response[:600]}")
        return
    if res.salvaged:
        print("   NOTE: response was truncated; recovered the complete rows")
    print(f"   as_of        {res.as_of_date}")
    print(f"   classes      {res.share_classes}")
    print(f"   rows         {len(res.rows)}")
    print()
    header = f"   {'name':<32} {'shares':>14} {'opts60d':>10} {'pct':>7}  flags"
    print(header)
    print("   " + "-" * (len(header) - 3))
    for r in res.rows:
        flags = []
        if r.is_group_row:
            flags.append("GROUP")
        if r.is_five_percent_holder:
            flags.append("5%")
        if r.pct_is_asterisk:
            flags.append("*")
        if r.unvested_awards:
            flags.append(f"unvested={r.unvested_awards:,}")
        score = names_match(r.name_raw, f4.owner_name) if f4 else 0.0
        if score >= 0.7:
            flags.append(f"CEO-MATCH={score:.2f}")
        print(f"   {r.name_raw[:32]:<32} "
              f"{(f'{r.shares_reported:,}' if r.shares_reported else '-'):>14} "
              f"{(f'{r.options_60d:,}' if r.options_60d else '-'):>10} "
              f"{(f'{r.pct_reported}' if r.pct_reported else '-'):>7}  "
              f"{' '.join(flags)}")
    print()
