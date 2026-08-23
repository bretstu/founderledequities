#!/usr/bin/env python3
"""Offline end-to-end demo -- no network, no API key.

Runs the fixture proxy through table location, a canned extraction (standing
in for the model call), and the full validation stack, so you can see the
record shape and the confidence logic before wiring up credentials.

    python3 demo.py
"""
from __future__ import annotations

import json
import os

from ceo_ownership.extract import parse_extraction_response
from ceo_ownership.proxy import locate_ownership_tables, location_confidence
from ceo_ownership.validate import (
    ValidationReport, assign_confidence, group_bound, reconcile_percentage,
)
from ceo_ownership.form4 import parse_ownership_xml
from ceo_ownership.validate import cross_document

FIXTURE = os.path.join("tests", "fixtures", "sample_proxy.html")
SHARES_OUTSTANDING = 122_200_000  # stands in for the companyfacts denominator

# What the model returns for the fixture table, with footnotes decomposed.
CANNED_EXTRACTION = json.dumps({
    "as_of_date": "2025-03-14",
    "share_classes": ["Common Stock"],
    "rows": [
        {"name_raw": "Dana R. Whitfield", "shares_reported": 4812600,
         "pct_reported": 3.9, "options_60d": 1200000,
         "shares_in_trusts_or_indirect": 640000, "unvested_awards": 310000,
         "shares_pledged": 400000, "shares_disclaimed": None,
         "footnote_text": "Includes 1,200,000 shares subject to options..."},
        {"name_raw": "Marcus Ellery", "shares_reported": 612340,
         "pct_reported": None, "pct_is_asterisk": True, "options_60d": 505000},
        {"name_raw": "Priya Raghunathan", "shares_reported": 488115,
         "pct_reported": None, "pct_is_asterisk": True, "options_60d": 300000,
         "shares_disclaimed": 40000},
        {"name_raw": "All directors and executive officers as a group (9 persons)",
         "shares_reported": 6410905, "pct_reported": 5.2, "is_group_row": True},
    ],
})

SAMPLE_FORM4 = open(  # reuse the Form 4 fixture embedded in the tests
    os.path.join("tests", "test_pipeline.py"), encoding="utf-8"
).read().split('SAMPLE_FORM4 = """')[1].split('"""')[0]


def main() -> None:
    with open(FIXTURE, encoding="utf-8") as fh:
        html = fh.read()

    print("=" * 68)
    print("1. TABLE LOCATION")
    print("=" * 68)
    cands = locate_ownership_tables(html)
    for i, c in enumerate(cands):
        label = "<-- selected" if i == 0 else ""
        print(f"  score {c.score:5.1f}  group_row={str(c.has_group_row):<5} "
              f"{' '.join(c.reasons)[:52]:<52} {label}")
    print(f"\n  location confidence: {location_confidence(cands)}")
    print("  (note: fixture heading is 'Ownership of Our Shares' -- a heading")
    print("   regex on the canonical Item 403 phrase would have missed it)")

    print("\n" + "=" * 68)
    print("2. EXTRACTION")
    print("=" * 68)
    res = parse_extraction_response(CANNED_EXTRACTION)
    ceo = res.rows[0]
    group = next(r for r in res.rows if r.is_group_row)
    print(f"  as of:            {res.as_of_date}")
    print(f"  reported shares:  {ceo.shares_reported:,}")
    print(f"  of which options: {ceo.options_60d:,}  (included by 13d-3)")
    print(f"  shares_13d3:      {ceo.shares_reported:,}   <-- the metric")
    print(f"  unvested (excl):  {ceo.unvested_awards:,}")
    print(f"  pledged (flag):   {ceo.shares_pledged:,}")

    print("\n" + "=" * 68)
    print("3. THE TWO PERCENTAGES")
    print("=" * 68)
    comparable = 100.0 * ceo.shares_reported / SHARES_OUTSTANDING
    print(f"  pct_reported   (as filed)      {ceo.pct_reported:.3f}%")
    print(f"  pct_comparable (ours)          {comparable:.3f}%   <- sort on this")
    print("\n  Both use the same 13d-3 figure. They differ because Rule")
    print("  13d-3(d)(1)(i) puts each holder's own 60-day options into THEIR")
    print("  denominator only -- so the filer's percentages are not comparable")
    print("  across companies. pct_comparable uses one denominator for all.")

    print("\n" + "=" * 68)
    print("4. VALIDATION")
    print("=" * 68)
    f4 = parse_ownership_xml(SAMPLE_FORM4, "0001-25-000001", "2025-02-13")
    report = ValidationReport()
    report.add(reconcile_percentage(ceo, SHARES_OUTSTANDING))
    report.add(group_bound(ceo, group))
    identity, divergence = cross_document(ceo, f4)
    report.add(identity)
    report.add(divergence)
    for c in report.checks:
        mark = {True: "PASS", False: "FAIL", None: "SKIP"}[c.passed]
        print(f"  [{mark}] {c.name:<20} {c.detail}")
    report.confidence = assign_confidence(report, location_confidence(cands))
    print(f"\n  CONFIDENCE: {report.confidence}")
    print("\n  Two independent documents agree on both the person and the share")
    print("  count: the proxy says 3,612,600 common after stripping options from")
    print("  footnote (1), and the CEO's own Form 4 Table I says the same. The")
    print("  identity check is the load-bearing one -- pct_reconciliation would")
    print("  have passed just as happily on the CFO's row.")


if __name__ == "__main__":
    main()
