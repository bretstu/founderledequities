"""When an issuer's filing history lives under a different CIK."""
from fle.successor import (needs_predecessor, candidates_from_accessions,
                           find_predecessor)

XOM = {"insiderTransactionForIssuerExists": 0, "_filings": [
    {"form": "10-Q",    "accessionNumber": "0000034088-26-000093"},
    {"form": "8-K",     "accessionNumber": "0002115436-26-000006"},
    {"form": "8-K",     "accessionNumber": "0002115436-26-000003"},
    {"form": "S-8 POS", "accessionNumber": "0001193125-26-292536"},
    {"form": "S-8 POS", "accessionNumber": "0001193125-26-292549"},
    {"form": "8-K12B",  "accessionNumber": "0001193125-26-291990"}]}


def test_edgar_states_the_condition_itself():
    """`insiderTransactionForIssuerExists` is 0, which is better than counting
    Section 16 filings ourselves: it is the filing system's own answer rather
    than our inference from a list we may have paged wrongly."""
    assert needs_predecessor(XOM)
    # a company with insider filings is never touched
    assert not needs_predecessor({"insiderTransactionForIssuerExists": 1,
                                  "_filings": [{"form": "10-K",
                                                "accessionNumber": "0000320193-26-1"}]})
    # nor is a shell with no periodic reports at all
    assert not needs_predecessor({"insiderTransactionForIssuerExists": 0,
                                  "_filings": [{"form": "S-1",
                                                "accessionNumber": "0000001-26-1"}]})


def test_the_predecessor_is_in_the_accession_number():
    """An accession is {transmitter}-{year}-{sequence}. ExxonMobil Holdings'
    10-Q is 0000034088-26-000093 -- transmitted by the predecessor. No list to
    maintain, no company names to compare."""
    assert candidates_from_accessions(XOM, 2115436)[0] == 34088


def test_a_filing_agent_is_tried_after_the_rare_transmitter():
    """0001193125 is a filing agent and transmits everything; a predecessor
    typically transmits one or two while the changeover settles. Ordering by
    rarity puts the likelier candidate first, and being wrong only costs a
    check, since each one is verified."""
    order = candidates_from_accessions(XOM, 2115436)
    assert order == [34088, 1193125]


def test_a_candidate_is_verified_not_trusted():
    """Being transmitted by someone proves nothing. Having this company's
    certified chief executive among your insiders is not coincidence."""
    import json
    import xml.etree.ElementTree as ET
    import fle.successor as S

    def owner_doc(name):
        return (f"<ownershipDocument><reportingOwner><reportingOwnerId>"
                f"<rptOwnerCik>1555145</rptOwnerCik><rptOwnerName>{name}"
                f"</rptOwnerName></reportingOwnerId>"
                f"<reportingOwnerRelationship><isOfficer>1</isOfficer>"
                f"</reportingOwnerRelationship></reportingOwner>"
                f"</ownershipDocument>")

    class _C:
        def submissions(self, cik):
            if cik == 34088:
                return {"name": "EXXON MOBIL CORP", "_filings": [
                    {"form": "3", "accessionNumber": "0000034088-12-1",
                     "primaryDocument": "d.xml", "filingDate": "2012-11-30"}]}
            return {"name": "A FILING AGENT", "_filings": []}   # no Section 16

        def get(self, url, use_cache=True):
            return owner_doc("Woods Darren W")

    real = S.find_predecessor
    pre = find_predecessor(_C(), 2115436, "Darren W. Woods", subs=XOM)
    assert pre.cik == 34088
    assert pre.matched_owner == "Woods Darren W"
    assert real is S.find_predecessor


def test_the_wrong_person_means_refusal():
    """Point it at a company that merely transmitted a filing and the chief
    executive is not there, so it declines rather than publishing someone
    else's holdings."""
    class _C:
        def submissions(self, cik):
            return {"name": "SOMEONE ELSE", "_filings": [
                {"form": "3", "accessionNumber": "0000001-12-1",
                 "primaryDocument": "d.xml", "filingDate": "2012-01-01"}]}

        def get(self, url, use_cache=True):
            return ("<ownershipDocument><reportingOwner><reportingOwnerId>"
                    "<rptOwnerCik>9</rptOwnerCik><rptOwnerName>Somebody Else"
                    "</rptOwnerName></reportingOwnerId></reportingOwner>"
                    "</ownershipDocument>")

    pre = find_predecessor(_C(), 2115436, "Darren W. Woods", subs=XOM)
    assert pre.cik is None
    assert "Darren W. Woods" in pre.note


def test_it_only_runs_when_the_normal_path_found_nothing():
    """493 companies produced a figure because they have Section 16 filings.
    None of them can reach this code."""
    import inspect
    from fle import ownership
    src = inspect.getsource(ownership.build)
    assert "if not led.lines and not led.owner_cik:" in src
    assert "find_predecessor(client, cik, owner_name)" in src
