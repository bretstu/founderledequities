"""UNITS REPORTED AS COMMON STOCK (2026-09-29). Found by a blind re-derivation of
two random companies (SHLS, CASH): some filers report restricted stock units in
Table I as common stock on the grant date, with only the footnote saying so,
and the stake counts them from the grant. The ledger now recognises the grant
from the footnote, the record carries a caution, and the company page says so.
No figure changes: a vest from Table I files no row, and the unvested remainder
would be an estimate."""
import os
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fle.ledger import units_as_common, _rows  # noqa: E402

SHOALS = "The reported securities are restricted stock units (\"RSUs\") that each represents a right to receive one share of the Issuer's Class A Common Stock. The reported RSUs will vest in three equal installments on March 4, 2025, March 4, 2026, and March 4, 2027."
PATHWARD_RSA = "All of which 20,000 shares are restricted stock granted to the reporting person, which shares of restricted stock are scheduled to vest in five equal installments."
PATHWARD_PSU_SETTLED = "Represents common stock received upon vesting on November 7, 2024 of performance share units (\"PSUs\") granted on November 2, 2021."
WITHHOLD = "Represents 27,639 RSUs that have been withheld by the Issuer to satisfy its income tax withholding obligations in connection with vesting of 61,776 RSUs and does not represent a sale."


def test_a_unit_grant_is_recognised_and_a_stock_award_is_not():
    assert units_as_common(SHOALS), "shoals: units filed as common on the grant"
    assert not units_as_common(PATHWARD_RSA), "restricted stock is shares, issued and votable"
    assert not units_as_common(PATHWARD_PSU_SETTLED), "shares received when units vested are shares"
    assert not units_as_common(""), "no footnote, no claim"


def test_the_rows_carry_their_own_footnotes():
    xml = f"""<ownershipDocument><nonDerivativeTable>
      <nonDerivativeTransaction><securityTitle><value>Class A Common Stock</value></securityTitle>
        <transactionDate><value>2024-02-27</value></transactionDate>
        <transactionCoding><transactionCode>A</transactionCode></transactionCoding>
        <transactionAmounts><transactionShares><value>142950</value></transactionShares><transactionPricePerShare><value>0</value></transactionPricePerShare><transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
        <postTransactionAmounts><sharesOwnedFollowingTransaction><value>245909</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
        <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
        <footnoteId id="F1"/></nonDerivativeTransaction>
    </nonDerivativeTable><footnotes><footnote id="F1">{SHOALS}</footnote></footnotes></ownershipDocument>"""
    rows = _rows(ET.fromstring(xml), "4", "2024-02-28", "0001831651-24-000020")
    assert len(rows) == 1 and rows[0].code == "A" and rows[0].moved == 142950
    assert "restricted stock units" in rows[0].notes and units_as_common(rows[0].notes)


def test_the_about_page_says_what_is_counted():
    about = open(os.path.join(ROOT, "about.html"), encoding="utf-8").read()
    assert "Options are never counted" in about
    assert "units that have not yet vested" in about, "the finding is stated, not hidden"
    assert "have not vested are not counted" not in about, "the sentence the audit showed was false is gone"
    assert 'class="kind xfer">Transfer' in about, "five kinds, as everywhere else on the site"
    assert about.count("What ownership means here") == 1 and "What counts as ownership" not in about, "one definition"


def test_the_page_says_so_where_the_caution_is_set():
    js = open(os.path.join(ROOT, "assets", "company-page.js"), encoding="utf-8").read()
    assert "restricted stock units this filer reports as shares before they vest" in js
    src = open(os.path.join(ROOT, "fle", "ownership.py"), encoding="utf-8").read()
    assert "restricted stock units this filer reports as shares before they vest" in src, "the page matches the caution the record writes"
