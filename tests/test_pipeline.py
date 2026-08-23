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
        self.assertEqual(normalize_name("Iger, Robert A."), ["robert", "iger"])

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


class TestTableDiscrimination(unittest.TestCase):
    def test_group_row_phrasings(self):
        from ceo_ownership.proxy import GROUP_ROW_RE
        for r in ["All directors and executive officers as a group (23 persons)",
                  "Directors and executive officers as a group (19 persons)",
                  "All current directors and executive officers as a group",
                  "Directors and named executive officers as a group (12)"]:
            self.assertTrue(GROUP_ROW_RE.search(r), r)
        self.assertIsNone(GROUP_ROW_RE.search("Susan L. Decker"))

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
