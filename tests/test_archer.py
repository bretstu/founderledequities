"""ARCHER (2026-09-16): the walk over the three filings that took the founder's record to zero, under the cover read both ways."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def _archer_docs():
    """The three real filings, and a client that serves them."""
    head = ('<ownershipDocument><periodOfReport>{p}</periodOfReport><issuer><issuerCik>0001824502</issuerCik></issuer>'
            '<reportingOwner><reportingOwnerId><rptOwnerCik>0001882604</rptOwnerCik><rptOwnerName>Goldstein Adam</rptOwnerName></reportingOwnerId>'
            '<reportingOwnerRelationship><isOfficer>1</isOfficer><officerTitle>CEO</officerTitle></reportingOwnerRelationship></reportingOwner>')

    def tx(t, code, sh, ad, after, di, nat="", d="2024-11-18"):
        return (f'<nonDerivativeTransaction><securityTitle><value>{t}</value></securityTitle><transactionDate><value>{d}</value></transactionDate><transactionCoding><transactionCode>{code}</transactionCode></transactionCoding>'
                f'<transactionAmounts><transactionShares><value>{sh}</value></transactionShares><transactionAcquiredDisposedCode><value>{ad}</value></transactionAcquiredDisposedCode></transactionAmounts>'
                f'<postTransactionAmounts><sharesOwnedFollowingTransaction><value>{after}</value></sharesOwnedFollowingTransaction></postTransactionAmounts><ownershipNature><directOrIndirectOwnership><value>{di}</value></directOrIndirectOwnership><natureOfOwnership><value>{nat}</value></natureOfOwnership></ownershipNature></nonDerivativeTransaction>')

    def hold(t, after, di, nat=""):
        return (f'<nonDerivativeHolding><securityTitle><value>{t}</value></securityTitle><postTransactionAmounts><sharesOwnedFollowingTransaction><value>{after}</value></sharesOwnedFollowingTransaction></postTransactionAmounts>'
                f'<ownershipNature><directOrIndirectOwnership><value>{di}</value></directOrIndirectOwnership><natureOfOwnership><value>{nat}</value></natureOfOwnership></ownershipNature></nonDerivativeHolding>')

    def dtx(t, code, sh, after, di, nat="", d="2024-11-18", under="Class A Common Stock"):
        return (f'<derivativeTransaction><securityTitle><value>{t}</value></securityTitle><transactionDate><value>{d}</value></transactionDate><transactionCoding><transactionCode>{code}</transactionCode></transactionCoding>'
                f'<transactionAmounts><transactionShares><value>{sh}</value></transactionShares></transactionAmounts><underlyingSecurity><underlyingSecurityTitle><value>{under}</value></underlyingSecurityTitle><underlyingSecurityShares><value>{sh}</value></underlyingSecurityShares></underlyingSecurity>'
                f'<postTransactionAmounts><sharesOwnedFollowingTransaction><value>{after}</value></sharesOwnedFollowingTransaction></postTransactionAmounts><ownershipNature><directOrIndirectOwnership><value>{di}</value></directOrIndirectOwnership><natureOfOwnership><value>{nat}</value></natureOfOwnership></ownershipNature></derivativeTransaction>')

    def dh(t, after, di, nat="", under="Class A Common Stock"):
        return (f'<derivativeHolding><securityTitle><value>{t}</value></securityTitle><underlyingSecurity><underlyingSecurityTitle><value>{under}</value></underlyingSecurityTitle><underlyingSecurityShares><value>{after}</value></underlyingSecurityShares></underlyingSecurity>'
                f'<postTransactionAmounts><sharesOwnedFollowingTransaction><value>{after}</value></sharesOwnedFollowingTransaction></postTransactionAmounts><ownershipNature><directOrIndirectOwnership><value>{di}</value></directOrIndirectOwnership><natureOfOwnership><value>{nat}</value></natureOfOwnership></ownershipNature></derivativeHolding>')
    A, B = "Class A Common Stock", "Class B Common Stock"
    docs = {"a1": head.format(p="2024-11-18") + tx(A, "C", 5002306, "A", 5002306, "D") + hold(A, 139526, "I", "By Capri Growth LLC")
                  + dtx("Performance Based Restricted Stock Units", "M", 5002306, 10004612, "D", under=B) + dtx(B, "M", 5002306, 11463959, "D") + dtx(B, "C", 5002306, 6461653, "D") + dh(B, 27756278, "I", "By Capri Growth LLC") + '</ownershipDocument>',
            "a2": head.format(p="2024-11-19") + tx(A, "S", 805170, "D", 4197136, "D", d="2024-11-19") + tx(A, "S", 1372247, "D", 2824889, "D", d="2024-11-19") + tx(A, "S", 829761, "D", 1995128, "D", d="2024-11-19") + tx(A, "P", 19762, "A", 2014890, "D", d="2024-11-19") + hold(A, 139526, "I", "By Capri Growth LLC") + '</ownershipDocument>',
            "a3": head.format(p="2024-12-31") + tx(A, "C", 6461653, "A", 8476543, "D", d="2024-12-31") + tx(A, "C", 27756278, "A", 27895804, "I", "By Capri Growth LLC", d="2024-12-31")
                  + dtx(B, "C", 6461653, 0, "D", d="2024-12-31") + dtx(B, "C", 27756278, 0, "I", "By Capri Growth LLC", d="2024-12-31") + '</ownershipDocument>'}

    class _E:
        def filing_index(self, cik, acc):
            return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}

        def get(self, url, use_cache=True):
            return next(v for k, v in docs.items() if k in url)

    mine = [{"form": "4", "accessionNumber": k, "filingDate": d, "reportDate": r, "primaryDocument": "d.xml"} for k, d, r in [("a1", "2024-11-19", "2024-11-18"), ("a2", "2024-11-22", "2024-11-19"), ("a3", "2025-01-03", "2024-12-31")]]
    return docs, mine, _E


def test_archer_a_convertible_class_b_survives_a_class_a_only_filing_and_the_final_conversion():
    """ARCHER (2026-09-16), the three filings that took Goldstein's record to
    zero, replayed with the class list the fixed cover reader builds for
    2024 (two bare contexts, no member names). 18 Nov: a PRSU tranche
    vests into Class B and 5.0M converts to Class A. 21 Nov: tax sales of
    Class A, no Class B rows. 31 Dec: the charter converts every Class B
    to Class A. With one class the walk wrote 34,357,457 / 2,154,416 / 0;
    with two it keeps the Class B (Table II, convertible) as its own group,
    carries it through the Class A-only filing, and lands the conversion
    without loss."""
    from fle.history import build_history
    from fle.series import Series, Point
    docs, mine, _E = _archer_docs()
    two = Series(points=[Point("2024-09-30", 425272673.0)], classes={"2024": {"c-4": 389161681.0, "c-5": 36110992.0}})
    got = [(s.date, round(s.shares), s.groups) for s in build_history(_E(), 1824502, "1882604", mine, series=two).snapshots]
    assert got == [("2024-11-18", 39359763, 2), ("2024-11-19", 36372347, 2), ("2024-12-31", 36372347, 2)], got
    # the record's three numbers, from the one-class reading (with the later letter rule, if present, switched off:
    # this test is about the cover, not the walk)
    import fle.ledger as L
    import fle.history as H
    saved = getattr(L, "names_another_letter", None)
    if saved is not None:
        L.names_another_letter = lambda *a, **k: False
        H.names_another_letter = L.names_another_letter
    try:
        one = Series(points=[Point("2024-09-30", 425272673.0)], classes={"0000": {"c-4": 389161681.0}})
        assert [round(s.shares) for s in build_history(_E(), 1824502, "1882604", mine, series=one).snapshots] == [34357457, 2154416, 0], "the record's three numbers, from the one-class reading"
    finally:
        if saved is not None:
            L.names_another_letter = saved
            H.names_another_letter = saved


def test_the_panels_ledger_reads_each_filing_under_the_classes_of_its_date():
    """The same three Archer filings through build_ledger (the panel's path),
    newest first, with today's cover saying one class: 0 before, 36,372,347
    with classes_at giving 2024 its two classes."""
    from fle.ledger import build_ledger
    from fle.series import Series
    docs, mine, _E = _archer_docs()
    subs = {"_filings": [dict(f, form="4") for f in mine]}

    class _C(_E):
        def submissions(self, cik):
            return subs if int(cik) == 1824502 else {"_filings": [dict(f) for f in mine]}

    led = build_ledger(_C(), 1824502, owner_cik="1882604", share_classes=1, class_members={"c-5": 770023800.0})
    assert round(led.total) == 0, "today's one class applied to 2024: the record's zero"
    ser = Series(classes={"2024": {"c-4": 389161681.0, "c-5": 36110992.0}, "2025": {"c-5": 542470264.0}})
    led = build_ledger(_C(), 1824502, owner_cik="1882604", share_classes=1, class_members={"c-5": 770023800.0}, classes_at=ser.classes_at)
    assert round(led.total) == 36372347, "each filing under the classes of its date"
