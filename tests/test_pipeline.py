"""Offline tests. No network, no API key required.

These cover the parts most likely to fail silently: which table gets picked,
whether a name matches a human, and whether a security title counts as
ownership.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ceo_ownership.extract import parse_extraction_response
from ceo_ownership.form4 import classify_security, parse_ownership_xml
from ceo_ownership.proxy import locate_ownership_tables, location_confidence
from ceo_ownership.validate import (
    names_match, normalize_name, reconcile_percentage, group_bound,
)

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "sample_proxy.html")


class TestTableLocation(unittest.TestCase):
    def setUp(self):
        with open(FIXTURE, encoding="utf-8") as fh:
            self.html = fh.read()
        self.cands = locate_ownership_tables(self.html)

    def test_picks_ownership_table_not_compensation(self):
        top = self.cands[0]
        self.assertIn("Whitfield", top.text)
        self.assertIn("Percent of Class", top.text)
        # The compensation table is full of dollar signs and must lose.
        self.assertNotIn("$16,050,000", top.text)

    def test_group_row_detected(self):
        self.assertTrue(self.cands[0].has_group_row)

    def test_heading_is_nonstandard_and_still_found(self):
        # Fixture uses "Ownership of Our Shares", not the canonical Item 403
        # heading -- exactly the case a heading regex would miss.
        self.assertIn("Ownership of Our Shares", self.html)
        self.assertEqual(location_confidence(self.cands), "HIGH")

    def test_footnotes_captured_in_trailing_context(self):
        self.assertIn("exercisable within 60 days", self.cands[0].trailing_context)
        self.assertIn("Whitfield Family Trust", self.cands[0].trailing_context)


class TestNameMatching(unittest.TestCase):
    def test_inverted_order(self):
        """Initials are retained -- proxy tables abbreviate given names."""
        self.assertEqual(normalize_name("Iger, Robert A."), ["robert", "a", "iger"])

    def test_nickname(self):
        self.assertGreaterEqual(names_match("Robert Iger", "Bob Iger"), 0.9)

    def test_middle_initial_ignored(self):
        self.assertEqual(names_match("Dana R. Whitfield", "Whitfield, Dana"), 1.0)

    def test_suffix_stripped(self):
        self.assertEqual(names_match("John Smith Jr.", "John Smith"), 1.0)

    def test_different_people_reject(self):
        self.assertEqual(names_match("Dana Whitfield", "Marcus Ellery"), 0.0)

    def test_same_surname_different_first(self):
        # Family members at the same company must not collide.
        self.assertEqual(names_match("Dana Whitfield", "Marcus Whitfield"), 0.0)

    def test_edgar_surname_first_no_comma(self):
        """EDGAR rptOwnerName format. Regression: this silently failed at first."""
        self.assertEqual(names_match("Dana R. Whitfield", "Whitfield Dana R"), 1.0)
        self.assertEqual(names_match("Timothy D. Cook", "Cook Timothy D"), 1.0)
        self.assertGreaterEqual(names_match("Robert A. Iger", "Iger Bob"), 0.9)

    def test_edgar_format_still_rejects_wrong_person(self):
        self.assertEqual(names_match("Dana R. Whitfield", "Whitfield Marcus"), 0.0)
        self.assertEqual(names_match("Dana R. Whitfield", "Ellery Marcus J"), 0.0)


class TestAbbreviatedTableNames(unittest.TestCase):
    """Proxy tables abbreviate given names to an initial.

    Regression: dropping single-character tokens collapsed "J. Duato" to a
    lone surname, which scored 0.60 and fell just under the 0.70 threshold.
    Thirteen companies failed to match a CEO row in a 100-company panel, five
    of them for this reason -- including Johnson & Johnson and GE.
    """

    def test_initial_matches_full_given_name(self):
        self.assertGreaterEqual(names_match("Joaquin Duato", "J. Duato"), 0.7)
        self.assertGreaterEqual(names_match("Pedro Ruiz", "P. Ruiz"), 0.7)

    def test_two_initials_match(self):
        self.assertGreaterEqual(names_match("Robert B. Ford", "R. B. Ford"), 0.7)

    def test_wrong_initial_still_rejected(self):
        self.assertLess(names_match("Alice Brown", "B. Brown"), 0.7)

    def test_surname_alone_stays_below_threshold(self):
        """A bare surname supports a match but cannot confirm it."""
        self.assertLess(names_match("H. Lawrence Culp, Jr.", "Culp"), 0.7)

    def test_existing_formats_unaffected(self):
        for a, b in [("Timothy D. Cook", "COOK TIMOTHY D"),
                     ("Ron M. Vachris", "Vachris Roland Michael"),
                     ("Mark Zuckerberg", "Zuckerberg Mark"),
                     ("Doug McMillon", "McMillon C Douglas")]:
            self.assertGreaterEqual(names_match(a, b), 0.7, f"{a} vs {b}")

    def test_different_people_still_rejected(self):
        self.assertLess(names_match("Mary T. Barra", "Gordon M. Nixon"), 0.7)
        self.assertLess(names_match("Jane Smith", "John Smith"), 0.7)


class TestSecurityClassification(unittest.TestCase):
    def test_common(self):
        for t in ["Common Stock", "Class A Common Stock", "Ordinary Shares",
                  "Common Stock, par value $0.01 per share"]:
            self.assertEqual(classify_security(t)[0], "common", t)

    def test_contingent_excluded(self):
        for t in ["Restricted Stock Units", "Performance Share Units",
                  "Stock Option (right to buy)", "Phantom Stock Units"]:
            self.assertEqual(classify_security(t)[0], "contingent", t)

    def test_upc_flagged_not_counted(self):
        for t in ["LLC Units", "Operating Partnership Units",
                  "Exchangeable Units"]:
            self.assertEqual(classify_security(t)[0], "upc", t)

    def test_unknown_is_excluded_not_assumed(self):
        kind, reason = classify_security("Series C Preferred Widget")
        self.assertEqual(kind, "unknown")
        self.assertIsNotNone(reason)


SAMPLE_FORM4 = """<?xml version="1.0"?>
<ownershipDocument>
  <periodOfReport>2025-02-11</periodOfReport>
  <reportingOwner>
    <reportingOwnerId>
      <rptOwnerCik>0001234567</rptOwnerCik>
      <rptOwnerName>Whitfield Dana R</rptOwnerName>
    </reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector><isOfficer>1</isOfficer>
      <officerTitle>Chief Executive Officer</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>3500000</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>2972600</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
    </nonDerivativeTransaction>
    <nonDerivativeHolding>
      <securityTitle><value>Common Stock</value></securityTitle>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>640000</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
      <ownershipNature>
        <directOrIndirectOwnership><value>I</value></directOrIndirectOwnership>
        <natureOfOwnership><value>By Family Trust</value></natureOfOwnership>
      </ownershipNature>
    </nonDerivativeHolding>
    <nonDerivativeHolding>
      <securityTitle><value>Restricted Stock Units</value></securityTitle>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>310000</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
    </nonDerivativeHolding>
  </nonDerivativeTable>
  <derivativeTable>
    <derivativeHolding>
      <securityTitle><value>Employee Stock Option (Right to Buy)</value></securityTitle>
    </derivativeHolding>
  </derivativeTable>
</ownershipDocument>
"""


class TestForm4Parsing(unittest.TestCase):
    def setUp(self):
        self.rec = parse_ownership_xml(SAMPLE_FORM4, "0001-25-000001", "2025-02-13")

    def test_identifies_ceo(self):
        self.assertTrue(self.rec.looks_like_ceo)
        self.assertEqual(self.rec.owner_name, "Whitfield Dana R")

    def test_same_day_supersedes_earlier_balance(self):
        # Two direct-common entries: the LATER one is the true balance.
        # 2,972,600 direct + 640,000 indirect = 3,612,600.
        # A naive sum would give 7,112,600.
        self.assertEqual(self.rec.common_shares, 3612600.0)

    def test_rsus_in_table_one_excluded(self):
        rsu = [h for h in self.rec.holdings if "Restricted" in h.security_title][0]
        self.assertFalse(rsu.counted)

    def test_indirect_counted(self):
        trust = [h for h in self.rec.holdings if h.direct_or_indirect == "I"][0]
        self.assertTrue(trust.counted)


class TestExtractionParsing(unittest.TestCase):
    def test_null_is_preserved_not_zeroed(self):
        res = parse_extraction_response(
            '{"as_of_date":"2025-03-14","share_classes":["Common Stock"],'
            '"rows":[{"name_raw":"Dana R. Whitfield","shares_reported":"4,812,600",'
            '"pct_reported":3.9,"options_60d":1200000,"shares_disclaimed":null}]}'
        )
        row = res.rows[0]
        self.assertEqual(row.shares_reported, 4812600)
        self.assertIsNone(row.shares_disclaimed)  # must NOT become 0

    def test_common_shares_strips_options_and_disclaimed(self):
        res = parse_extraction_response(
            '{"as_of_date":null,"share_classes":[],"rows":[{"name_raw":"X",'
            '"shares_reported":1000000,"options_60d":300000,"shares_disclaimed":50000}]}'
        )
        self.assertEqual(res.rows[0].common_shares, 650000)

    def test_markdown_fences_tolerated(self):
        res = parse_extraction_response(
            '```json\n{"as_of_date":null,"share_classes":[],"rows":[]}\n```'
        )
        self.assertIsNone(res.error)


class TestValidation(unittest.TestCase):
    def test_reconciliation_uses_per_row_denominator(self):
        """Rule 13d-3(d)(1)(i): the holder's own options inflate their denominator."""
        res = parse_extraction_response(
            '{"as_of_date":null,"share_classes":[],"rows":[{"name_raw":"Dana R. Whitfield",'
            '"shares_reported":4812600,"pct_reported":3.9,"options_60d":1200000}]}'
        )
        row = res.rows[0]
        outstanding = 122_200_000
        check = reconcile_percentage(row, outstanding)
        self.assertTrue(check.passed, check.detail)

        # Ignoring the option adjustment shifts the answer measurably.
        naive = 100.0 * row.shares_reported / outstanding
        self.assertGreater(abs(naive - row.pct_reported), 0.03)

    def test_asterisk_rows_cannot_reconcile(self):
        res = parse_extraction_response(
            '{"as_of_date":null,"share_classes":[],"rows":[{"name_raw":"Y",'
            '"shares_reported":612340,"pct_reported":null,"pct_is_asterisk":true}]}'
        )
        check = reconcile_percentage(res.rows[0], 122_200_000)
        self.assertIsNone(check.passed)  # skipped, not failed

    def test_group_bound_catches_overstatement(self):
        res = parse_extraction_response(
            '{"as_of_date":null,"share_classes":[],"rows":['
            '{"name_raw":"CEO","shares_reported":9000000},'
            '{"name_raw":"group","shares_reported":6410905,"is_group_row":true}]}'
        )
        check = group_bound(res.rows[0], res.rows[1])
        self.assertFalse(check.passed)


class TestDenominator(unittest.TestCase):
    def test_multi_class_summed_from_prose(self):
        from ceo_ownership.outstanding import shares_outstanding_from_proxy as f
        r = f("As of the record date, 2,151,469,000 shares of our Class A common "
              "stock and 342,152,000 shares of our Class B common stock were "
              "outstanding.")
        self.assertEqual(r["total"], 2_493_621_000)
        self.assertEqual(len(r["per_class"]), 2)

    def test_three_classes(self):
        from ceo_ownership.outstanding import shares_outstanding_from_proxy as f
        r = f("There were 5,800,000,000 shares of Class A stock, 860,000,000 "
              "shares of Class B stock, and 5,300,000,000 shares of Class C "
              "stock outstanding.")
        self.assertEqual(len(r["per_class"]), 3)

    def test_option_plan_sentences_rejected(self):
        from ceo_ownership.outstanding import shares_outstanding_from_proxy as f
        r = f("There were 12,000,000 shares reserved for issuance under the "
              "2019 Plan and outstanding awards of 3,400,000 shares.")
        self.assertIsNone(r["total"])

    def test_implied_removes_holder_options(self):
        """13d-3(d)(1)(i): the holder's own options are in THEIR denominator."""
        from ceo_ownership.outstanding import implied_outstanding
        self.assertEqual(implied_outstanding(4_812_600, 3.9, 1_200_000), 122_200_000)
        self.assertIsNone(implied_outstanding(1000, None))


class TestConvertibleCommon(unittest.TestCase):
    def test_class_b_in_table_two_counts(self):
        """Dual-class super-voting shares are derivatives but real ownership."""
        xml = SAMPLE_FORM4.replace(
            "<derivativeHolding>\n      <securityTitle><value>Employee Stock "
            "Option (Right to Buy)</value></securityTitle>\n    </derivativeHolding>",
            "<derivativeHolding>"
            "<securityTitle><value>Class B Common Stock</value></securityTitle>"
            "<postTransactionAmounts><sharesOwnedFollowingTransaction>"
            "<value>50000000</value></sharesOwnedFollowingTransaction>"
            "</postTransactionAmounts></derivativeHolding>")
        rec = parse_ownership_xml(xml, "a", "2025-01-01")
        self.assertEqual(rec.derivative_common_shares, 50_000_000.0)
        self.assertEqual(rec.total_common, 3_612_600 + 50_000_000)
        self.assertTrue(rec.has_convertible_common)

    def test_options_still_excluded_from_table_two(self):
        rec = parse_ownership_xml(SAMPLE_FORM4, "a", "2025-01-01")
        self.assertEqual(rec.derivative_common_shares, 0.0)
        self.assertEqual(rec.total_common, rec.common_shares)


class TestCeoTitleScoring(unittest.TestCase):
    """Divisional CEOs must never be mistaken for the company CEO."""

    def test_company_ceo(self):
        from ceo_ownership.form4 import ceo_title_score as f
        for t in ["Chief Executive Officer", "COB and CEO",
                  "Chairman, President and CEO",
                  "Chief Executive Officer, President and Director",
                  "Chief Executive Officer, Costco Wholesale Corporation"]:
            self.assertEqual(f(t), 100, t)

    def test_co_ceo(self):
        from ceo_ownership.form4 import ceo_title_score as f
        self.assertEqual(f("Co-Chief Executive Officer"), 90)

    def test_divisional_ceo_rejected(self):
        """Regression: Althoff (MSFT) and Petno (JPM) both beat the real CEO."""
        from ceo_ownership.form4 import ceo_title_score as f
        for t in ["CEO, Commercial Business", "CEO Commercial Business",
                  "co-CEO Commercial & Investment Bank", "EVP, CEO Walmart U.S.",
                  "President and CEO, Americas"]:
            self.assertEqual(f(t), 40, t)

    def test_non_ceo(self):
        from ceo_ownership.form4 import ceo_title_score as f
        for t in ["Chief Financial Officer", "Chief Operating Officer",
                  "Executive Vice President", "Director", "See Remarks", None]:
            self.assertEqual(f(t), 0, str(t))


class TestCapitalStock(unittest.TestCase):
    def test_alphabet_capital_stock_counts(self):
        """Regression: Class C Capital Stock was excluded as 'unknown'."""
        self.assertEqual(classify_security("Class C Capital Stock")[0], "common")
        self.assertEqual(classify_security("Capital Stock")[0], "common")

    def test_branded_stock_units_are_contingent(self):
        self.assertEqual(
            classify_security("Class C Google Stock Units")[0], "contingent")


PEO_TRANSITION = """<html><body><ix:header><ix:resources>
<xbrli:context id="a"><xbrli:entity><xbrli:segment><xbrli:explicitMember
 dimension="ecd:IndividualAxis">c:VachrisMember</xbrli:explicitMember>
</xbrli:segment></xbrli:entity><xbrli:period>
<xbrli:endDate>2025-08-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="b"><xbrli:period>
<xbrli:endDate>2024-09-01</xbrli:endDate></xbrli:period></xbrli:context>
</ix:resources></ix:header>
<ix:nonNumeric contextRef="a" name="ecd:PeoName">Ron M. Vachris</ix:nonNumeric>
<ix:nonNumeric contextRef="b" name="ecd:PeoName">W. Craig Jelinek</ix:nonNumeric>
</body></html>"""

PEO_OVERTAGGED = """<html><body><ix:header><ix:resources>
<xbrli:context id="c1"><xbrli:period>
<xbrli:endDate>2025-12-31</xbrli:endDate></xbrli:period></xbrli:context>
</ix:resources></ix:header>
<ix:nonNumeric contextRef="c1" name="ecd:PeoName">Fred W. Bock</ix:nonNumeric>
<ix:nonNumeric contextRef="c1" name="ecd:PeoName">Audie K. Gale</ix:nonNumeric>
<ix:nonNumeric contextRef="c1" name="ecd:PeoName">Florence A. Hood</ix:nonNumeric>
</body></html>"""


class TestPeoExtraction(unittest.TestCase):
    """CEO identity from tagged data, not from free-text titles."""

    def test_most_recent_peo_wins(self):
        from ceo_ownership.peo import extract_peo
        r = extract_peo(PEO_TRANSITION)
        self.assertEqual(r.primary, "Ron M. Vachris")
        self.assertIn("W. Craig Jelinek", r.names)
        self.assertTrue(r.transition_detected)

    def test_overtagging_not_mistaken_for_transition(self):
        """Some filers tag every NEO with ecd:PeoName."""
        from ceo_ownership.peo import extract_peo
        r = extract_peo(PEO_OVERTAGGED)
        self.assertTrue(r.suspect_overtagged)
        self.assertFalse(r.transition_detected)

    def test_absent_tags_return_empty(self):
        from ceo_ownership.peo import extract_peo
        r = extract_peo("<html><body><p>No XBRL here.</p></body></html>")
        self.assertEqual(r.names, [])
        self.assertIsNone(r.primary)

    def test_undimensioned_single_peo(self):
        from ceo_ownership.peo import extract_peo
        r = extract_peo('<html><body><ix:nonNumeric name="ecd:PeoName">'
                        'Satya Nadella</ix:nonNumeric></body></html>')
        self.assertEqual(r.primary, "Satya Nadella")


# Real table structures, taken verbatim from the 2026 proxies. Four filers,
# four different column layouts -- this is the regression set that matters.
REAL_TABLES = {
    "COST": """Name of Beneficial Owner | Shares Beneficially Owned 1 | Percent of Class 2
Ron M. Vachris | 52,258 | *
Helena B. Foulkes | 1,126 (3) | *
All directors and executive officers as a group (23 persons) | 460,270 | *""",

    "MSFT": """Beneficial Ownership
Name | Common Stock 1,2 | Percent of Common Stock | Additional Underlying Shares or Stock Units 3,4 | Total 5
Reid G. Hoffman | 15,905 | 6 | * | 16,217 | 32,122
Catherine MacGregor | 0 | * | 1,487 | 1,487
Satya Nadella | 900,572 | 12 | * | 0 | 900,572
Directors and Executive Officers as a Group (18 people) | 2,279,620 | 13 | * | N/A | N/A""",

    "JPM": """Beneficial ownership
Name | Common stock (#) 1 | SARs/Options exercisable within 60 days (#) | Total beneficial ownership (#) | Additional underlying stock units (#) 2 | Total (#)
Michele G. Buck | 5 | \u2014 | 5 | 914 | 919
James Dimon 3 | 6,266,647 | \u2014 | 6,266,647 | 653,426 | 6,920,073
All directors, nominees and current executive officers as a group (21 persons) 3 | 8,573,082 | \u2014 | 8,573,082 | 2,518,835 | 11,091,917""",

    "WMT": """Name of Beneficial Owner | Direct or Indirect with Sole Voting and Dispositive Power (1)(2) | Indirect with Shared Voting and Dispositive Power | Total | Percent of Class
Tim Flynn | 156,945 | (3) | - | 156,945 | *
John Furner | 342,311 | 132,850 | (10) | 475,161 | *
Doug McMillon | 1,243,874 | 1,053,909 | (11) | 2,297,783 | *
Directors, Director Nominees, and Executive Officers as a Group (24 persons) | 5,642,495 | 1,402,466 | 7,044,961 | *""",
}


class TestThirteenDThreeSelection(unittest.TestCase):
    """Rule 13d-3 = holdings PLUS anything acquirable within 60 days.

    Where a filer breaks those into separate columns they must be ADDED.
    Columns the filer marks as NOT beneficially owned are always excluded.
    """

    def test_explicit_total_beneficial_column_wins(self):
        from ceo_ownership.freepath import parse_table_heuristic
        t = ("Name | Common stock (#) 1 | SARs/Options exercisable within 60 "
             "days (#) | Total beneficial ownership (#) | Additional "
             "underlying stock units (#) 2 | Total (#)\n"
             "James Dimon 3 | 6,266,647 | \u2014 | 6,266,647 | 653,426 | 6,920,073")
        r = parse_table_heuristic(t)[0]
        self.assertEqual(r.shares_reported, 6_266_647)
        self.assertEqual(r.notes, "column=total_beneficial")

    def test_options_column_is_added_not_chosen(self):
        """13d-3 deems 60-day acquirables owned, so they belong in the total."""
        from ceo_ownership.freepath import parse_table_heuristic
        t = ("Name | Common stock | Options exercisable within 60 days | Percent\n"
             "Jane Roe | 1,000,000 | 250,000 | 2.1")
        r = parse_table_heuristic(t)[0]
        self.assertEqual(r.shares_reported, 1_250_000)
        self.assertIn("options60d", r.notes)

    def test_unvested_units_column_excluded(self):
        """"Additional Underlying Shares or Stock Units" is explicitly not
        beneficially owned -- Microsoft says so in footnotes 3 and 4."""
        from ceo_ownership.freepath import parse_table_heuristic
        t = ("Name | Common Stock 1,2 | Percent of Common Stock | Additional "
             "Underlying Shares or Stock Units 3,4 | Total 5\n"
             "Amy E. Hood | 465,746 | * | 65,398 | 531,144")
        r = parse_table_heuristic(t)[0]
        self.assertEqual(r.shares_reported, 465_746)

    def test_tesla_single_column_includes_options_as_filed(self):
        """Musk's 717,323,438 includes 303.9M 60-day options. Under 13d-3 that
        is correct as filed -- the old common-only metric had no clean answer."""
        from ceo_ownership.freepath import parse_table_heuristic
        t = ("Beneficial Owner Name | Shares Beneficially Owned | Percentage "
             "of Shares Beneficially Owned\n"
             "Elon Musk (1) | 717,323,438 | 19.8 %")
        r = parse_table_heuristic(t)[0]
        self.assertEqual(r.shares_reported, 717_323_438)
        self.assertEqual(r.pct_reported, 19.8)


class TestPanelCheckpoint(unittest.TestCase):
    """A long run will be interrupted; the checkpoint must survive it."""

    def setUp(self):
        import tempfile, os
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "panel.jsonl")

    def test_roundtrip(self):
        from ceo_ownership.panel import append_record, load_completed
        append_record(self.path, {"cik": 320193, "shares_13d3": 3280295})
        append_record(self.path, {"cik": 1326801, "shares_13d3": 342463325})
        done = load_completed(self.path)
        self.assertEqual(sorted(done), [320193, 1326801])

    def test_truncated_final_line_discarded(self):
        """A hard kill mid-write must cost at most one row, not the file."""
        from ceo_ownership.panel import append_record, load_completed
        append_record(self.path, {"cik": 1, "shares_13d3": 10})
        append_record(self.path, {"cik": 2, "shares_13d3": 20})
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write('{"cik": 3, "compa')
        done = load_completed(self.path)
        self.assertEqual(sorted(done), [1, 2])

    def test_missing_file_is_empty_not_an_error(self):
        from ceo_ownership.panel import load_completed
        self.assertEqual(load_completed("/no/such/file.jsonl"), {})


class TestTriage(unittest.TestCase):
    """Collapse per-company stories into recurring signatures."""

    def test_signature_strips_company_detail(self):
        """Five companies failing one way must look like one bug, not five."""
        from ceo_ownership.triage import _signature
        a = _signature("free path could not settle it -- CEO row not found: "
                       "15 candidates, best match 0.00 for 'Mary T. Barra'")
        b = _signature("free path could not settle it -- CEO row not found: "
                       "8 candidates, best match 0.00 for 'Gordon M. Nixon'")
        self.assertEqual(a, b)

    def test_different_causes_stay_separate(self):
        from ceo_ownership.triage import _signature
        self.assertNotEqual(
            _signature("x -- CEO row not found: 3 candidates"),
            _signature("x -- heuristic parse found no rows"))

    def test_report_covers_untrusted_figures(self):
        from ceo_ownership.triage import triage
        recs = [{"cik": 1, "company": "A", "shares_13d3": 100,
                 "pct_comparable": 1.0, "confidence": "LOW",
                 "validation": {"checks": [
                     {"name": "pct_reconciliation", "passed": False,
                      "detail": "denominator below outstanding"}]}}]
        out = triage(recs)
        self.assertIn("FIGURES PRODUCED BUT NOT TRUSTED", out)
        self.assertIn("pct_reconciliation", out)

    def test_check_coverage_reported(self):
        """A check that mostly skips is not protecting anything."""
        from ceo_ownership.triage import triage
        recs = [{"cik": i, "company": "C", "shares_13d3": 1,
                 "pct_comparable": 1.0, "confidence": "HIGH",
                 "validation": {"checks": [
                     {"name": "pct_reconciliation", "passed": None},
                     {"name": "yoy_continuity", "passed": True}]}}
                for i in range(3)]
        out = triage(recs)
        self.assertIn("CHECK COVERAGE", out)

    def test_empty_input(self):
        from ceo_ownership.triage import triage
        self.assertIn("PANEL TRIAGE", triage([]))


class TestPublicSite(unittest.TestCase):
    """The public page must never show a row it cannot stand behind."""

    def _recs(self):
        return [
            {"cik": 1, "company": "Alpha", "ticker": "ALP", "ceo_name": "A Founder",
             "shares_13d3": 5_000_000, "pct_comparable": 12.5,
             "confidence": "HIGH", "source_url": "https://sec.gov/1",
             "filing_date": "2026-04-01"},
            {"cik": 2, "company": "Beta", "ceo_name": "B Manager",
             "shares_13d3": 900, "pct_comparable": 0.004,
             "confidence": "MEDIUM", "source_url": ""},
            {"cik": 3, "company": "Broken", "error": "could not read",
             "pct_comparable": None, "confidence": "LOW"},
            {"cik": 4, "company": "NoCeo", "ceo_name": None,
             "pct_comparable": 3.0, "confidence": "HIGH"},
        ]

    def test_errored_and_ceo_less_rows_excluded(self):
        from ceo_ownership.site import _rows_from_records
        rows = _rows_from_records(self._recs())
        self.assertEqual([r["co"] for r in rows], ["Alpha", "Beta"])

    def test_sorted_by_ownership(self):
        from ceo_ownership.site import _rows_from_records
        rows = _rows_from_records(self._recs())
        self.assertGreater(rows[0]["pct"], rows[1]["pct"])

    def test_quality_marker_set_for_non_high(self):
        from ceo_ownership.site import _rows_from_records
        rows = _rows_from_records(self._recs())
        self.assertEqual(rows[0]["q"], 0)
        self.assertEqual(rows[1]["q"], 1)

    def test_output_is_self_contained(self):
        from ceo_ownership.site import build_site
        out = build_site(self._recs())
        self.assertIn("A Founder", out)
        self.assertNotIn("{{DATA}}", out)
        self.assertNotIn("Broken", out)

    def test_empty_input_still_renders(self):
        from ceo_ownership.site import build_site
        out = build_site([])
        self.assertIn("<html", out)
        self.assertIn("const DATA = []", out)


class TestRedoModes(unittest.TestCase):
    """After a fix, affected companies must actually be reprocessed."""

    def setUp(self):
        import tempfile, os
        from ceo_ownership.panel import append_record
        self.path = os.path.join(tempfile.mkdtemp(), "p.jsonl")
        append_record(self.path, {"cik": 1, "shares_13d3": 100})
        append_record(self.path, {"cik": 2, "error": "could not read"})
        append_record(self.path, {"cik": 3, "shares_13d3": 300})

    def _todo(self, redo):
        from ceo_ownership.panel import load_completed
        done = load_completed(self.path)
        if redo == "all":
            done = {}
        elif redo == "failed":
            done = {k: v for k, v in done.items() if not v.get("error")}
        return [c for c in (1, 2, 3, 4) if c not in done]

    def test_none_skips_everything_done(self):
        self.assertEqual(self._todo("none"), [4])

    def test_failed_retries_only_errors(self):
        self.assertEqual(self._todo("failed"), [2, 4])

    def test_all_reprocesses_everything(self):
        self.assertEqual(self._todo("all"), [1, 2, 3, 4])

    def test_later_row_supersedes_earlier(self):
        """Re-running appends; last entry per CIK wins, so no file rewrite."""
        from ceo_ownership.panel import append_record, load_completed
        append_record(self.path, {"cik": 2, "shares_13d3": 222})
        self.assertEqual(load_completed(self.path)[2]["shares_13d3"], 222)


class TestFilerClassification(unittest.TestCase):
    """Classification must never exclude an equity by mistake."""

    class _FakeClient:
        def __init__(self, forms):
            self.forms = forms

        def submissions(self, cik):
            return {"_filings": [{"form": f} for f in self.forms]}

    def _kind(self, forms):
        from ceo_ownership.panel import classify_filer
        return classify_filer(self._FakeClient(forms), 1)[0]

    def test_operating_company(self):
        self.assertEqual(self._kind(["10-K", "10-Q", "8-K"]), "operating")

    def test_bdc_files_both_and_counts_as_operating(self):
        """A business development company files a 10-K AND an N-2, and has a
        real chief executive. Testing fund forms first would misclassify it."""
        self.assertEqual(self._kind(["10-K", "N-2", "N-54A"]), "operating")

    def test_foreign_private_issuer_kept(self):
        """FPIs file 20-F instead of a 10-K. Treating a missing 10-K as
        disqualifying would drop every ADR."""
        self.assertEqual(self._kind(["20-F", "6-K"]), "foreign_private_issuer")
        self.assertEqual(self._kind(["40-F"]), "foreign_private_issuer")

    def test_older_small_business_forms_kept(self):
        self.assertEqual(self._kind(["10-KSB", "10-QSB"]), "operating")

    def test_registered_investment_company(self):
        self.assertEqual(self._kind(["N-CSR", "N-CEN", "DEF 14A"]),
                         "investment_company")

    def test_absence_is_unknown_not_excluded(self):
        """Absence of a 10-K has innocent causes: a proxy filed before the
        first annual report, a Reg A+ issuer, a truncated filing history."""
        self.assertEqual(self._kind(["DEF 14A", "8-K"]), "unknown")
        self.assertEqual(self._kind([]), "unknown")

    def test_skip_is_off_by_default(self):
        import inspect as _inspect
        from ceo_ownership.panel import build_panel
        sig = _inspect.signature(build_panel)
        self.assertIs(sig.parameters["skip_non_operating"].default, False)

    def test_hms_formatting(self):
        from ceo_ownership.panel import _hms
        self.assertEqual(_hms(0), "0:00:00")
        self.assertEqual(_hms(3661), "1:01:01")


class TestWorksheetLossGuard(unittest.TestCase):
    """A guard must not share a code path with the failure it guards against.

    Two afternoons of checking were lost because the "would this lose data?"
    check counted answers using the same reader that had just failed to find
    them: it compared zero against zero, saw no loss, and wrote.
    """

    def setUp(self):
        import tempfile, os
        self.dir = tempfile.mkdtemp()
        self.ws = os.path.join(self.dir, "worksheet.csv")
        self.recs = [{"cik": c, "company": f"Co {c}", "ceo_name": "P",
                      "shares_13d3": 100, "pct_comparable": 1.0,
                      "shares_outstanding": 5e6, "confidence": "HIGH",
                      "flags": [], "error": None, "validation": {"checks": []}}
                     for c in (1023313, 1318605, 1321655)]

    def _write(self, **kw):
        from ceo_ownership.verify import build_sample, write_worksheet
        return write_worksheet(build_sample(self.recs, include_all=True),
                               self.ws, **kw)

    def _fill(self, cik_as=None):
        import csv
        rows = list(csv.DictReader(open(self.ws, newline="", encoding="utf-8-sig")))
        for r in rows:
            if cik_as:
                r["cik"] = cik_as
            r["actual_shares"] = "93,675,251"
        with open(self.ws, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)

    def test_cik_parsing_survives_excel_formats(self):
        from ceo_ownership.verify import _parse_cik
        self.assertEqual(_parse_cik("1321655"), 1321655)
        self.assertEqual(_parse_cik(" 1321655 "), 1321655)
        self.assertEqual(_parse_cik("1321655.0"), 1321655)
        self.assertEqual(_parse_cik("1,321,655"), 1321655)
        self.assertIsNotNone(_parse_cik("1.32166E+06"))
        self.assertIsNone(_parse_cik(""))
        self.assertIsNone(_parse_cik("abc"))

    def test_raw_count_is_independent_of_the_parser(self):
        self._write()
        self._fill()
        from ceo_ownership.verify import raw_answer_count
        self.assertEqual(raw_answer_count(self.ws), 3)

    def test_write_refused_when_recovery_fails(self):
        """The decisive case: if the answers cannot be read back, do not
        write. Previously this wrote an empty sheet without a word."""
        import ceo_ownership.verify as V
        from ceo_ownership.verify import WorksheetOpenError, raw_answer_count
        self._write()
        self._fill()
        orig_h = V.load_hand_entered
        V.load_hand_entered = lambda p: {}
        try:
            with self.assertRaises(WorksheetOpenError):
                self._write()
        finally:
            V.load_hand_entered = orig_h
        self.assertEqual(raw_answer_count(self.ws), 3)   # untouched

    def test_force_still_allows_it(self):
        import ceo_ownership.verify as V
        self._write()
        self._fill()
        orig = V.load_hand_entered
        V.load_hand_entered = lambda p: {}
        try:
            self._write(force=True)
        finally:
            V.load_hand_entered = orig

    def test_normal_round_trip_unaffected(self):
        from ceo_ownership.verify import raw_answer_count
        self._write()
        self._fill()
        self._write()
        self.assertEqual(raw_answer_count(self.ws), 3)


class TestAnswersAreDurable(unittest.TestCase):
    """Hand-entered answers must survive anything done to the worksheet.

    The worksheet was previously a read-modify-write of the same file: values
    were recovered from the copy about to be overwritten. Any failure in that
    read -- an Excel re-save, an encoding change, a lock -- destroyed them,
    with no copy anywhere. An afternoon of reading filings is not something to
    stake on a merge.
    """

    def setUp(self):
        import tempfile, os
        self.dir = tempfile.mkdtemp()
        self.ws = os.path.join(self.dir, "worksheet.csv")
        self.recs = [{"cik": c, "company": f"Co {c}", "ceo_name": "A Person",
                      "shares_13d3": 1000 + c, "pct_comparable": 1.0,
                      "shares_outstanding": 5_000_000, "confidence": "HIGH",
                      "flags": [], "error": None, "validation": {"checks": []}}
                     for c in (1023313, 1318605, 1321655)]

    def _write(self):
        from ceo_ownership.verify import build_sample, write_worksheet
        return write_worksheet(build_sample(self.recs, include_all=True), self.ws)

    def _fill(self, encoding="utf-8"):
        import csv
        rows = list(csv.DictReader(open(self.ws, newline="", encoding="utf-8-sig")))
        for r in rows:
            r["actual_shares"] = "7,380,411"
            r["actual_outstanding"] = "19,175,893"
        with open(self.ws, "w", newline="", encoding=encoding) as fh:
            w = csv.DictWriter(fh, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)

    def _read_back(self):
        import csv
        return list(csv.DictReader(open(self.ws, newline="", encoding="utf-8-sig")))

    def test_numbers_survive_regeneration(self):
        self._write()
        self._fill()
        self._write()
        rows = self._read_back()
        self.assertTrue(all(r["actual_shares"] for r in rows))
        self.assertTrue(all(r["actual_outstanding"] for r in rows))

    def test_survives_excel_style_bom(self):
        """Excel writes a BOM when saving a CSV, which would otherwise
        corrupt the first header and lose that column."""
        self._write()
        self._fill(encoding="utf-8-sig")
        self._write()
        self.assertTrue(all(r["actual_shares"] for r in self._read_back()))

    def test_no_files_are_left_behind(self):
        """No backup copies, no shadow answers file. Neither addressed the
        failure that motivated them -- nothing can recover data that never
        reached disk -- and both cluttered the working directory."""
        import os
        self._write()
        self._fill()
        self._write()
        self.assertEqual(sorted(os.listdir(self.dir)), ["worksheet.csv"])

    def test_refuses_while_open_in_excel(self):
        """Values typed but not saved are not on disk. Rewriting the file
        discards them and no merge can recover them, so do not rewrite."""
        import os
        from ceo_ownership.verify import WorksheetOpenError
        self._write()
        self._fill()
        lock = os.path.join(self.dir, "~$worksheet.csv")
        open(lock, "w").close()
        try:
            with self.assertRaises(WorksheetOpenError):
                self._write()
        finally:
            os.remove(lock)

    def test_force_overrides_the_lock(self):
        import os
        from ceo_ownership.verify import build_sample, write_worksheet
        self._write()
        self._fill()
        lock = os.path.join(self.dir, "~$worksheet.csv")
        open(lock, "w").close()
        try:
            write_worksheet(build_sample(self.recs, include_all=True),
                            self.ws, force=True)
        finally:
            os.remove(lock)

    def test_counts_reported_per_column(self):
        """A partial loss must be visible immediately, not discovered later."""
        from ceo_ownership.verify import answer_counts
        self._write()
        self._fill()
        self._write()
        counts = answer_counts(self.ws)
        self.assertEqual(counts["actual_shares"], 3)
        self.assertEqual(counts["actual_outstanding"], 3)


class TestWorksheetPersistence(unittest.TestCase):
    """Regenerating must carry hand-entered answers forward."""

    def setUp(self):
        import tempfile, os
        self.path = os.path.join(tempfile.mkdtemp(), "w.csv")
        self.recs = [{"cik": i, "company": f"Co {i}", "ceo_name": "A Person",
                      "shares_13d3": 1000 + i, "pct_comparable": 0.5,
                      "confidence": "HIGH", "flags": [], "error": None,
                      "validation": {"checks": [
                          {"name": "pct_reconciliation", "passed": None},
                          {"name": "yoy_continuity", "passed": True}]}}
                     for i in range(1, 21)]

    def _write(self):
        from ceo_ownership.verify import build_sample, write_worksheet
        return write_worksheet(build_sample(self.recs, include_all=True),
                               self.path)

    def _fill(self, n):
        import csv
        with open(self.path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        for r in rows[:n]:
            r["actual_shares"] = r["reported_shares"]
            r["notes"] = "checked by hand"
        with open(self.path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)

    def test_include_all_lists_every_company(self):
        from ceo_ownership.verify import build_sample
        self.assertEqual(len(build_sample(self.recs, include_all=True)), 20)

    def test_no_duplicates(self):
        from ceo_ownership.verify import build_sample
        ciks = [r["cik"] for r in build_sample(self.recs, include_all=True)]
        self.assertEqual(len(ciks), len(set(ciks)))

    def test_hand_entered_survives_regeneration(self):
        self._write()
        self._fill(3)
        self.assertEqual(self._write(), 3)

    def test_pipeline_columns_refresh_answers_do_not(self):
        """After a parser fix, the pipeline figure updates while the
        hand-checked answer stays -- so accuracy can be re-scored without
        re-reading a single filing."""
        import csv
        self._write()
        self._fill(2)
        for r in self.recs:
            r["shares_13d3"] += 7
        self._write()
        with open(self.path, newline="", encoding="utf-8") as fh:
            rows = [r for r in csv.DictReader(fh) if r["actual_shares"]]
        self.assertEqual(len(rows), 2)
        for r in rows:
            self.assertNotEqual(r["reported_shares"], r["actual_shares"])
            self.assertEqual(r["notes"], "checked by hand")

    def test_first_write_preserves_nothing(self):
        self.assertEqual(self._write(), 0)


class TestVerificationSampling(unittest.TestCase):
    """The sample is aimed at what the automatic checks could not establish."""

    def _rec(self, cik, conf, recon, cont, pct=0.5, flags=None, err=None):
        return {"cik": cik, "company": f"Co {cik}", "ceo_name": "Jane Doe",
                "shares_13d3": 1000, "pct_comparable": pct,
                "confidence": conf, "flags": flags or [], "error": err,
                "validation": {"checks": [
                    {"name": "pct_reconciliation", "passed": recon},
                    {"name": "yoy_continuity", "passed": cont}]}}

    def test_reconciled_rows_identified(self):
        from ceo_ownership.verify import assign_stratum
        self.assertEqual(
            assign_stratum(self._rec(1, "HIGH", True, True)), "reconciled")

    def test_continuity_only_is_the_blind_spot(self):
        """No printed percentage means the share count was never checked
        against an independent statement of it."""
        from ceo_ownership.verify import assign_stratum
        self.assertEqual(
            assign_stratum(self._rec(2, "HIGH", None, True)), "continuity_only")

    def test_errors_and_low_go_to_failed(self):
        from ceo_ownership.verify import assign_stratum
        self.assertEqual(
            assign_stratum(self._rec(3, "LOW", None, None)), "failed")
        self.assertEqual(
            assign_stratum(self._rec(4, "HIGH", True, True, err="x")), "failed")

    def test_largest_holding_is_included(self):
        from ceo_ownership.verify import build_sample
        records = [self._rec(i, "HIGH", True, True, pct=0.01) for i in range(1, 60)]
        records.append(self._rec(999, "HIGH", True, True, pct=42.0))
        rows = build_sample(records, include_all=True)
        self.assertIn(999, [int(r["cik"]) for r in rows])

    def test_no_company_sampled_twice(self):
        from ceo_ownership.verify import build_sample
        records = ([self._rec(i, "HIGH", None, True, pct=i / 10)
                    for i in range(1, 200)])
        rows = build_sample(records)
        ciks = [r["cik"] for r in rows]
        self.assertEqual(len(ciks), len(set(ciks)))


class TestContinuityBands(unittest.TestCase):
    """Thresholds are asymmetric: holdings can double, they cannot evaporate."""

    def _verdict(self, prior, cur):
        import ceo_ownership.continuity as C
        ratio = cur / prior
        change = abs(ratio - 1.0)
        if C._looks_like_scale_error(ratio):
            return "suspicious"
        if change <= C.STABLE_BAND:
            return "stable"
        if ratio > 1 and (ratio - 1) <= C.MAX_PLAUSIBLE_INCREASE:
            return "plausible"
        if ratio < 1 and (1 - ratio) <= C.MAX_PLAUSIBLE_DECREASE:
            return "plausible"
        return "suspicious"

    def test_ordinary_drift_is_stable(self):
        self.assertEqual(self._verdict(3_280_180, 3_280_295), "stable")   # AAPL
        self.assertEqual(self._verdict(44_677, 52_258), "stable")         # COST
        self.assertEqual(self._verdict(922_922_938, 870_604_104), "stable")  # NVDA

    def test_doubling_is_plausible(self):
        self.assertEqual(self._verdict(100_000, 195_000), "plausible")

    def test_oracle_collapse_is_suspicious(self):
        """Regression: -97.3% passed as "plausible" because a symmetric band
        of abs(ratio-1) <= 1.0 admits any decrease at all."""
        self.assertEqual(self._verdict(8_618_592, 228_695), "suspicious")

    def test_moderate_sale_still_plausible(self):
        self.assertEqual(self._verdict(100_000, 52_000), "plausible")

    def test_large_collapse_suspicious(self):
        self.assertEqual(self._verdict(100_000, 20_000), "suspicious")


class TestScaleDetection(unittest.TestCase):
    def test_powers_of_ten_flagged(self):
        from ceo_ownership.continuity import _looks_like_scale_error as f
        self.assertEqual(f(10.0), 10.0)
        self.assertEqual(f(0.1), 0.1)
        self.assertEqual(f(100.4), 100.0)
        self.assertEqual(f(1000.0), 1000.0)

    def test_ordinary_changes_not_flagged(self):
        from ceo_ownership.continuity import _looks_like_scale_error as f
        for r in (1.0, 1.15, 0.92, 2.4, 0.5, 7.0):
            self.assertIsNone(f(r), r)

    def test_date_helper(self):
        from ceo_ownership.continuity import _minus_one_day as f
        self.assertEqual(f("2026-04-16"), "2026-04-15")
        self.assertEqual(f("2026-01-01"), "2025-12-31")
        self.assertEqual(f("garbage"), "garbage")


class TestGroupPercentageCheck(unittest.TestCase):
    """Recovers numeric coverage where the CEO's own percentage is an asterisk.

    89 of 98 rows in a 100-company panel could not run the individual
    reconciliation, because most CEOs hold under one percent and the filer
    prints an asterisk. The group row usually does carry a figure.
    """

    def _grp(self, shares, pct=None, asterisk=False):
        from ceo_ownership.extract import OwnershipRow
        return OwnershipRow(name_raw="directors and officers as a group",
                            shares_reported=shares, pct_reported=pct,
                            pct_is_asterisk=asterisk, is_group_row=True)

    def test_cabot_group_reconciles(self):
        """Cabot: 1,647,720 reported as 3.08% of 52,221,604."""
        from ceo_ownership.validate import group_percentage_check as g
        c = g(self._grp(1_647_720, 3.08), 52_221_604)
        self.assertTrue(c.passed)
        self.assertIn("denominator confirmed", c.detail)

    def test_wrong_denominator_caught(self):
        from ceo_ownership.validate import group_percentage_check as g
        self.assertFalse(g(self._grp(1_647_720, 8.0), 52_221_604).passed)

    def test_positive_gap_allowed(self):
        """The group's own 60-day options inflate their denominator, so
        computing HIGHER than the filing is expected."""
        from ceo_ownership.validate import group_percentage_check as g
        self.assertTrue(g(self._grp(1_000_000, 4.0), 24_000_000).passed)

    def test_asterisk_group_skips(self):
        from ceo_ownership.validate import group_percentage_check as g
        self.assertIsNone(g(self._grp(460_270, asterisk=True), 443_957_682).passed)

    def test_absent_group_skips(self):
        from ceo_ownership.validate import group_percentage_check as g
        self.assertIsNone(g(None, 1_000_000).passed)

    def test_counts_toward_high_confidence(self):
        from ceo_ownership.validate import ValidationReport, Check, assign_confidence
        rep = ValidationReport()
        rep.add(Check("identity_match", True, ""))
        rep.add(Check("pct_reconciliation", None, "asterisk"))
        rep.add(Check("yoy_continuity", None, "no prior year"))
        rep.add(Check("group_pct_reconciliation", True, ""))
        self.assertEqual(assign_confidence(rep, "HIGH"), "HIGH")


class TestReconciliationInfersOptions(unittest.TestCase):
    """The denominator gap is a measurement, not an error.

    Rule 13d-3(d)(1)(i) puts a holder's own 60-day options in THEIR
    denominator only, so shares/pct - outstanding = those options.
    """

    def _row(self, shares, pct):
        from ceo_ownership.extract import OwnershipRow
        return OwnershipRow(name_raw="X", shares_reported=shares, pct_reported=pct)

    def test_tesla_gap_recovers_footnoted_option_count(self):
        """Musk: 717,323,438 at 19.8% against 3,325,150,886 outstanding.
        The footnote says 303,960,630 options; the implied band must cover it."""
        from ceo_ownership.validate import reconcile_percentage
        c = reconcile_percentage(self._row(717_323_438, 19.8), 3_325_150_886)
        self.assertTrue(c.passed)
        self.assertAlmostEqual(c.value, 297_717_863, delta=1_000)
        self.assertIn("288,569,205-306,866,522", c.detail)  # band covers 303.9M

    def test_clean_match_implies_no_options(self):
        from ceo_ownership.validate import reconcile_percentage
        c = reconcile_percentage(self._row(870_604_104, 3.58), 24_312_141_810)
        self.assertTrue(c.passed)
        self.assertEqual(c.value, 0.0)

    def test_implied_options_cannot_exceed_the_holding(self):
        """13d-3 counts options inside the reported figure, so they are a
        subset of it. A larger implied value means something is wrong."""
        from ceo_ownership.validate import reconcile_percentage
        c = reconcile_percentage(self._row(900_000_000, 19.8), 3_325_150_886)
        self.assertFalse(c.passed)
        self.assertIn("impossible", c.detail)

    def test_denominator_below_outstanding_fails(self):
        from ceo_ownership.validate import reconcile_percentage
        c = reconcile_percentage(self._row(1_000_000, 50.0), 10_000_000)
        self.assertFalse(c.passed)
        self.assertIn("BELOW shares outstanding", c.detail)

    def test_asterisk_still_skipped(self):
        from ceo_ownership.extract import OwnershipRow
        from ceo_ownership.validate import reconcile_percentage
        row = OwnershipRow(name_raw="X", shares_reported=5_000,
                           pct_reported=None, pct_is_asterisk=True)
        self.assertIsNone(reconcile_percentage(row, 1_000_000).passed)


class TestZeroWidthPadding(unittest.TestCase):
    """Tesla pads every cell with U+200B zero-width spaces."""

    ZW = "\u200b"

    def _tsla(self):
        z = self.ZW
        return (f"Beneficial Owner Name | {z} | {z} | Shares Beneficially Owned "
                f"| {z} | {z} | Percentage of Shares Beneficially Owned | {z}\n"
                f"Elon Musk (1) | {z} | {z} | {z} | {z} | 717,323,438 | {z} | "
                f"{z} | {z} | {z} | {z} | 19.8 % | {z} | {z}")

    def test_shares_and_percent_both_read(self):
        """Regression: the percentage was lost, which silently skipped the
        reconciliation check -- the strongest numeric validator there is."""
        from ceo_ownership.freepath import parse_table_heuristic
        r = parse_table_heuristic(self._tsla())[0]
        self.assertEqual(r.shares_reported, 717_323_438)
        self.assertEqual(r.pct_reported, 19.8)

    def test_columns_stay_aligned(self):
        """Regression: "\u200b".strip() is truthy, so spacer cells survived and
        desynchronised data rows from the header."""
        from ceo_ownership.freepath import parse_table_heuristic
        r = parse_table_heuristic(self._tsla())[0]
        self.assertEqual(r.notes, "column=common")

    def test_footnote_marker_not_read_as_percent(self):
        from ceo_ownership.freepath import parse_table_heuristic
        t = ("Name | Common Stock 1,2 | Percent of Common Stock | Additional "
             "Underlying Shares or Stock Units 3,4 | Total 5\n"
             "Satya Nadella | 900,572 | 12 | * | 0 | 900,572")
        r = parse_table_heuristic(t)[0]
        self.assertTrue(r.pct_is_asterisk)
        self.assertIsNone(r.pct_reported)


class TestRealTableStructures(unittest.TestCase):
    """Header-aware column selection against four real layouts."""

    def _row(self, ticker, surname):
        from ceo_ownership.freepath import parse_table_heuristic
        rows = parse_table_heuristic(REAL_TABLES[ticker])
        return next(r for r in rows if surname in r.name_raw)

    def test_single_column_layout(self):
        self.assertEqual(self._row("COST", "Vachris").shares_reported, 52_258)

    def test_common_column_beats_total(self):
        """MSFT and JPM both split out non-common equity; take common, not Total."""
        self.assertEqual(self._row("MSFT", "Nadella").shares_reported, 900_572)
        self.assertEqual(self._row("JPM", "Dimon").shares_reported, 6_266_647)

    def test_voting_power_split_uses_total(self):
        """Regression: WMT splits by voting power, so the first number is only
        the sole-voting part -- 342,311 of Furner's actual 475,161."""
        self.assertEqual(self._row("WMT", "Furner").shares_reported, 475_161)
        self.assertEqual(self._row("WMT", "McMillon").shares_reported, 2_297_783)

    def test_footnote_superscript_not_read_as_shares(self):
        """MSFT renders "900,572(12)" as two cells; the 12 must not shift
        column alignment."""
        self.assertEqual(self._row("MSFT", "Hoffman").shares_reported, 15_905)

    def test_genuine_tiny_holding_survives(self):
        """JPMorgan lists a director holding 5 shares -- not a footnote ref."""
        self.assertEqual(self._row("JPM", "Buck").shares_reported, 5)

    def test_zero_holding_preserved(self):
        self.assertEqual(self._row("MSFT", "MacGregor").shares_reported, 0)

    def test_group_row_found_in_every_layout(self):
        from ceo_ownership.freepath import parse_table_heuristic
        expected = {"COST": 460_270, "MSFT": 2_279_620,
                    "JPM": 8_573_082, "WMT": 7_044_961}
        for tk, want in expected.items():
            rows = parse_table_heuristic(REAL_TABLES[tk])
            grp = [r for r in rows if r.is_group_row]
            self.assertEqual(len(grp), 1, tk)
            self.assertEqual(grp[0].shares_reported, want, tk)


DUAL_CLASS_TABLES = {
    "META": """Name of Beneficial Owner | Shares Beneficially Owned | % of Total Voting Power (1)
Class A | Class B
Shares | % | Shares | %
Mark Zuckerberg (2) | 639,347 | * | 341,823,978 | 99.8 | 60.8
Susan Li (3) | 31,429 | * | \u2014 | \u2014 | *
All current executive officers and directors as a group (20 persons) (20) | 1,555,951 | * | 341,823,978 | 99.8 | 60.9""",

    "GOOGL": """Name of Beneficial Owner | Voting Shares Beneficially Owned | Total Voting Power (1) %
Class A Common Stock | Class B Common Stock
Shares | % | Shares | %
Larry Page | \u2014 | \u2014 | 389,051,160 | 46.5 | 27.4
Sundar Pichai | 227,560 | * | \u2014 | \u2014 | *""",
}


class TestDualClassTables(unittest.TestCase):
    """Multi-row headers where each share class gets its own column."""

    def test_class_columns_are_summed(self):
        """Regression: Zuckerberg read as 639,347 (Class A only) instead of
        342,463,325. The summed figure matches his Form 4 total exactly."""
        from ceo_ownership.freepath import parse_table_heuristic
        rows = parse_table_heuristic(DUAL_CLASS_TABLES["META"])
        zuck = next(r for r in rows if "Zuckerberg" in r.name_raw)
        self.assertEqual(zuck.shares_reported, 342_463_325)
        self.assertIn("2xclass", zuck.notes)

    def test_single_class_holder_in_dual_class_table(self):
        from ceo_ownership.freepath import parse_table_heuristic
        rows = parse_table_heuristic(DUAL_CLASS_TABLES["META"])
        li = next(r for r in rows if "Susan Li" in r.name_raw)
        self.assertEqual(li.shares_reported, 31_429)

    def test_group_row_still_found(self):
        from ceo_ownership.freepath import parse_table_heuristic
        rows = parse_table_heuristic(DUAL_CLASS_TABLES["META"])
        self.assertEqual(len([r for r in rows if r.is_group_row]), 1)

    def test_voting_only_table_is_detected(self):
        """Alphabet's table omits non-voting Class C, so the proxy does not
        contain the economic answer and must never resolve free."""
        from ceo_ownership.freepath import header_reports_voting_only
        self.assertTrue(header_reports_voting_only(
            DUAL_CLASS_TABLES["GOOGL"].splitlines()))
        self.assertFalse(header_reports_voting_only(
            DUAL_CLASS_TABLES["META"].splitlines()))

    def test_voting_only_forces_escalation(self):
        from ceo_ownership.freepath import try_free_path
        from ceo_ownership.form4 import Form4Record
        f4 = Form4Record(accession="a", filing_date="2026-07-28", period=None,
                         owner_name="Pichai Sundar", owner_cik="1",
                         officer_title="Chief Executive Officer",
                         is_officer=True, is_director=False,
                         common_shares=3_006_750.0)
        res = try_free_path(DUAL_CLASS_TABLES["GOOGL"], "", f4)
        self.assertTrue(res.escalate)
        self.assertIn("VOTING shares only", res.reasons[0])


class TestHonorifics(unittest.TestCase):
    def test_honorific_stripped(self):
        """Tesla tags ecd:PeoName as "Mr. Musk"."""
        from ceo_ownership.peo import _clean_name
        self.assertEqual(_clean_name("Mr. Musk"), "Musk")
        self.assertEqual(_clean_name("Dr. Jane Roe"), "Jane Roe")
        self.assertEqual(_clean_name("Mark Zuckerberg"), "Mark Zuckerberg")


class TestAlphabetDenominator(unittest.TestCase):
    def test_consisting_of_not_double_counted(self):
        """"6,659,444,154 shares of Class A and Class B ... consisting of
        5,823,665,113 shares of Class A" -- the leading figure is the total."""
        from ceo_ownership.outstanding import shares_outstanding_from_proxy as f
        r = f("On the Record Date, we had 6,659,444,154 shares of Class A "
              "common stock and Class B common stock issued and outstanding, "
              "consisting of 5,823,665,113 shares of Class A common stock and "
              "835,779,041 shares of Class B common stock.")
        self.assertEqual(r["total"], 6_659_444_154)
        self.assertEqual(len(r["per_class"]), 2)


class TestSplitTables(unittest.TestCase):
    """Long ownership tables are emitted one <table> per printed page."""

    CABOT = """<html><body>
<table><tr><th>Name</th><th>Total Number of Shares</th><th>Percent of Class</th></tr>
<tr><td>Sean D. Keohane</td><td>418,398</td><td>*</td></tr>
<tr><td>Erica McLaughlin</td><td>121,000</td><td>*</td></tr></table>
<table><tr><th>Name</th><th>Total Number of Shares</th><th>Percent of Class</th></tr>
<tr><td>Christine Y. Yan</td><td>17,171</td><td>*</td></tr>
<tr><td>Directors and executive officers as a group (15 persons)</td>
<td>1,647,720</td><td>3.08%</td></tr></table></body></html>"""

    def test_fragments_are_merged(self):
        """Regression: Cabot's tail fragment scored higher than the body,
        because it carried the group row. The CEO was in the other half."""
        from ceo_ownership.proxy import locate_ownership_tables
        top = locate_ownership_tables(self.CABOT)[0]
        self.assertIn("Keohane", top.text)
        self.assertIn("Christine Y. Yan", top.text)
        self.assertTrue(top.has_group_row)

    def test_merge_preserves_document_order(self):
        from ceo_ownership.proxy import locate_ownership_tables
        top = locate_ownership_tables(self.CABOT)[0]
        self.assertLess(top.text.index("Keohane"), top.text.index("Christine"))

    def test_unrelated_tables_not_merged(self):
        from ceo_ownership.proxy import locate_ownership_tables
        html = ("<html><body>"
                "<table><tr><th>Name</th><th>Shares</th><th>Percent</th></tr>"
                "<tr><td>A Person</td><td>1,000</td><td>*</td></tr>"
                "<tr><td>Directors and officers as a group</td><td>9,000</td>"
                "<td>2%</td></tr></table>"
                "<table><tr><th>Plan</th><th>Awards</th><th>Price</th></tr>"
                "<tr><td>2019 Plan</td><td>500,000</td><td>$41</td></tr></table>"
                "</body></html>")
        top = locate_ownership_tables(html)[0]
        self.assertNotIn("2019 Plan", top.text)


class TestDisneyCase(unittest.TestCase):
    """Disney: the right table, a CEO who is not in it, and an apostrophe."""

    DIS = """<html><body><table>
<tr><th>Name</th><th>Shares 1,2 (#)</th><th>Stock Units 3 (#)</th>
<th>Shares Acquirable Within 60 Days 4 (#)</th><th>Percent of Class</th></tr>
<tr><td>Mary T. Barra</td><td>229</td><td>25,495</td><td>—</td><td>*</td></tr>
<tr><td>Robert A. Iger</td><td>253,862</td><td>—</td><td>2,088,863</td>
<td>*</td></tr>
<tr><td>All Directors, nominees and executive officers as a group (15 persons)
</td><td>444,008</td><td>126,234</td><td>2,482,524</td><td>*</td></tr>
</table></body></html>"""

    def test_bare_shares_header_counts_as_holdings(self):
        """Regression: Disney's real table was docked 3.5 points because its
        header is "Shares 1,2 (#)" rather than a longer phrase."""
        from ceo_ownership.proxy import locate_ownership_tables
        c = locate_ownership_tables(self.DIS)[0]
        self.assertTrue(any("holdings_column" in r for r in c.reasons))
        self.assertFalse(any("no_holdings_column" in r for r in c.reasons))

    def test_apostrophe_surnames_match(self):
        """EDGAR writes "DAmaro Joshua W"; the certification says
        "Josh D'Amaro". An internal apostrophe made them different tokens."""
        from ceo_ownership.validate import names_match
        self.assertGreaterEqual(names_match("Josh D'Amaro", "DAmaro Joshua W"), 0.7)
        self.assertGreaterEqual(names_match("Sean O'Brien", "OBrien Sean P"), 0.7)
        self.assertLess(names_match("Josh D'Amaro", "Iger Robert A"), 0.7)

    def test_incoming_ceo_genuinely_absent(self):
        """No parser change produces a row for a CEO appointed after the
        proxy was written. Disney's January table lists Iger."""
        from ceo_ownership.extract import table_to_text
        from ceo_ownership.freepath import parse_table_heuristic
        from ceo_ownership.proxy import locate_ownership_tables
        from ceo_ownership.validate import names_match
        rows = parse_table_heuristic(
            table_to_text(locate_ownership_tables(self.DIS)[0].html))
        self.assertFalse(any(names_match(r.name_raw, "Josh D'Amaro") >= 0.7
                             for r in rows))
        self.assertTrue(any(names_match(r.name_raw, "Robert A. Iger") >= 0.7
                            for r in rows))


class TestGrantTableNotMistakenForHoldings(unittest.TestCase):
    """Containing the CEO's name is necessary but not sufficient."""

    def test_grant_table_lacks_holdings_column(self):
        """GE's grant table lists "Culp | 57,540 | 684,923". Reading 57,540
        as a holding would be silently wrong, so name matching alone must not
        be allowed to select it."""
        from ceo_ownership.proxy import locate_ownership_tables
        grant = ("<html><body><table><tr><th>NAME</th><th>OPTIONS GRANTED</th>"
                 "<th>STOCK AWARDS GRANTED</th></tr>"
                 "<tr><td>Culp</td><td>57,540</td><td>684,923</td></tr>"
                 "</table></body></html>")
        c = locate_ownership_tables(grant)
        if c:
            self.assertTrue(any("no_holdings_column" in r for r in c[0].reasons))


class TestGroupRowAcrossTables(unittest.TestCase):
    """The aggregate row is often in a different table from the CEO's.

    Regression: name-based table selection took group_bound's skip count from
    4 to 12 on a 100-company panel, because GE-style layouts put directors,
    named executives, the group total and 5% holders in four side-by-side
    tables. More figures with less checking is the wrong trade.
    """

    GE = """<html><body>
<table><tr><th>DIRECTORS AND DIRECTOR NOMINEES</th><th>NUMBER OF SHARES</th>
<th>PERCENT OF CLASS</th></tr>
<tr><td>Sebastien Bazin</td><td>0</td><td>*</td></tr></table>
<table><tr><th>NAMED EXECUTIVES</th><th>NUMBER OF SHARES</th>
<th>PERCENT OF CLASS</th></tr>
<tr><td>H. Lawrence Culp, Jr.</td><td>1,612,480</td><td>**</td></tr></table>
<table><tr><th>CURRENT DIRECTORS &amp; EXECUTIVES</th><th>NUMBER OF SHARES</th>
<th>PERCENT OF CLASS</th></tr>
<tr><td>Current directors &amp; executives as a group (16 people)</td>
<td>1,964,879</td><td>**</td></tr></table></body></html>"""

    def _tables(self):
        from ceo_ownership.proxy import locate_ownership_tables
        return locate_ownership_tables(self.GE)

    def test_ceo_table_has_no_group_row(self):
        from ceo_ownership.extract import table_to_text
        from ceo_ownership.freepath import parse_table_heuristic
        ceo_tbl = next(c for c in self._tables() if "Culp" in c.text)
        rows = parse_table_heuristic(table_to_text(ceo_tbl.html))
        self.assertFalse(any(r.is_group_row for r in rows))

    def test_group_row_recoverable_from_adjacent_table(self):
        from ceo_ownership.extract import table_to_text
        from ceo_ownership.freepath import parse_table_heuristic
        tables = self._tables()
        ceo_tbl = next(c for c in tables if "Culp" in c.text)
        found = None
        for c in tables:
            if c is ceo_tbl:
                continue
            for r in parse_table_heuristic(table_to_text(c.html)):
                if r.is_group_row and r.shares_reported:
                    found = r
                    break
            if found:
                break
        self.assertIsNotNone(found)
        self.assertEqual(found.shares_reported, 1_964_879)

    def test_bound_holds_with_real_numbers(self):
        from ceo_ownership.extract import table_to_text
        from ceo_ownership.freepath import parse_table_heuristic
        ceo_tbl = next(c for c in self._tables() if "Culp" in c.text)
        ceo = next(r for r in parse_table_heuristic(table_to_text(ceo_tbl.html))
                   if "Culp" in r.name_raw)
        self.assertLessEqual(ceo.shares_reported, 1_964_879)


class TestCeoNameAlwaysPopulated(unittest.TestCase):
    """ceo_name must hold the CEO's name, not the matched table row.

    Regression: it was written only when the ownership row was found, so a
    company whose Section 302 certification named its CEO perfectly still
    showed a blank ceo_name if table selection failed -- which reads as an
    identity failure when identity in fact succeeded.
    """

    def test_field_exists_and_defaults_empty(self):
        from ceo_ownership.pipeline import OwnershipRecord
        r = OwnershipRecord(cik=1, ticker="X", company="Co", ceo_source=None)
        self.assertIsNone(r.ceo_name)
        self.assertIn("ceo_name_in_table", r.as_dict())

    def test_table_name_is_recorded_separately(self):
        """Proxy tables abbreviate: "J. Duato" for Joaquin Duato. Both the
        identified name and the printed one are worth keeping."""
        from ceo_ownership.pipeline import OwnershipRecord
        r = OwnershipRecord(cik=1, ticker="X", company="Co", ceo_source=None)
        r.ceo_name = "Joaquin Duato"
        r.ceo_name_in_table = "J. Duato"
        d = r.as_dict()
        self.assertEqual(d["ceo_name"], "Joaquin Duato")
        self.assertEqual(d["ceo_name_in_table"], "J. Duato")

    def test_triage_counts_missing_names_not_missing_rows(self):
        from ceo_ownership.triage import triage
        recs = [{"cik": 1, "ceo_name": "Sean D. Keohane", "error":
                 "free path could not settle it -- CEO row not found",
                 "confidence": "LOW"}]
        self.assertIn("no CEO name   : 0", triage(recs))


class TestTableSelectedByCeoName(unittest.TestCase):
    """When a company prints several ownership tables, the CEO's name picks.

    Regression: GE prints three -- 5% holders, directors, named executives --
    and every structural signal treats them alike. Scoring picked the
    directors table; Exxon's 5% table outranked the one holding Darren Woods.
    The name is known before the table is chosen, so use it.
    """

    GE = """<html><body>
<p>5% BENEFICIAL OWNERS</p>
<table><tr><th>5% BENEFICIAL OWNERS</th><th>NUMBER OF SHARES</th>
<th>PERCENT OF CLASS</th></tr>
<tr><td>The Vanguard Group</td><td>102,000,000</td><td>9.8%</td></tr></table>
<table><tr><th>DIRECTORS AND DIRECTOR NOMINEES</th><th>NUMBER OF SHARES</th>
<th>PERCENT OF CLASS</th></tr>
<tr><td>S\u00e9bastien Bazin</td><td>0</td><td>*</td></tr>
<tr><td>Margaret Billson</td><td>2,133</td><td>*</td></tr></table>
<table><tr><th>NAMED EXECUTIVES</th><th>NUMBER OF SHARES</th>
<th>PERCENT OF CLASS</th></tr>
<tr><td>H. Lawrence Culp, Jr.</td><td>1,612,480</td><td>**</td></tr>
<tr><td>Rahul Ghai</td><td>140,216</td><td>**</td></tr></table></body></html>"""

    def _select(self, html, names):
        from ceo_ownership.proxy import locate_ownership_tables
        from ceo_ownership.extract import table_to_text
        from ceo_ownership.freepath import parse_table_heuristic
        from ceo_ownership.validate import names_match
        for cand in locate_ownership_tables(html):
            rows = parse_table_heuristic(table_to_text(cand.html))
            people = [r for r in rows if not r.is_group_row]
            if any(names_match(r.name_raw, nm) >= 0.7
                   for r in people for nm in names):
                return cand
        return None

    def test_picks_the_table_holding_the_ceo(self):
        got = self._select(self.GE, ["H. Lawrence Culp"])
        self.assertIsNotNone(got)
        self.assertIn("Culp, Jr.", got.text)

    def test_skips_five_percent_and_director_tables(self):
        got = self._select(self.GE, ["H. Lawrence Culp"])
        self.assertNotIn("Vanguard", got.text)
        self.assertNotIn("Bazin", got.text)

    def test_a_director_would_select_the_director_table(self):
        """The mechanism is name-driven, not table-label-driven."""
        got = self._select(self.GE, ["Margaret Billson"])
        self.assertIn("Billson", got.text)

    def test_absent_name_selects_nothing(self):
        self.assertIsNone(self._select(self.GE, ["Nobody Here"]))

    def test_candidates_widened_for_selection(self):
        """Three tables must all remain available to choose between."""
        from ceo_ownership.proxy import locate_ownership_tables
        self.assertGreaterEqual(len(locate_ownership_tables(self.GE)), 3)


class TestHoldingsColumnRequirement(unittest.TestCase):
    """An ownership table must have a column that counts shares held."""

    EXXON = """<html><body>
<table><tr><td>Page</td></tr><tr><td>PROXY SUMMARY</td><td>1</td></tr>
<tr><td>CERTAIN BENEFICIAL OWNERS</td><td>37</td></tr>
<tr><td>DIRECTOR AND EXECUTIVE OFFICER STOCK OWNERSHIP</td><td>38</td></tr></table>
<table><tr><th>Named Executive Officer</th><th>Shares Owned (1)</th>
<th>Shares Covered by Exercisable Options</th></tr>
<tr><td>D.W. Woods</td><td>374,437</td><td>0</td></tr>
<tr><td>Directors and executive officers as a group</td><td>2,100,000</td>
<td>0</td></tr></table></body></html>"""

    GE = """<html><body>
<table><tr><th>NAME</th><th>OPTIONS GRANTED*</th><th>STOCK AWARDS GRANTED*</th></tr>
<tr><td>Culp</td><td>57,540</td><td>684,923</td></tr>
<tr><td>All current executive officers as a group</td><td>261,697</td>
<td>1,146,983</td></tr></table>
<p>5% BENEFICIAL OWNERS</p>
<table><tr><th>NAMED EXECUTIVES</th><th>NUMBER OF SHARES</th>
<th>PERCENT OF CLASS</th></tr>
<tr><td>H. Lawrence Culp, Jr.</td><td>1,612,480</td><td>**</td></tr>
<tr><td>Rahul Ghai</td><td>140,216</td><td>**</td></tr></table></body></html>"""

    def test_contents_page_loses(self):
        """Regression: Exxon's table of contents won, because "CERTAIN
        BENEFICIAL OWNERS" is a chapter title."""
        from ceo_ownership.proxy import locate_ownership_tables
        self.assertIn("Woods", locate_ownership_tables(self.EXXON)[0].text)

    def test_real_table_not_mistaken_for_contents(self):
        """Exxon's options column is all zeros, and "0" looks like a page
        number. Comma-formatted share counts distinguish the two."""
        from ceo_ownership.proxy import locate_ownership_tables
        top = locate_ownership_tables(self.EXXON)[0]
        self.assertFalse(any("contents_page" in r for r in top.reasons))

    def test_grant_table_loses_to_ownership_table(self):
        """Regression: GE's equity GRANT table won on the group-row bonus,
        because it also totals officers as a group."""
        from ceo_ownership.proxy import locate_ownership_tables
        top = locate_ownership_tables(self.GE)[0]
        self.assertIn("Culp, Jr.", top.text)
        self.assertNotIn("OPTIONS GRANTED", top.text)

    def test_number_of_shares_parses_as_holdings(self):
        from ceo_ownership.freepath import parse_table_heuristic
        r = parse_table_heuristic(
            "NAMED EXECUTIVES | NUMBER OF SHARES | PERCENT OF CLASS\n"
            "H. Lawrence Culp, Jr. | 1,612,480 | **")[0]
        self.assertEqual(r.shares_reported, 1_612_480)


class TestProseTablePenalty(unittest.TestCase):
    def test_prose_table_loses_to_data_table(self):
        """Regression: Exxon's "Issue | New Jersey | Texas" legal comparison
        outranked the real table, because its prose mentions "beneficial
        owner" and several percentages."""
        from ceo_ownership.proxy import locate_ownership_tables
        prose = ("<table><tr><td>Issue</td><td>New Jersey</td><td>Texas</td></tr>"
                 "<tr><td>" + ("beneficial owner of not less than 10% of shares " * 40)
                 + "</td><td>" + ("Texas By-laws require 15% of voting power " * 40)
                 + "</td></tr></table>")
        real = ("<table><tr><th>Named Executive Officer</th><th>Shares Owned</th>"
                "<th>Shares Covered by Exercisable Options</th></tr>"
                "<tr><td>D.W. Woods</td><td>374,437</td><td>0</td></tr>"
                "<tr><td>Directors and executive officers as a group</td>"
                "<td>2,100,000</td><td>0</td></tr></table>")
        top = locate_ownership_tables(f"<html><body>{prose}{real}</body></html>")[0]
        self.assertIn("Woods", top.text)

    def test_exxon_header_roles(self):
        """"Shares Owned" plus "Exercisable Options" are ADDED under 13d-3."""
        from ceo_ownership.freepath import parse_table_heuristic
        t = ("Named Executive Officer | Shares Owned (1) | Shares Covered by "
             "Exercisable Options\nD.W. Woods | 374,437 | 0")
        r = parse_table_heuristic(t)[0]
        self.assertEqual(r.shares_reported, 374_437)


class TestRegionFirstExtraction(unittest.TestCase):
    """Search the table's neighbourhood before the whole document.

    Item 6(a) mandates that the count be stated but not where, and
    "outstanding" appears throughout ownership prose in unrelated senses.
    Both silent denominator errors -- Enova's acquirable-shares footnote and
    Exxon's authorized capital -- came from scanning everything.
    """

    ENOVA_FOOTNOTES = (
        "The ownership percentage for each individual named below is based on "
        "the number of shares of our Common Stock issued and outstanding on "
        "March 20, 2026, which was 24,945,366. This amount includes 1,023,200 "
        "shares that directors have the right to acquire within 60 days.")

    NOISY_DOC = (
        "<html><body><p>ExxonMobil has authorized capital consisting of "
        "9,000,000,000 shares of common stock outstanding under the charter."
        "</p><p>" + ENOVA_FOOTNOTES + "</p></body></html>")

    def test_footnotes_searched_first(self):
        from ceo_ownership.outstanding import outstanding_by_region
        found, region = outstanding_by_region(
            self.NOISY_DOC, footnotes=self.ENOVA_FOOTNOTES)
        self.assertEqual(found["total"], 24_945_366)
        self.assertEqual(region, "table_footnotes")

    def test_ownership_basis_sentence_beats_charter_recital(self):
        """Even with no table context, a sentence tying the figure to the
        ownership calculation outranks a number found anywhere else."""
        from ceo_ownership.outstanding import outstanding_by_region
        found, region = outstanding_by_region(self.NOISY_DOC)
        self.assertEqual(found["total"], 24_945_366)
        self.assertEqual(region, "ownership_basis_sentence")

    def test_real_phrasings(self):
        from ceo_ownership.outstanding import outstanding_by_region
        for html, want in [
            ("<html><body><p>Applicable percentage ownership is based on "
             "3,325,150,886 shares of Tesla's common stock outstanding at "
             "September 15, 2025.</p></body></html>", 3_325_150_886),
            ("<html><body><p>The calculation of percentage of ownership of "
             "each listed beneficial owner is based on 52,221,604 shares of "
             "Cabot common stock, which represents the number of shares "
             "outstanding on January 14, 2026.</p></body></html>", 52_221_604),
        ]:
            found, region = outstanding_by_region(html)
            self.assertEqual(found["total"], want)
            self.assertEqual(region, "ownership_basis_sentence")

    def test_region_order(self):
        """The table body is not a region: it reports holdings, not the
        outstanding count."""
        from ceo_ownership.outstanding import denominator_regions
        names = [n for n, _ in denominator_regions(
            "<html><body>x</body></html>", table_context="ctx", footnotes="fn")]
        self.assertEqual(names[0], "table_footnotes")
        self.assertNotIn("table_context", names)
        self.assertEqual(names[-1], "whole_document")

    def test_nothing_found(self):
        from ceo_ownership.outstanding import outstanding_by_region
        found, region = outstanding_by_region("<html><body>no numbers</body></html>")
        self.assertIsNone(found["total"])
        self.assertEqual(region, "not_found")


class TestImpliedDenominatorMultiClass(unittest.TestCase):
    """Shares and percentage must describe the same class.

    Regression: in a multi-class table the parser sums shares across classes
    while the percentage belongs to one. Peter Thiel's three-class total over
    his Class A percentage implied 3,277,833,333 shares against Palantir's
    real 2,397,157,109, flagging a 37% disagreement the calculation had
    invented.
    """

    def _row(self, notes):
        from ceo_ownership.extract import OwnershipRow
        return OwnershipRow(name_raw="Peter Thiel", shares_reported=98_335_000,
                            pct_reported=3.0, notes=notes)

    def test_multi_class_row_refused(self):
        from ceo_ownership.outstanding import implied_from_row
        self.assertIsNone(implied_from_row(self._row("column=3xclass")))
        self.assertIsNone(implied_from_row(self._row("column=2xclass")))

    def test_single_class_row_still_used(self):
        from ceo_ownership.extract import OwnershipRow
        from ceo_ownership.outstanding import implied_from_row
        row = OwnershipRow(name_raw="Vachris", shares_reported=1_647_720,
                           pct_reported=3.08, notes="column=common")
        self.assertAlmostEqual(implied_from_row(row), 53_497_402, delta=100)

    def test_options_still_subtracted(self):
        from ceo_ownership.extract import OwnershipRow
        from ceo_ownership.outstanding import implied_from_row
        row = OwnershipRow(name_raw="group", shares_reported=2_182_430,
                           pct_reported=8.4, options_60d=1_023_200,
                           notes="column=common")
        self.assertAlmostEqual(implied_from_row(row), 24_958_110, delta=100)


class TestTrailingContextExcludesTheTable(unittest.TestCase):
    """"Footnote context" must begin after the table, not inside it.

    Regression: it was computed from the 80-character snippet used to LOCATE
    the table, so for any table longer than 80 characters -- all of them --
    the region was mostly table body. Palantir's denominator search read that
    region and took BlackRock's 158,217,849 holding out of the ownership
    table, while the correct 2,397,157,109 sat two regions away.
    """

    HTML = ("<html><body>"
            "<p>The following table sets forth beneficial ownership as of "
            "April 6, 2026.</p>"
            "<table><tr><th>Name</th><th>Shares Beneficially Owned</th>"
            "<th>Percent</th></tr>"
            + "".join(f"<tr><td>Holder {i}</td><td>{i*1_000_000:,}</td>"
                      f"<td>*</td></tr>" for i in range(1, 40))
            + "<tr><td>All directors and officers as a group</td>"
              "<td>50,000,000</td><td>2%</td></tr></table>"
            "<p>(1) Based on 2,397,157,109 shares of common stock "
            "outstanding.</p></body></html>")

    def _top(self):
        from ceo_ownership.proxy import locate_ownership_tables
        return locate_ownership_tables(self.HTML)[0]

    def test_trailing_starts_after_the_table(self):
        top = self._top()
        self.assertIn("2,397,157,109", top.trailing_context)
        self.assertNotIn("Holder 20", top.trailing_context)
        self.assertNotIn("Holder 39", top.trailing_context)

    def test_preceding_is_before_the_table(self):
        top = self._top()
        self.assertIn("following table", top.preceding_context)
        self.assertNotIn("Holder 1", top.preceding_context)

    def test_denominator_comes_from_the_footnote(self):
        from ceo_ownership.outstanding import outstanding_by_region
        top = self._top()
        found, region = outstanding_by_region(
            self.HTML, footnotes=top.trailing_context,
            preceding=top.preceding_context)
        self.assertEqual(found["total"], 2_397_157_109)
        self.assertEqual(region, "table_footnotes")

    def test_no_table_holding_can_be_taken_as_the_count(self):
        """The largest number in the table is 50,000,000; it must not win."""
        from ceo_ownership.outstanding import outstanding_by_region
        top = self._top()
        found, _ = outstanding_by_region(
            self.HTML, footnotes=top.trailing_context,
            preceding=top.preceding_context)
        self.assertNotEqual(found["total"], 50_000_000)
        self.assertNotEqual(found["total"], 39_000_000)


class TestPalantirDenominator(unittest.TestCase):
    """Palantir states the count in the proxy Q&A, not near the table.

    Its introductory paragraph explains the 60-day rule and gives no total,
    so the figure has to be found elsewhere -- under the standard heading
    "How many shares are outstanding and entitled to vote as of the record
    date?", which most proxies carry.
    """

    PLTR = """<html><body>
<p>Who is entitled to vote at the annual meeting?</p>
<p>You can vote at the annual meeting if you were a holder of our common stock
as of the close of business on April 6, 2026, the "record date." As of the
close of business on April 6, 2026, we had 2,397,157,109 shares of common
stock outstanding and entitled to vote on any matter, consisting of
2,295,915,766 shares of Class A common stock, 100,236,343 shares of Class B
common stock, and 1,005,000 shares of Class F common stock.</p>
<p>The amounts and percentages of Class A common stock, Class B common stock
and Class F common stock beneficially owned are reported on the basis of the
regulations of the SEC governing the determination of beneficial ownership.</p>
</body></html>"""

    def test_found_in_the_voting_qa(self):
        from ceo_ownership.outstanding import outstanding_by_region
        found, region = outstanding_by_region(self.PLTR)
        self.assertEqual(found["total"], 2_397_157_109)
        self.assertEqual(region, "entitled_to_vote_qa")

    def test_all_three_classes_parsed(self):
        from ceo_ownership.outstanding import outstanding_by_region
        found, _ = outstanding_by_region(self.PLTR)
        self.assertEqual(len(found["per_class"]), 3)
        self.assertEqual(found["per_class"]["Class A"], 2_295_915_766)
        self.assertEqual(found["per_class"]["Class F"], 1_005_000)

    def test_karps_percentage(self):
        """6,432,258 A + 86,907,993 B + 335,000 F over the total."""
        from ceo_ownership.outstanding import outstanding_by_region
        found, _ = outstanding_by_region(self.PLTR)
        karp = 6_432_258 + 86_907_993 + 335_000
        self.assertAlmostEqual(100 * karp / found["total"], 3.908, places=2)

    def test_qa_ranks_ahead_of_whole_document(self):
        from ceo_ownership.outstanding import denominator_regions
        names = [n for n, _ in denominator_regions(self.PLTR)]
        self.assertLess(names.index("entitled_to_vote_qa"),
                        names.index("whole_document"))


class TestTableBodyNeverSearched(unittest.TestCase):
    """The ownership table reports holdings, never the outstanding count.

    Item 403 governs the table; Item 6(a) requires the count and is satisfied
    in prose. Every filing examined states it in text.

    Regression: searching the table body took BlackRock's 158,217,849 Class A
    holding as Palantir's share count, because its header reads "Percentage
    of Votes (Record Date Outstanding Shares)" and the flattened table
    therefore looks like a sentence about shares outstanding. Karp was
    reported at 59.2% instead of 3.9%.
    """

    PLTR = ("Shares Beneficially Owned Class A Class B Class F Percentage of "
            "Votes (Record Date Outstanding Shares) % Alexander Karp "
            "6,432,258 * 86,907,993 64.0 335,000 33.3 11.4 BlackRock, Inc. "
            "158,217,849 6.9 \u2014 * \u2014 * 3.5")

    def test_table_body_yields_nothing(self):
        from ceo_ownership.outstanding import outstanding_by_region
        found, region = outstanding_by_region(
            "<html><body>x</body></html>", table_context=self.PLTR)
        self.assertIsNone(found["total"])
        self.assertEqual(region, "not_found")

    def test_table_body_is_not_a_region(self):
        from ceo_ownership.outstanding import denominator_regions
        names = [n for n, _ in denominator_regions(
            "<html></html>", table_context="T", footnotes="F", preceding="P")]
        self.assertNotIn("table_context", names)
        self.assertEqual(names, ["table_introduction", "table_footnotes",
                                 "whole_document"])

    def test_legitimate_regions_still_work(self):
        from ceo_ownership.outstanding import outstanding_by_region
        intro = ("All percentage calculations are based on the number of "
                 "shares of common stock issued and outstanding on February "
                 "18, 2026, which was 621,925,120.")
        f, r = outstanding_by_region("<html><body>x</body></html>",
                                     preceding=intro)
        self.assertEqual(f["total"], 621_925_120)
        note = ("The calculation of percentage of ownership is based on "
                "52,221,604 shares of Cabot common stock, which represents "
                "the number of shares outstanding.")
        f, r = outstanding_by_region("<html><body>x</body></html>",
                                     footnotes=note)
        self.assertEqual(f["total"], 52_221_604)


class TestSecondReaderPlumbing(unittest.TestCase):
    """The flag has to actually reach the code it enables.

    Regression: build_panel accepted second_reader and never passed it to
    build_record, so --second-reader ran to completion, reported success, and
    did nothing. A silent no-op is the worst failure mode a flag can have --
    it looks exactly like a reader that ran and found agreement.
    """

    def test_build_panel_forwards_the_flag(self):
        import inspect
        from ceo_ownership import panel
        src = inspect.getsource(panel.build_panel)
        self.assertIn("second_reader=second_reader", src)

    def test_build_record_accepts_it(self):
        import inspect
        from ceo_ownership.pipeline import build_record
        self.assertIn("second_reader",
                      inspect.signature(build_record).parameters)

    def test_default_is_off(self):
        import inspect
        from ceo_ownership.pipeline import build_record
        from ceo_ownership.panel import build_panel
        for fn in (build_record, build_panel):
            self.assertIs(inspect.signature(fn).parameters["second_reader"]
                          .default, False)

    def test_every_flag_reaches_build_record(self):
        """The same class of bug for the other pass-through options."""
        import inspect
        from ceo_ownership import panel
        src = inspect.getsource(panel.build_panel)
        for name in ("continuity", "with_form4", "llm_mode", "second_reader"):
            self.assertIn(f"{name}=", src, name)


class TestOutstandingSweep(unittest.TestCase):
    """Recall for the parser, precision for the reader.

    The targeted regions were each added after a company failed -- the voting
    Q&A from Palantir, the table introduction from Capital One. A list built
    from hindsight keeps missing filers nobody has hit yet: three companies
    in the last run matched no region at all, so the reader saw nothing and
    could not reason about anything.

    Sweeping every mention of the phrase cannot miss the sentence for want of
    the right heading. It returns several candidates, which a regex could not
    resolve and a reader can.
    """

    FILLER = "Governance discussion of committees and compensation. " * 60
    MENTIONS = [
        ("2,408,613,219", "On February 24, 2026, there were 2,408,613,219 "
                          "shares outstanding."),
        ("9,000,000,000", "The Company has authorized capital of 9,000,000,000 "
                          "shares of common stock."),
        ("5,760,367", "these 5,760,367 shares represent less than 1% of the "
                      "shares outstanding."),
        ("1,023,200", "Includes 1,023,200 shares directors have the right to "
                      "acquire within 60 days."),
        ("2,295,915,766", "consisting of 2,295,915,766 shares of Class A "
                          "common stock outstanding."),
    ]

    def _doc(self):
        body = "".join(f"<p>{self.FILLER}</p><p>{text}</p>"
                       for _, text in self.MENTIONS)
        return f"<html><body>{body}</body></html>"

    def _sweep(self, **kw):
        from ceo_ownership.outstanding import outstanding_mentions
        return outstanding_mentions(self._doc(), **kw)

    def test_captures_the_real_count(self):
        self.assertIn("2,408,613,219", self._sweep())

    def test_captures_per_class_counts(self):
        self.assertIn("2,295,915,766", self._sweep())

    def test_captures_the_trap_sentence_so_it_can_be_rejected(self):
        """J&J's "these 5,760,367 shares represent less than 1% of the shares
        outstanding" says "outstanding", so it is a candidate. The reader
        rejects it; the sweep should not have to."""
        self.assertIn("5,760,367", self._sweep())

    def test_omits_phrases_that_never_say_outstanding(self):
        sweep = self._sweep()
        self.assertNotIn("9,000,000,000", sweep)   # authorized capital
        self.assertNotIn("1,023,200", sweep)       # right to acquire

    def test_windows_are_capped(self):
        self.assertLessEqual(self._sweep(max_windows=2).count("---"), 2)

    def test_stays_a_small_fraction_of_the_document(self):
        self.assertLess(len(self._sweep()), len(self._doc()) * 0.25)

    def test_windows_need_a_number(self):
        from ceo_ownership.outstanding import outstanding_mentions
        self.assertEqual(
            outstanding_mentions("<p>shares outstanding were discussed</p>"), "")

    def test_sweep_is_sent_to_the_reader(self):
        from ceo_ownership.outstanding import regions_for_model
        names = [n for n, _ in regions_for_model(self._doc())]
        self.assertIn("every_mention_of_shares_outstanding", names)
        self.assertNotIn("whole_document", names)


class TestShareCountReader(unittest.TestCase):
    """The parser locates the text; the model reads it.

    Every denominator failure has been a real figure with the wrong meaning
    attached -- acquirable shares, authorized capital, a holding compared
    against the count -- and each was answered with another exclusion
    pattern written after the company was already reported wrong. Those
    patterns sat on the critical path, so a number had to survive all of
    them to be reported.

    The parser still finds the regions, which it does well: 97 of 100 in the
    last run. Only the reading moved.
    """

    def test_regions_exclude_the_whole_document(self):
        """Sending two million characters would reintroduce exactly the
        needle-in-a-haystack problem the parser already solves."""
        from ceo_ownership.outstanding import denominator_regions
        html = ("<html><body><p>As of April 6, 2026 we had 2,397,157,109 "
                "shares of common stock outstanding.</p></body></html>")
        named = [n for n, _ in denominator_regions(
            html, footnotes="fn", preceding="intro") if n != "whole_document"]
        self.assertIn("table_introduction", named)
        self.assertNotIn("whole_document", named)

    def test_no_regions_means_no_call(self):
        from ceo_ownership.reader import read_share_count
        self.assertIsNotNone(read_share_count([]).error)
        self.assertIsNotNone(read_share_count([("intro", "   ")]).error)

    def test_quote_must_appear_in_the_text_sent(self):
        """A figure that cannot be traced to a place in the filing is not
        auditable, and auditability is the whole claim here."""
        from ceo_ownership.reader import _normalise
        payload = ("=== table_introduction ===\nAll percentage calculations "
                   "are based on 621,925,120 shares outstanding.")
        self.assertIn(_normalise("based on 621,925,120 shares outstanding"),
                      _normalise(payload))
        self.assertNotIn(_normalise("we had 9,000,000,000 shares"),
                         _normalise(payload))

    def test_per_class_sums_to_the_total(self):
        from ceo_ownership.reader import CountReading
        r = CountReading(shares_outstanding=2_397_157_109,
                         per_class={"Class A": 2_295_915_766,
                                    "Class B": 100_236_343,
                                    "Class F": 1_005_000})
        self.assertEqual(sum(r.per_class.values()), r.shares_outstanding)

    def test_reading_is_a_candidate_not_an_override(self):
        """It still competes with the XBRL cover page and the implied
        figures, and disagreement is still reported."""
        from ceo_ownership.outstanding import DenominatorCandidate
        c = DenominatorCandidate(2_397_157_109, "model_read_regions",
                                 "2026-04-06", "we had 2,397,157,109 shares")
        self.assertEqual(c.source, "model_read_regions")

    def test_cheap_model_by_default(self):
        from ceo_ownership.config import SETTINGS
        self.assertIn("haiku", SETTINGS.classifier_model.lower())


class TestTypographicApostrophes(unittest.TestCase):
    """Filings set apostrophes as U+2019, not as a straight quote.

    Regression: a curly apostrophe fell outside the allowed characters and
    became a SPACE, so Gilead's "Daniel P. O\u2019Day" tokenised as
    ["o", "day"] while the certification's "O'Day" gave ["oday"]. The CEO
    was reported as absent from his own ownership table, and the closest
    match was The Vanguard Group at 0.00.
    """

    def test_curly_and_straight_agree(self):
        from ceo_ownership.validate import normalize_name
        self.assertEqual(normalize_name("Daniel P. O\u2019Day"),
                         normalize_name("Daniel P. O'Day"))

    def test_gilead_ceo_matches(self):
        from ceo_ownership.validate import names_match
        self.assertGreaterEqual(
            names_match("Daniel P. O\u2019Day", "O'Day Daniel P"), 0.7)
        self.assertGreaterEqual(
            names_match("Daniel P. O\u2019Day", "Daniel P. O\u2019Day"), 0.7)

    def test_still_rejects_a_different_person(self):
        from ceo_ownership.validate import names_match
        self.assertLess(
            names_match("Daniel P. O\u2019Day", "The Vanguard Group"), 0.7)

    def test_other_typographic_punctuation(self):
        from ceo_ownership.validate import normalize_name
        self.assertEqual(normalize_name("Smith\u2013Jones Mary"),
                         normalize_name("Smith-Jones Mary"))


class TestBareStockHeader(unittest.TestCase):
    """Verizon heads its holdings column simply "Stock"."""

    VZ = ("<html><body><p>shares of Verizon common stock beneficially owned"
          "</p><table><tr><th>Named executive officers</th><th>Stock 1</th>"
          "<th>Total stock-based holdings 2</th></tr>"
          "<tr><td>Daniel Schulman</td><td>0</td><td>981,034</td></tr>"
          "<tr><td>All directors and executive officers as a group</td>"
          "<td>1,200,000</td><td>4,500,000</td></tr></table></body></html>")

    GE = ("<html><body><table><tr><th>NAME</th><th>OPTIONS GRANTED</th>"
          "<th>STOCK AWARDS GRANTED</th></tr>"
          "<tr><td>Culp</td><td>57,540</td><td>684,923</td></tr>"
          "</table></body></html>")

    def test_bare_stock_counts(self):
        from ceo_ownership.proxy import locate_ownership_tables
        top = locate_ownership_tables(self.VZ)[0]
        self.assertTrue(any("holdings_column" in r and "no_" not in r
                            for r in top.reasons))

    def test_stock_awards_granted_does_not(self):
        """GE's grant table must keep failing this test."""
        from ceo_ownership.proxy import locate_ownership_tables
        c = locate_ownership_tables(self.GE)
        self.assertTrue(not c or any("no_holdings_column" in r
                                     for r in c[0].reasons))

    def test_stock_units_does_not(self):
        from ceo_ownership.proxy import locate_ownership_tables
        html = self.VZ.replace("<th>Stock 1</th>", "<th>Stock Units 1</th>")
        top = locate_ownership_tables(html)[0]
        self.assertFalse(any("holdings_column" in r and "no_" not in r
                             for r in top.reasons))


class TestFootnoteColumnTables(unittest.TestCase):
    """A prose TABLE is not the same as a table with a prose COLUMN.

    Regression: the penalty judged the longest cell anywhere, so Coca-Cola's
    ownership table -- which carries an "Additional Information" column of
    footnote text beside its name and share columns -- lost 7 points and was
    never parsed. Its CEO holds 4,461,496 and the pipeline reported nothing.
    """

    KO = ("<html><body><table>"
          "<tr><th>Name</th><th>Aggregate Number of Shares Beneficially Owned"
          "</th><th>Percent of Outstanding Shares</th>"
          "<th>Additional Information</th></tr>"
          "<tr><td>James Quincey</td><td>4,461,496</td><td>*</td><td>"
          + ("Includes 44,678 shares held by a family member and 3,879,031 "
             "shares that may be acquired upon the exercise of options. " * 6)
          + "</td></tr>"
          "<tr><td>All Directors, Director nominees and executive officers as "
          "a group (22 persons)</td><td>38,886,151</td><td>*</td>"
          "<td>Includes 400 shares of restricted stock.</td></tr>"
          "</table></body></html>")

    XOM = ("<html><body><table>"
           "<tr><td>Issue</td><td>New Jersey</td><td>Texas</td></tr><tr><td>"
           + ("beneficial owner of not less than 10% of shares outstanding " * 40)
           + "</td><td>"
           + ("Texas By-laws require 15% of the voting power " * 40)
           + "</td></tr></table></body></html>")

    def test_one_footnote_column_does_not_disqualify(self):
        from ceo_ownership.proxy import locate_ownership_tables
        top = locate_ownership_tables(self.KO)[0]
        self.assertIn("Quincey", top.text)
        self.assertFalse(any("prose_table" in r for r in top.reasons))

    def test_the_ceo_row_parses(self):
        from ceo_ownership.extract import table_to_text
        from ceo_ownership.freepath import parse_table_heuristic
        from ceo_ownership.proxy import locate_ownership_tables
        top = locate_ownership_tables(self.KO)[0]
        rows = parse_table_heuristic(table_to_text(top.html))
        q = next(r for r in rows if "Quincey" in r.name_raw)
        self.assertEqual(q.shares_reported, 4_461_496)

    def test_a_genuinely_prose_table_is_still_rejected(self):
        """Exxon's legal comparison is prose in two of three columns."""
        from ceo_ownership.proxy import locate_ownership_tables
        self.assertEqual(locate_ownership_tables(self.XOM), [])


class TestModelDeclineRejectsTheTable(unittest.TestCase):
    """The model refusing to find the CEO is evidence about the TABLE.

    Altria's CEO holds 510,538; the parser reported 4,816,743, a figure not
    in the ownership table at all. Bank of America's holds 2,803,195; the
    parser reported 0. Both were flagged "several ownership tables", both had
    the model decline, and both then published the parser's number.
    """

    def test_next_candidate_is_tried(self):
        import inspect
        from ceo_ownership import pipeline
        src = inspect.getsource(pipeline.build_record)
        self.assertIn("table_rechosen_after_model_declined", src)
        self.assertIn("model_declined_first_table", src)

    def test_attempts_are_bounded(self):
        """Beyond a few tables the problem is not which table."""
        import inspect
        from ceo_ownership import pipeline
        self.assertIn("ceo_tables[:3]",
                      inspect.getsource(pipeline.build_record))

    def test_candidates_are_ordered_not_excluded(self):
        """The model is the filter, so the parser's job is to make sure the
        right table is IN the list. A table wrongly included costs one cheap
        call; one wrongly excluded cannot be recovered."""
        import inspect
        from ceo_ownership import pipeline
        src = inspect.getsource(pipeline.build_record)
        self.assertIn("ceo_tables.sort(", src)
        self.assertIn("ceo_tables = [c for c in candidates if _has_ceo(c)]", src)

    def test_worksheet_distinguishes_the_blank_reasons(self):
        from ceo_ownership.verify import build_roll_worksheet, WORKSHEET_COLUMNS
        self.assertIn("llm_note", WORKSHEET_COLUMNS)

    def test_declined_is_not_shown_as_blank(self):
        from ceo_ownership.verify import build_sample
        rows = build_sample([{
            "cik": 1, "company": "Co", "ceo_name": "X", "shares_13d3": 100,
            "agreement": "parser_only", "model_note": "person not in table",
            "pct_comparable": 1.0, "shares_outstanding": 1e6,
            "confidence": "LOW", "flags": [], "error": None,
            "validation": {"checks": []}}], include_all=True)
        self.assertEqual(rows[0]["llm_shares"], "declined")
        self.assertIn("not in table", rows[0]["llm_note"])


class TestRollForward(unittest.TestCase):
    """Carrying the anchor forward with Form 4 deltas.

    Both legs are structured -- Form 4 is XML on a fixed schema, the share
    count is an XBRL fact -- so neither needs a model. That is the opposite
    of the proxy, where content is mandated but format is not.
    """

    def _txn(self, code, shares, acquired=True):
        from ceo_ownership.rollforward import Transaction
        return Transaction(date="2026-05-01", code=code, shares=shares,
                           acquired=acquired, security="Common Stock",
                           direct=True)

    def test_sales_and_withholding_subtract(self):
        self.assertEqual(self._txn("S", 12_100, False).effect, -12_100)
        self.assertEqual(self._txn("F", 3_400, False).effect, -3_400)
        self.assertEqual(self._txn("G", 5_000, False).effect, -5_000)

    def test_purchases_add(self):
        self.assertEqual(self._txn("P", 2_000).effect, 2_000)

    def test_option_exercise_is_neutral(self):
        """The trap: an exercise looks like an acquisition, but an option
        exercisable within 60 days was ALREADY in the 13d-3 figure. Adding
        the shares counts the same interest twice."""
        self.assertEqual(self._txn("M", 50_000).effect, 0)
        self.assertEqual(self._txn("C", 10_000).effect, 0)

    def test_grants_are_skipped(self):
        """A Form 4 does not say when restricted stock vests, and it is not
        beneficially owned until it does. Skipping understates rather than
        overstates."""
        self.assertEqual(self._txn("A", 25_000).effect, 0)

    def test_unknown_code_falls_back_to_the_flag(self):
        """Every Form 4 carries acquired/disposed, whatever the code."""
        self.assertEqual(self._txn("Z", 100, True).effect, 100)
        self.assertEqual(self._txn("Z", 100, False).effect, -100)

    def test_a_realistic_sequence(self):
        anchor = 475_161
        txns = [self._txn("S", 12_100, False), self._txn("F", 3_400, False),
                self._txn("M", 50_000), self._txn("A", 25_000),
                self._txn("G", 5_000, False), self._txn("P", 2_000)]
        self.assertEqual(anchor + sum(t.effect for t in txns), 456_661)

    def test_holding_cannot_go_negative(self):
        from ceo_ownership.rollforward import RollForward
        self.assertGreaterEqual(max(0.0, 100 + (-500)), 0)

    def test_worksheet_is_built_around_the_arithmetic(self):
        """Checking a roll-forward asks "does this add up", not "what does
        the table say", so the columns are anchor, delta, result."""
        from ceo_ownership.verify import ROLL_COLUMNS
        for col in ("anchor_shares", "net_delta", "rolled_shares",
                    "gap_days", "form4_url", "actual_delta"):
            self.assertIn(col, ROLL_COLUMNS)

    def test_worksheet_flags_large_moves(self):
        from ceo_ownership.verify import build_roll_worksheet
        rows = build_roll_worksheet([{
            "cik": 1, "company": "Co", "ceo_name": "X", "shares_13d3": 100_000,
            "filing_date": "2026-01-01", "rolled_shares": 40_000.0,
            "rolled_net_delta": -60_000.0, "rolled_txn_count": 3,
            "flags": []}])
        self.assertIn("-60%", rows[0]["hint"])

    def test_rows_without_a_roll_are_omitted(self):
        from ceo_ownership.verify import build_roll_worksheet
        self.assertEqual(build_roll_worksheet([{"cik": 1, "company": "Co"}]), [])


class TestModelIsPrimary(unittest.TestCase):
    """The model answers; the parser checks it.

    On a hundred companies the readers disagreed 16 times. The model was
    clearly right in at least ten and the parser clearly right in none. The
    parser's recurring failure was reporting ONE COLUMN as the whole figure:
    Caterpillar's options without its common stock, Stryker's acquirable
    without its owned, BlackRock's units without its common.

    The denominator had already been moved to the model, and corroboration
    rose from 31 rows confirmed by two sources to 74.
    """

    def test_reported_figure_is_the_models(self):
        import inspect
        from ceo_ownership import pipeline
        src = inspect.getsource(pipeline.build_record)
        self.assertIn('rec.shares_source = "llm_table_read"', src)
        self.assertIn("rec.parser_shares = rec.shares_13d3", src)

    def test_parser_figure_is_kept(self):
        from ceo_ownership.pipeline import OwnershipRecord
        r = OwnershipRecord(cik=1, ticker="X", company="Co", ceo_source=None)
        self.assertIn("parser_shares", r.as_dict())

    def test_parser_used_when_the_model_fails(self):
        import inspect
        from ceo_ownership import pipeline
        src = inspect.getsource(pipeline.build_record)
        self.assertIn("model_read_failed_using_parser", src)

    def test_worksheet_names_the_source(self):
        from ceo_ownership.verify import WORKSHEET_COLUMNS
        for col in ("reported_shares", "source", "parser_shares", "llm_shares"):
            self.assertIn(col, WORKSHEET_COLUMNS)

    def test_partnership_units_excluded_by_prompt(self):
        """Blackstone: the model returned 231,924,793 partnership units as
        common stock. Units are a different security."""
        from ceo_ownership.reader import SYSTEM
        self.assertIn("Partnership units", SYSTEM)
        self.assertIn("REPORT COMMON STOCK ONLY", SYSTEM)

    def test_other_stock_based_holdings_excluded(self):
        """Honeywell: the model added 1,967 of "other stock-based holdings",
        which the table lists separately from beneficial ownership."""
        from ceo_ownership.reader import SYSTEM
        self.assertIn("other stock-based holdings", SYSTEM)
        self.assertIn("SEPARATELY from beneficial ownership", SYSTEM)


class TestTwoReaders(unittest.TestCase):
    """An independent read of the same section, compared.

    Every other check compares one of our readings against another of our
    readings. Johnson & Johnson passed identity, the group bound and
    continuity while being 25% wrong, because all three agreed with each
    other about a wrong number. Agreement between two independent readers is
    evidence none of them can supply.
    """

    def _reading(self, **kw):
        from ceo_ownership.reader import ModelReading
        return ModelReading(**kw)

    def test_agreement(self):
        from ceo_ownership.reader import compare_readings
        a = compare_readings(1_407_667, 2_408_613_219,
                             self._reading(shares=1_407_667,
                                           shares_outstanding=2_408_613_219))
        self.assertEqual(a.verdict, "agree")
        self.assertTrue(a.shares_agree)

    def test_the_jnj_error_would_have_been_caught(self):
        """The parser read 1,763,964 and was HIGH confidence."""
        from ceo_ownership.reader import compare_readings
        a = compare_readings(1_763_964, 5_760_367,
                             self._reading(
                                 shares=1_407_667,
                                 shares_outstanding=2_408_613_219,
                                 column_used="Total number of shares "
                                             "beneficially owned"))
        self.assertEqual(a.verdict, "disagree")
        self.assertIn("1,763,964", a.detail)
        self.assertIn("1,407,667", a.detail)

    def test_denominator_disagreement_reported(self):
        from ceo_ownership.reader import compare_readings
        a = compare_readings(1_407_667, 5_760_367,
                             self._reading(shares=1_407_667,
                                           shares_outstanding=2_408_613_219))
        self.assertEqual(a.verdict, "agree")
        self.assertFalse(a.outstanding_agree)
        self.assertIn("outstanding", a.detail)

    def test_each_reader_alone(self):
        from ceo_ownership.reader import compare_readings
        self.assertEqual(
            compare_readings(52_258, 443_957_682,
                             self._reading(shares=None)).verdict, "parser_only")
        self.assertEqual(
            compare_readings(None, 443_957_682,
                             self._reading(shares=52_258)).verdict, "model_only")
        self.assertEqual(
            compare_readings(None, None, self._reading()).verdict, "neither")

    def test_model_error_is_not_a_disagreement(self):
        from ceo_ownership.reader import compare_readings
        a = compare_readings(52_258, 443_957_682,
                             self._reading(error="rate limited"))
        self.assertEqual(a.verdict, "not_compared")

    def test_tolerance_absorbs_rounding(self):
        from ceo_ownership.reader import compare_readings
        self.assertEqual(
            compare_readings(1_000_000, 5e8,
                             self._reading(shares=1_000_400,
                                           shares_outstanding=5e8)).verdict,
            "agree")

    def test_parsed_figure_is_still_the_reported_one(self):
        """Disagreement flags for review; it does not silently swap in the
        model's answer. The parsed path stays the auditable one."""
        from ceo_ownership.reader import compare_readings
        a = compare_readings(1_763_964, 5_760_367,
                             self._reading(shares=1_407_667))
        self.assertEqual(a.verdict, "disagree")
        self.assertIsNone(getattr(a, "chosen", None))

    def test_agreement_counts_toward_confidence(self):
        from ceo_ownership.validate import (ValidationReport, Check,
                                            assign_confidence)
        rep = ValidationReport()
        rep.add(Check("identity_match", True, ""))
        rep.add(Check("pct_reconciliation", None, "asterisk"))
        rep.add(Check("yoy_continuity", None, "no prior year"))
        rep.add(Check("readers_agree", True, "both read 1,407,667"))
        self.assertEqual(assign_confidence(rep, "HIGH"), "HIGH")


class TestJohnsonAndJohnson(unittest.TestCase):
    """Two independent failures on one filing.

    Numerator: a legitimate zero in the deferred-units column was deleted as
    a footnote marker, shifting every later column left, so the total column
    was read as options and ADDED to common shares -- 1,763,964 instead of
    1,407,667. The group row was unaffected because its cell there is 95,564.

    Denominator: the paragraph introducing the table says "In the aggregate,
    these 5,760,367 shares represent less than 1% of the shares outstanding".
    That is a holding measured against the count, not the count.
    """

    TABLE = ("Name | Number of common shares (1) (#) | Deferred share units (2) "
             "(#) | Common shares underlying options or stock units (3) (#) | "
             "Total number of shares beneficially owned (4) (#)\n"
             "J. Duato | 356,297 | 0 | 1,051,370 | 1,407,667\n"
             "M. C. Beckerle | 0 | 15,738 | 0 | 15,738\n"
             "All Directors and executive officers as a group (21) | 890,696 | "
             "95,564 | 2,873,680 | 3,859,940")

    def _row(self, key):
        from ceo_ownership.freepath import parse_table_heuristic
        return next(r for r in parse_table_heuristic(self.TABLE)
                    if key in r.name_raw)

    def test_ceo_total_not_double_counted(self):
        r = self._row("Duato")
        self.assertEqual(r.shares_reported, 1_407_667)
        self.assertEqual(r.notes, "column=total_beneficial")

    def test_not_common_plus_total(self):
        self.assertNotEqual(self._row("Duato").shares_reported, 1_763_964)

    def test_zero_is_a_holding_not_a_footnote_marker(self):
        """Beckerle holds zero common shares and 15,738 deferred units."""
        self.assertEqual(self._row("Beckerle").shares_reported, 15_738)

    def test_group_row(self):
        self.assertEqual(self._row("group").shares_reported, 3_859_940)

    def test_total_number_of_shares_header_recognised(self):
        """"Total number of shares beneficially owned" -- words between
        "total" and "beneficially owned" defeated the stricter pattern."""
        from ceo_ownership.freepath import classify_header
        roles = classify_header([
            "Name", "Number of common shares", "Deferred share units",
            "Common shares underlying options or stock units",
            "Total number of shares beneficially owned"])
        self.assertEqual(roles[-1], "total_beneficial")

    def test_holding_compared_to_outstanding_is_not_the_count(self):
        from ceo_ownership.outstanding import shares_outstanding_from_proxy as f
        intro = ("In addition to such shares, the Directors and executive "
                 "officers as a group own/control a total of 890,696 shares. "
                 "In the aggregate, these 5,760,367 shares represent less "
                 "than 1% of the shares outstanding.")
        self.assertIsNone(f(intro)["total"])

    def test_the_real_count_still_found(self):
        from ceo_ownership.outstanding import shares_outstanding_from_proxy as f
        self.assertEqual(
            f("On February 24, 2026, there were 2,408,613,219 shares "
              "outstanding.")["total"], 2_408_613_219)

    def test_superscripts_still_stripped(self):
        """Microsoft's footnote markers must still go."""
        from ceo_ownership.freepath import parse_table_heuristic
        t = ("Name | Common Stock 1,2 | Percent of Common Stock | Additional "
             "Underlying Shares or Stock Units 3,4 | Total 5\n"
             "Satya Nadella | 900,572 | 12 | * | 0 | 900,572")
        self.assertEqual(parse_table_heuristic(t)[0].shares_reported, 900_572)


class TestSpanningHeaders(unittest.TestCase):
    """Headers split across two rows by a spanning cell.

    Regression: only the first header row was read, so Capital One's
    category label "Amount and Nature of Beneficial Ownership" -- which
    spans four columns -- was mapped onto the first data cell. Fairbank came
    back as 3,732,088 (common stock alone) instead of 4,055,254, because the
    column actually named "Total Beneficial Ownership" was in the row we
    ignored.
    """

    COF = """Name | Amount and Nature of Beneficial Ownership | Stock- Settled RSUs (2) | Total (3)
Common Stock | Stock that May Be Acquired within 60 Days (1) | Total Beneficial Ownership | Percent of Class
Richard D. Fairbank | 3,732,088 | 323,166 | 4,055,254 | * | 153,351 | 4,208,605
Ann Fritz Hackett | 673 | 55,571 | 56,244 | * | \u2014 | 56,244
All directors and executive officers as a group (29 persons) | 4,247,299 | 614,411 | 4,861,710 | 0.78% | 586,526 | 5,448,236"""

    NOW = """Name of Beneficial Owner | Shares Beneficially Owned
Number | Percent
William R. McDermott (3) | 2,212,904 | *
All current executive officers, directors and nominees as a group (15 persons) | 3,566,103 | *"""

    def _row(self, table, surname):
        from ceo_ownership.freepath import parse_table_heuristic
        return next(r for r in parse_table_heuristic(table) if surname in r.name_raw)

    def test_capital_one_total_beneficial_ownership(self):
        r = self._row(self.COF, "Fairbank")
        self.assertEqual(r.shares_reported, 4_055_254)
        self.assertEqual(r.notes, "column=total_beneficial")

    def test_not_common_stock_alone(self):
        self.assertNotEqual(self._row(self.COF, "Fairbank").shares_reported,
                            3_732_088)

    def test_rsu_and_grand_total_columns_excluded(self):
        """4,208,605 adds 153,351 unvested RSUs, which 13d-3 excludes."""
        self.assertNotEqual(self._row(self.COF, "Fairbank").shares_reported,
                            4_208_605)

    def test_roles_resolve_to_the_filers_own_layout(self):
        from ceo_ownership.freepath import parse_spanning_header
        roles, _ = parse_spanning_header(self.COF.splitlines())
        self.assertEqual(roles, ["name", "common", "options",
                                 "total_beneficial", "percent", "units",
                                 "total"])

    def test_group_row_and_percentage(self):
        r = self._row(self.COF, "group")
        self.assertEqual(r.shares_reported, 4_861_710)
        self.assertEqual(r.pct_reported, 0.78)

    def test_spanning_label_qualifies_bare_subcolumns(self):
        """ServiceNow's sub-columns are "Number" and "Percent" -- meaningless
        alone, clear as "Shares Beneficially Owned Number"."""
        from ceo_ownership.freepath import parse_spanning_header
        roles, _ = parse_spanning_header(self.NOW.splitlines())
        self.assertEqual(roles, ["name", "common", "percent"])
        self.assertEqual(self._row(self.NOW, "McDermott").shares_reported,
                         2_212_904)

    def test_single_row_headers_unaffected(self):
        r = self._row(
            "Name of Beneficial Owner | Shares Beneficially Owned | Percent of Class\n"
            "Ron M. Vachris | 52,258 | *", "Vachris")
        self.assertEqual(r.shares_reported, 52_258)


class TestCapitalOneDenominator(unittest.TestCase):
    """The count is stated in the paragraph that introduces the table.

    Regression: only the table text and the text AFTER it were searched, so
    Capital One's 621,925,120 was never seen and the scraper took 5,448,236 --
    a cell from inside the table itself.
    """

    INTRO = ("The following table lists the beneficial ownership of Capital "
             "One common stock as of February 18, 2026 by our directors, the "
             "NEOs in this proxy statement, and all directors and executive "
             "officers as a group. All percentage calculations are based on "
             "the number of shares of common stock issued and outstanding on "
             "February 18, 2026, which was 621,925,120.")
    TABLE = ("Name Common Stock Total Beneficial Ownership Total "
             "Richard D. Fairbank 3,732,088 4,055,254 4,208,605 "
             "All directors and executive officers as a group 4,861,710 5,448,236")

    def test_introduction_is_searched(self):
        from ceo_ownership.outstanding import outstanding_by_region
        found, region = outstanding_by_region(
            "<html><body>x</body></html>",
            table_context=self.TABLE, preceding=self.INTRO)
        self.assertEqual(found["total"], 621_925_120)
        self.assertEqual(region, "table_introduction")

    def test_introduction_ranks_first(self):
        from ceo_ownership.outstanding import denominator_regions
        names = [n for n, _ in denominator_regions(
            "<html></html>", table_context="t", footnotes="f", preceding="p")]
        self.assertEqual(names[0], "table_introduction")

    def test_preceding_context_is_retained(self):
        """score_table computed it and threw it away."""
        from ceo_ownership.proxy import locate_ownership_tables
        html = ("<html><body><p>" + self.INTRO + "</p>"
                "<table><tr><th>Name</th><th>Common Stock</th>"
                "<th>Total Beneficial Ownership</th></tr>"
                "<tr><td>Richard D. Fairbank</td><td>3,732,088</td>"
                "<td>4,055,254</td></tr>"
                "<tr><td>All directors and executive officers as a group</td>"
                "<td>4,247,299</td><td>4,861,710</td></tr>"
                "</table></body></html>")
        top = locate_ownership_tables(html)[0]
        self.assertIn("621,925,120", top.preceding_context)


class TestDenominatorTriangulation(unittest.TestCase):
    """Agreement between independent sources, not faith in one.

    Nothing reports shares outstanding at the proxy record date in
    structured form -- Item 6(a) mandates the disclosure, not its format.
    """

    def _rows(self):
        from ceo_ownership.extract import OwnershipRow
        grp = OwnershipRow(
            name_raw="All directors and executive officers as a group",
            shares_reported=2_182_430, pct_reported=8.4,
            options_60d=1_023_200, is_group_row=True)
        ceo = OwnershipRow(name_raw="Steven Cunningham",
                           shares_reported=197_777, pct_is_asterisk=True)
        return ceo, grp

    def _snap(self, total=24_980_000.0):
        from ceo_ownership.outstanding import OutstandingSnapshot
        return OutstandingSnapshot(
            cik=1, end_date="2026-02-28", filed_date="2026-03-05",
            accession="a", form="10-K", total_shares=total, class_count=1,
            per_class=[total], tag_used="EntityCommonStockSharesOutstanding")

    ENOVA = ("<html><body><p>The ownership percentage is based on the number "
             "of shares of our Common Stock issued and outstanding on March "
             "20, 2026, which was 24,945,366. Only stockholders of record at "
             "the close of business on March 20, 2026 (the Record Date) may "
             "vote. This amount includes 1,023,200 shares that directors and "
             "executive officers have the right to acquire within 60 days."
             "</p></body></html>")

    def test_three_sources_agree(self):
        from ceo_ownership.outstanding import resolve_denominator
        ceo, grp = self._rows()
        r = resolve_denominator(self.ENOVA, self._snap(), [ceo, grp], group_row=grp)
        self.assertGreaterEqual(r.confirmed_by, 2)
        self.assertLess(r.spread, 0.01)

    def test_corroborated_proxy_figure_is_primary(self):
        """The proxy's own figure leads once another source confirms it: it
        is the only one dated to the record date, which is also the date the
        numerator uses. No internal date mismatch."""
        from ceo_ownership.outstanding import resolve_denominator
        ceo, grp = self._rows()
        r = resolve_denominator(self.ENOVA, self._snap(), [ceo, grp], group_row=grp)
        self.assertEqual(r.source, "proxy_text")
        self.assertEqual(r.value, 24_945_366)
        self.assertEqual(r.gap_days, 0)

    def test_proxy_figure_reported_even_when_others_disagree(self):
        """The column means one thing for every company: what the proxy says.
        Disagreement is surfaced, not silently resolved by swapping source --
        swapping would also reintroduce a numerator/denominator date gap."""
        from ceo_ownership.outstanding import resolve_denominator
        ceo, grp = self._rows()
        odd = ("<html><body><p>there were 31,000,000 shares outstanding on "
               "March 20, 2026 (the Record Date).</p></body></html>")
        r = resolve_denominator(odd, self._snap(), [ceo, grp], group_row=grp)
        self.assertEqual(r.value, 31_000_000)
        self.assertEqual(r.source, "proxy_text")
        self.assertGreater(r.disagreement, 0.15)
        self.assertEqual(r.confirmed_by, 0)

    def test_disagreement_magnitude_recorded(self):
        from ceo_ownership.outstanding import resolve_denominator
        ceo, grp = self._rows()
        r = resolve_denominator(self.ENOVA, self._snap(), [ceo, grp], group_row=grp)
        self.assertLess(r.disagreement, 0.01)

    def test_bad_scrape_still_rejected(self):
        from ceo_ownership.outstanding import resolve_denominator
        ceo, grp = self._rows()
        bad = ("<html><body><p>This amount includes 1,023,200 shares that "
               "directors have the right to acquire and were outstanding."
               "</p></body></html>")
        r = resolve_denominator(bad, self._snap(), [ceo, grp], group_row=grp)
        self.assertNotEqual(r.value, 1_023_200)

    def test_drift_is_immaterial_at_these_magnitudes(self):
        """A 20-day gap moves Enova's CEO from 0.793% to 0.792%."""
        self.assertAlmostEqual(100 * 197_777 / 24_980_000,
                               100 * 197_777 / 24_945_366, places=2)

    def test_multi_class_falls_back_to_prose(self):
        """companyfacts drops the class dimension, so Meta and Alphabet get
        nothing from the tagged source and prose must carry them."""
        from ceo_ownership.outstanding import resolve_denominator
        meta = ("<html><body><p>As of the record date, 2,151,469,000 shares "
                "of our Class A common stock and 342,152,000 shares of our "
                "Class B common stock were outstanding.</p></body></html>")
        r = resolve_denominator(meta, None, [], group_row=None)
        self.assertEqual(r.value, 2_493_621_000)
        self.assertEqual(r.source, "proxy_text")

    def test_date_parsing(self):
        from ceo_ownership.outstanding import date_gap_days, _to_iso
        self.assertEqual(_to_iso("March 20, 2026"), "2026-03-20")
        self.assertEqual(_to_iso("2026-03-20"), "2026-03-20")
        self.assertIsNone(_to_iso("not a date"))
        self.assertEqual(date_gap_days("2026-02-28", "March 20, 2026"), 20)

    def test_group_row_floor_rejects_impossible_value(self):
        """A denominator below the shares insiders hold cannot be right."""
        from ceo_ownership.outstanding import resolve_denominator
        ceo, grp = self._rows()
        bad = ("<html><body><p>This amount includes 1,023,200 shares that "
               "directors have the right to acquire and were outstanding."
               "</p></body></html>")
        r = resolve_denominator(bad, None, [ceo, grp], group_row=grp)
        self.assertNotEqual(r.value, 1_023_200)
        self.assertGreater(r.value, 20_000_000)

    def test_implied_subtracts_group_options(self):
        """13d-3(d)(1)(i) puts the group's own options in its denominator --
        4.1% of Enova. Without subtracting them the estimate runs high."""
        from ceo_ownership.outstanding import implied_from_row
        _, grp = self._rows()
        self.assertAlmostEqual(implied_from_row(grp), 24_958_110, delta=100)

    def test_disagreement_is_reported(self):
        from ceo_ownership.outstanding import resolve_denominator
        ceo, grp = self._rows()
        r = resolve_denominator(self.ENOVA, self._snap(40_000_000.0),
                                [ceo, grp], group_row=grp)
        self.assertGreater(r.spread, 0.05)

    def test_record_date_extracted(self):
        from ceo_ownership.outstanding import record_date_from_proxy
        self.assertIn("March 20", record_date_from_proxy(self.ENOVA) or "")

    def test_no_sources_returns_nothing(self):
        from ceo_ownership.outstanding import resolve_denominator
        r = resolve_denominator("<html></html>", None, [], group_row=None)
        self.assertIsNone(r.value)


class TestEnovaDenominator(unittest.TestCase):
    """Enova: the denominator came from a footnote about acquirable shares.

    Regression: "This amount includes 1,023,200 shares that directors and
    executive officers have the right to acquire within 60 days" was taken as
    shares outstanding. Its CEO was reported at 19.329% instead of 0.793% --
    a 24x overstatement on the second-largest figure in the panel, with a
    share count that was entirely correct.
    """

    ENOVA = ("The ownership percentage for each individual named below is "
             "based on the number of shares of our Common Stock issued and "
             "outstanding on March 20, 2026, which was 24,945,366. Includes "
             "all of our current directors and all executive officers "
             "employed by us as of March 20, 2026. This amount includes "
             "1,023,200 shares that directors and executive officers have "
             "the right to acquire within 60 days following March 20, 2026.")

    def test_acquirable_footnote_not_used(self):
        from ceo_ownership.outstanding import shares_outstanding_from_proxy as f
        self.assertEqual(f(self.ENOVA)["total"], 24_945_366)

    def test_group_row_bounds_the_denominator(self):
        """All directors and officers cannot hold more than the company."""
        from ceo_ownership.outstanding import denominator_is_credible as d
        self.assertFalse(d(1_023_200, 2_182_430)[0])
        self.assertTrue(d(24_945_366, 2_182_430)[0])

    def test_resulting_percentage(self):
        self.assertAlmostEqual(100 * 197_777 / 24_945_366, 0.793, places=2)

    def test_no_group_row_means_no_objection(self):
        from ceo_ownership.outstanding import denominator_is_credible as d
        self.assertTrue(d(24_945_366, None)[0])


class TestAuthorizedCapital(unittest.TestCase):
    def test_authorized_shares_not_taken_as_outstanding(self):
        """Regression: Exxon's charter recital -- "authorized capital
        consisting of 9,000,000,000 shares" -- beat the real 4,179,747,572,
        because the scraper takes the largest figure per class."""
        from ceo_ownership.outstanding import shares_outstanding_from_proxy as f
        text = ("WHEREAS, ExxonMobil has authorized capital consisting of "
                "9,000,000,000 shares of common stock outstanding under the "
                "charter. Ownership percentage is based on shares outstanding "
                "on December 31, 2025, of 4,179,747,572.")
        r = f(text)
        self.assertEqual(r["total"], 4_179_747_572)


class TestTableDiscrimination(unittest.TestCase):
    def test_group_row_phrasings(self):
        from ceo_ownership.proxy import GROUP_ROW_RE
        for r in ["All directors and executive officers as a group (23 persons)",
                  "Directors and executive officers as a group (19 persons)",
                  "All current directors and executive officers as a group",
                  "Directors and named executive officers as a group (12)",
                  # GE Aerospace says "executives", not "officers"
                  "Current directors & executives as a group (16 people)"]:
            self.assertTrue(GROUP_ROW_RE.search(r), r)
        self.assertIsNone(GROUP_ROW_RE.search("Susan L. Decker"))
        self.assertIsNone(GROUP_ROW_RE.search("Total"))

    def test_address_column_marks_five_percent_table(self):
        """Item 403(a) requires 5% owners' addresses; 403(b) does not."""
        from ceo_ownership.proxy import ADDRESS_HEADER_RE
        self.assertTrue(ADDRESS_HEADER_RE.search(
            "Name of beneficial owner Address of beneficial owner Common stock"))
        self.assertIsNone(ADDRESS_HEADER_RE.search(
            "Beneficial ownership Name Common stock (#) SARs/Options"))


class TestWalmartCommonTitle(unittest.TestCase):
    def test_bare_common_counts(self):
        """Regression: Walmart uses securityTitle 'Common'; all 8 CEO
        holding lines were skipped and the total came out as zero."""
        self.assertEqual(classify_security("Common")[0], "common")
        self.assertEqual(classify_security("Shares")[0], "common")

    def test_contingent_still_excluded(self):
        self.assertEqual(classify_security("Restricted Stock Units")[0],
                         "contingent")


class TestCertificationFallbacks(unittest.TestCase):
    """Filenames are not dependable; size and content are."""

    def test_small_docs_offered_when_no_ex31_name(self):
        """Regression: Rollins and Espey file certifications whose names do
        not contain a recognisable "ex31", so the search found nothing."""
        from ceo_ownership.certification import _pick_exhibits, _small_documents
        idx = {"directory": {"item": [
            {"name": "rol-20241231.htm", "type": "10-K", "size": "4200000"},
            {"name": "rol-1231202xq4a.htm", "type": "", "size": "9800"},
            {"name": "rol-1231202xq4c.htm", "type": "", "size": "4100"},
            {"name": "chart.jpg", "type": "", "size": "60000"},
            {"name": "big-exhibit.htm", "type": "", "size": "900000"},
        ]}}
        self.assertEqual(_pick_exhibits(idx), [])
        small = [n for n, _ in _small_documents(idx, set())]
        self.assertIn("rol-1231202xq4c.htm", small)
        self.assertIn("rol-1231202xq4a.htm", small)
        self.assertNotIn("chart.jpg", small)          # not htm/txt
        self.assertNotIn("big-exhibit.htm", small)    # over the size ceiling
        self.assertNotIn("rol-20241231.htm", small)   # the report itself

    def test_smallest_first(self):
        from ceo_ownership.certification import _small_documents
        idx = {"directory": {"item": [
            {"name": "b.htm", "type": "", "size": "9000"},
            {"name": "a.htm", "type": "", "size": "3000"},
        ]}}
        self.assertEqual([n for n, _ in _small_documents(idx, set())],
                         ["a.htm", "b.htm"])

    def test_named_exhibits_not_duplicated_by_fallback(self):
        from ceo_ownership.certification import _pick_exhibits, _small_documents
        idx = {"directory": {"item": [
            {"name": "a10-kexhibit311.htm", "type": "EX-31.1", "size": "9000"},
        ]}}
        named = _pick_exhibits(idx)
        self.assertEqual(len(named), 1)
        self.assertEqual(_small_documents(idx, {n for n, _ in named}), [])

    def test_plain_text_strips_markup(self):
        from ceo_ownership.certification import _plain_text
        out = _plain_text("<p>I, <b>Jane Roe</b>, certify&nbsp;that:</p>")
        self.assertIn("Jane Roe", out)
        self.assertNotIn("<", out)


class TestCitigroupExhibitNaming(unittest.TestCase):
    """Citigroup's 10-Q, taken from its real filing directory.

    Regression: the abbreviation "exh" was unrecognised -- the pattern
    accepted "ex" and "exhibit" but not "exh" -- so EX-31.01 sat in a
    177-document filing unmatched and the company was reported as having no
    Section 302 certification at all.
    """

    CITI = {"directory": {"item": [
        {"name": "0000831001-26-000045-index.html", "type": "text.gif"},
        {"name": "c-20260630.htm", "type": "text.gif", "size": "14543949"},
        {"name": "R7.htm", "type": "text.gif", "size": "3000"},
        {"name": "R15.htm", "type": "text.gif", "size": "3200"},
        {"name": "citi-exh2201x6302026.htm", "type": "text.gif", "size": "9000"},
        {"name": "citi-exh3101x6302026.htm", "type": "text.gif", "size": "9500"},
        {"name": "citi-exh3102x6302026.htm", "type": "text.gif", "size": "9500"},
        {"name": "citi-exh3201x6302026.htm", "type": "text.gif", "size": "8800"},
    ]}}

    def test_exh_abbreviation_matched(self):
        from ceo_ownership.certification import _pick_exhibits
        names = [n for n, _ in _pick_exhibits(self.CITI)]
        self.assertIn("citi-exh3101x6302026.htm", names)

    def test_peo_certification_ranks_ahead_of_cfo(self):
        from ceo_ownership.certification import _pick_exhibits
        names = [n for n, _ in _pick_exhibits(self.CITI)]
        self.assertLess(names.index("citi-exh3101x6302026.htm"),
                        names.index("citi-exh3102x6302026.htm"))

    def test_other_exhibit_numbers_not_matched(self):
        from ceo_ownership.certification import _pick_exhibits
        names = [n for n, _ in _pick_exhibits(self.CITI)]
        self.assertNotIn("citi-exh3201x6302026.htm", names)  # EX-32
        self.assertNotIn("citi-exh2201x6302026.htm", names)  # EX-22

    def test_viewer_fragments_excluded(self):
        """177-document filings bury exhibits under tiny R##.htm fragments,
        which sort to the front of a size-ordered list."""
        from ceo_ownership.certification import _pick_exhibits, _small_documents
        small = [n for n, _ in _small_documents(
            self.CITI, {n for n, _ in _pick_exhibits(self.CITI)})]
        self.assertNotIn("R7.htm", small)
        self.assertNotIn("R15.htm", small)
        self.assertNotIn("0000831001-26-000045-index.html", small)

    def test_all_known_naming_conventions(self):
        from ceo_ownership.certification import _pick_exhibits
        for name in ["a10-kexhibit311.htm", "msft-ex31_1.htm",
                     "d908201dex311.htm", "ex31.htm", "rol-ex-31.1.htm",
                     "wmtexhibit311fy27q1.htm", "citi-exh3101x6302026.htm"]:
            idx = {"directory": {"item": [
                {"name": name, "type": "", "size": "9000"}]}}
            self.assertTrue(_pick_exhibits(idx), name)

    def test_unknown_size_does_not_exclude(self):
        """Regression: the test was `0 < size <= MAX`, so a filing whose
        index omits sizes returned no candidates and the fallback never ran."""
        from ceo_ownership.certification import _small_documents
        idx = {"directory": {"item": [{"name": "cert.htm", "type": ""}]}}
        self.assertEqual([n for n, _ in _small_documents(idx, set())],
                         ["cert.htm"])


class TestNameCleaning(unittest.TestCase):
    def test_mc_names_not_split(self):
        """Regression: "Doug McMillon" became "Doug Mc Millon"."""
        from ceo_ownership.peo import _clean_name
        from ceo_ownership.validate import names_match
        self.assertEqual(_clean_name("Doug McMillon"), "Doug McMillon")
        self.assertEqual(_clean_name("Robert MacDonald"), "Robert MacDonald")
        self.assertGreaterEqual(
            names_match(_clean_name("Doug McMillon"), "McMillon C Douglas"), 0.7)

    def test_run_together_initial_still_split(self):
        from ceo_ownership.peo import _clean_name
        self.assertEqual(_clean_name("Ron M.Vachris"), "Ron M. Vachris")


class TestFormFourDocumentPath(unittest.TestCase):
    def test_xsl_rendered_path_is_stripped(self):
        """primaryDocument points at xslF345X05/..., which serves HTML."""
        name = "xslF345X05/wf-form4_173456.xml"
        self.assertEqual(name.rsplit("/", 1)[-1], "wf-form4_173456.xml")


class TestCertification(unittest.TestCase):
    """SOX 302 signature: the signer IS the principal executive officer."""

    def test_plain_certification(self):
        from ceo_ownership.certification import extract_names_from_certification as f
        text = ("EXHIBIT 31.1 CERTIFICATION OF PRINCIPAL EXECUTIVE OFFICER "
                "I, Timothy D. Cook, certify that: 1. I have reviewed this "
                "annual report on Form 10-K of Apple Inc.;")
        self.assertEqual(f(text), ["Timothy D. Cook"])

    def test_title_after_name_is_stripped(self):
        from ceo_ownership.certification import extract_names_from_certification as f
        self.assertEqual(
            f("I, Jane A. Roe, Chief Executive Officer of Acme Corp, certify"),
            ["Jane A. Roe"])

    def test_all_caps_and_hyphenated(self):
        from ceo_ownership.certification import extract_names_from_certification as f
        self.assertEqual(f("I, RON M. VACHRIS, certify that:"),
                         ["RON M. VACHRIS"])
        self.assertEqual(f("I, Jean-Luc O'Brien-Smith, certify that:"),
                         ["Jean-Luc O'Brien-Smith"])

    def test_boilerplate_is_not_a_name(self):
        """Regression: 'I, the undersigned, hereby state' parsed as a person."""
        from ceo_ownership.certification import extract_names_from_certification as f
        self.assertEqual(f("I, the undersigned, hereby state"), [])
        self.assertEqual(f("I, the Registrant, certify"), [])

    def test_combined_certification_returns_all_signers(self):
        from ceo_ownership.certification import extract_names_from_certification as f
        self.assertEqual(
            f("I, Fred Bock, certify that: ... I, Alice Chen, certify that:"),
            ["Fred Bock", "Alice Chen"])

    def test_exhibit_found_by_filename_when_type_absent(self):
        """Regression: index.json does NOT carry the EDGAR type "EX-31.1",
        and real filenames do not start with "ex31"."""
        from ceo_ownership.certification import _pick_exhibits
        idx = {"directory": {"item": [
            {"name": "a10-kexhibit312.htm", "type": ""},
            {"name": "a10-kexhibit311.htm", "type": ""},
            {"name": "d908201dex311.htm", "type": ""},
            {"name": "aapl-20250927.htm", "type": ""}]}}
        names = [n for n, _ in _pick_exhibits(idx)]
        self.assertIn("a10-kexhibit311.htm", names)
        self.assertIn("d908201dex311.htm", names)
        # the CFO certification must rank last
        self.assertEqual(names[-1], "a10-kexhibit312.htm")

    def test_declared_type_still_preferred_when_present(self):
        from ceo_ownership.certification import _pick_exhibits
        idx = {"directory": {"item": [
            {"name": "b.htm", "type": "EX-31.2"},
            {"name": "a.htm", "type": "EX-31.1"}]}}
        self.assertEqual(_pick_exhibits(idx)[0][0], "a.htm")

    def test_no_candidates(self):
        from ceo_ownership.certification import _pick_exhibits
        self.assertEqual(_pick_exhibits({"directory": {"item": []}}), [])

    def test_cert_name_matches_edgar_form4_name(self):
        """The whole point: formats differ, matching bridges them."""
        from ceo_ownership.validate import names_match
        self.assertGreaterEqual(names_match("RON M. VACHRIS",
                                            "Vachris Roland Michael"), 0.7)
        self.assertGreaterEqual(names_match("Timothy D. Cook",
                                            "COOK TIMOTHY D"), 0.7)


if __name__ == "__main__":
    unittest.main(verbosity=2)
