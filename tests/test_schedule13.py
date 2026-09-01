"""The Schedule 13D/G fallback, on a fixture reconstructed from the real
Lütke 13G/A cover text (accession 0001341004-24-000043, sc13ga8.htm) as
pasted from a live probe. First install should verify end-to-end against
the real document."""
import pytest

from fle.schedule13 import (Stake, _schedule_doc, _stake_for_person,
                            is_foreign_reporter, stake_from_schedule13)

LUTKE_PAGE = (
    "CUSIP No. 82509L107 Schedule 13G/A 1 NAME OF REPORTING PERSON "
    "TOBIAS L\u00dcTKE 2 CHECK THE APPROPRIATE BOX IF A MEMBER OF A GROUP "
    "(a) \u2610 (b) \u2610 3 SEC USE ONLY 4 CITIZENSHIP OR PLACE OF "
    "ORGANIZATION Canadian and German NUMBER OF SHARES BENEFICIALLY OWNED "
    "BY EACH REPORTING PERSON WITH 5 SOLE VOTING POWER 13,363,790 (1) "
    "6 SHARED VOTING POWER 67,634,192 (2) 7 SOLE DISPOSITIVE POWER "
    "13,363,790 (1) 8 SHARED DISPOSITIVE POWER 67,634,192 (2) "
    "9 AGGREGATE AMOUNT BENEFICIALLY OWNED BY EACH REPORTING PERSON "
    "80,997,982 (1)(2) 10 CHECK BOX IF THE AGGREGATE AMOUNT IN ROW (9) "
    "EXCLUDES CERTAIN SHARES \u2610 11 PERCENT OF CLASS REPRESENTED BY "
    "AMOUNT IN ROW (9) 6.3% (3) 12 TYPE OF REPORTING PERSON IN ")

INVESTOR_PAGE = (
    "CUSIP No. 111111111 Schedule 13D 1 NAME OF REPORTING PERSON "
    "Shopify Strategic Holdings 3 LLC 2 CHECK THE APPROPRIATE BOX "
    "9 AGGREGATE AMOUNT BENEFICIALLY OWNED BY EACH REPORTING PERSON "
    "30,305,609 (1) 11 PERCENT OF CLASS REPRESENTED BY AMOUNT IN ROW (9) "
    "7.7% ")


def test_the_matching_persons_page_yields_the_stake():
    hit = _stake_for_person(INVESTOR_PAGE + " " + LUTKE_PAGE, "Tobias L\u00fctke")
    assert hit is not None
    shares, pct, person = hit
    assert shares == 80_997_982 and pct == 6.3
    assert "L\u00dcTKE" in person.upper()


def test_the_company_as_investor_never_matches_its_ceo():
    # Shopify's own feed carries 13Ds it FILED about other companies;
    # the reporting-person match is the subject check
    assert _stake_for_person(INVESTOR_PAGE, "Tobias L\u00fctke") is None


def test_the_schedule_is_picked_by_size_not_alphabet():
    index = {"directory": {"item": [
        {"name": "0001341004-24-000043-index.html", "size": ""},
        {"name": "ex1.htm", "size": "5729"},
        {"name": "image0.jpg", "size": "631"},
        {"name": "sc13ga8.htm", "size": "70118"}]}}
    assert _schedule_doc(index) == "sc13ga8.htm"


def test_end_to_end_with_entity_escapes():
    class Client:
        def submissions(self, cik):
            return {"_filings": [
                {"form": "SC 13G/A", "accessionNumber": "0001341004-24-000043",
                 "filingDate": "2024-02-13"},
                {"form": "40-F", "accessionNumber": "a-2",
                 "filingDate": "2024-05-01"}]}
        def filing_index(self, cik, acc):
            return {"directory": {"item": [
                {"name": "ex1.htm", "size": "5729"},
                {"name": "sc13ga8.htm", "size": "70118"}]}}
        def primary_document(self, cik, acc, name):
            assert name == "sc13ga8.htm"
            # the real document writes the umlaut as an entity
            return ("<html><body><table><tr><td>" +
                    LUTKE_PAGE.replace("L\u00dcTKE", "L&#220;TKE") +
                    "</td></tr></table></body></html>")
    stake = stake_from_schedule13(Client(), 1594805, "Tobias L\u00fctke")
    assert stake and stake.shares == 80_997_982 and stake.percent == 6.3
    assert stake.filing_date == "2024-02-13" and "sc13ga8.htm" in stake.url


def test_foreign_reporter_detection():
    assert is_foreign_reporter({"_filings": [{"form": "40-F"}, {"form": "6-K"}]})
    assert not is_foreign_reporter({"_filings": [{"form": "10-K"}, {"form": "40-F"}]})
    assert not is_foreign_reporter({"_filings": [{"form": "10-K"}]})


def test_a_fetch_failure_raises_not_absent():
    class Broken:
        def submissions(self, cik):
            return {"_filings": [{"form": "SC 13G", "accessionNumber": "a-1",
                                  "filingDate": "2024-01-01"}]}
        def filing_index(self, cik, acc):
            raise RuntimeError("429")
    with pytest.raises(RuntimeError):
        stake_from_schedule13(Broken(), 1, "Anyone")
