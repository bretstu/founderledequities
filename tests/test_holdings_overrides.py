"""One curated file, two directions. universe/exclusions.csv removes what a
filing attributes to the CEO but the company says is not theirs (TKO), and
SUPPLEMENTS what a filer states in a remark is held of record but left out
of the tables (SpaceX). A supplement is one more table line, injected at
the parse step into every filing by that owner that still states the
figure, so every stage downstream inherits it. No regex or model reads the
sentence; a person recorded the figure, and the walk matches the digits."""
import os

from fle.exclusions import Exclusion, figure_stated, read_exclusions
from fle.ledger import build_ledger, supplement_rows, _rows
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OWNER = ('<reportingOwner><reportingOwnerId><rptOwnerCik>0001494730</rptOwnerCik>'
         '<rptOwnerName>Musk Elon</rptOwnerName></reportingOwnerId>'
         '<reportingOwnerRelationship><isOfficer>1</isOfficer>'
         '<officerTitle>CEO</officerTitle></reportingOwnerRelationship></reportingOwner>')
ISS = '<issuer><issuerCik>0001181412</issuerCik></issuer>'


def _hold(title, bal, direct="I", nature="By Elon Musk Revocable Trust"):
    nat = f'<natureOfOwnership><value>{nature}</value></natureOfOwnership>' if direct == "I" else ""
    return (f'<nonDerivativeHolding><securityTitle><value>{title}</value></securityTitle>'
            f'<postTransactionAmounts><sharesOwnedFollowingTransaction><value>{bal}</value>'
            f'</sharesOwnedFollowingTransaction></postTransactionAmounts><ownershipNature>'
            f'<directOrIndirectOwnership><value>{direct}</value></directOrIndirectOwnership>{nat}'
            f'</ownershipNature></nonDerivativeHolding>')


def _doc(body, remark=""):
    rem = f'<remarks>{remark}</remarks>' if remark else ""
    return f'<ownershipDocument>{ISS}{OWNER}{body}{rem}</ownershipDocument>'


def _entry(**kw):
    base = dict(cik="1181412", ticker="SPCX", security="Class B Common Stock (restricted; disclosed in a remark)",
                direct="D", reason="This Form 4 does not include 1,302,072,285 shares ...",
                source="https://www.sec.gov/Archives/edgar/data/1181412/000162828026044069/wk-form4_1781740812.xml",
                shares=1302072285.0, owner_cik="1494730", since="2026-06-11")
    base.update(kw)
    return Exclusion(**base)


REMARK = "This Form 4 does not include 1,302,072,285 shares of unvested performance-based restricted Class B Common Stock."


def _supp(doc_xml, entries):
    root = ET.fromstring(doc_xml)
    rows = _rows(root, "4", "2026-06-15", "acc")
    return supplement_rows(root, rows, "4", "2026-06-15", "acc", entries)


def test_a_filing_that_states_the_figure_gets_the_line():
    extra = _supp(_doc(_hold("Class B Common Stock", 3916980790), REMARK), [_entry()])
    assert len(extra) == 1
    ln = extra[0]
    assert ln.security == "Class B Common Stock" and ln.direct == "D" and ln.shares == 1302072285 and ln.table == "I"
    assert "recorded from https://www.sec.gov" in ln.notes


def test_the_figure_must_still_be_stated_commas_or_not():
    assert figure_stated("does not include 1,302,072,285 shares", 1302072285)
    assert figure_stated("does not include 1302072285 shares", 1302072285)
    assert figure_stated("does not include 1 302 072 285 shares", 1302072285)
    assert not figure_stated("does not include 1,235,372,285 shares", 1302072285), "a vested tranche changes the figure"
    assert not figure_stated("does not include 1,302,072,258 shares", 1302072285), "a typo is a changed figure"
    assert not figure_stated("11,302,072,285", 1302072285), "not a substring of a longer number"
    assert _supp(_doc(_hold("Class B Common Stock", 1), "does not include 1,235,372,285 shares"), [_entry()]) == []
    assert _supp(_doc(_hold("Class B Common Stock", 1)), [_entry()]) == [], "no remark, no line"


def test_the_tables_win_when_the_class_appears_held_directly():
    """A vesting Form 4 lists Class B directly: the filer's own line stands
    alone, whatever the remark says. Phrasing does not matter: the class is
    read the way the walk reads every title."""
    for title in ("Class B Common Stock", "Class B", "Restricted Class B Common Stock, par value $0.001"):
        doc = _doc(_hold("Class B Common Stock", 3916980790) + _hold(title, 66_700_000, direct="D"), REMARK)
        assert _supp(doc, [_entry()]) == [], title


def test_a_successor_does_not_inherit():
    other = _doc(_hold("Class B Common Stock", 1), REMARK).replace("0001494730", "0000000999")
    assert _supp(other, [_entry()]) == []


def test_end_to_end_the_panel_and_the_history_agree():
    """Form 3 and Form 4 both state the figure; the Form 4 is newest and
    reports Class B through the trusts only. The ledger's total carries the
    supplement, the record says so, and the tables' own figure rides beside it."""
    form3 = _doc(_hold("Class A Common Stock", 526_165_420) + _hold("Class B Common Stock", 3_916_980_790), REMARK)
    form4 = _doc(_hold("Class A Common Stock", 849_494_440) + _hold("Class B Common Stock", 3_916_980_790), REMARK)
    docs = {"f3": form3, "f4": form4}
    feed = [{"form": "3", "accessionNumber": "f3", "filingDate": "2026-06-11", "reportDate": "2026-06-11", "primaryDocument": "d.xml"},
            {"form": "4", "accessionNumber": "f4", "filingDate": "2026-06-17", "reportDate": "2026-06-15", "primaryDocument": "d.xml"}]

    class _Edgar:
        def submissions(self, cik): return {"_filings": feed}
        def filing_index(self, cik, acc): return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}
        def get(self, url, use_cache=True, **kw):
            for k in docs:
                if k in url: return docs[k]
            raise KeyError(url)

    led = build_ledger(_Edgar(), 1181412, owner_cik="1494730", share_classes=2, exclude=[_entry()])
    assert led.total == 849_494_440 + 3_916_980_790 + 1_302_072_285, "the supplement is one more line in the newest filing"
    assert "Class B Common Stock" in led.supplemented and led.supplemented["Class B Common Stock"][0] == 1_302_072_285
    plain = build_ledger(_Edgar(), 1181412, owner_cik="1494730", share_classes=2)
    assert plain.total == 849_494_440 + 3_916_980_790, "without the entry, the tables alone"


def test_the_loader_separates_the_two_directions_and_demands_a_receipt(tmp_path):
    p = tmp_path / "exclusions.csv"
    p.write_text("cik,ticker,security,direct,reason,source,shares,owner_cik,since\n"
                 "1,TKO,Class B Common Stock,I,attributed not owned,https://sec.gov/x,,,\n"
                 "2,SPCX,Class B Common Stock,D,the remark says so,https://sec.gov/y,1302072285,1494730,2026-06-11\n",
                 encoding="utf-8")
    ex = read_exclusions(str(p))
    assert [e.ticker for e in ex.for_issuer(1)] == ["TKO"]
    assert [e.is_addition for e in ex.for_issuer(2)] == [True], "the walk sees the supplement among the issuer's entries"
    assert [e.shares for e in ex.additions_for("SPCX")] == [1302072285.0]
    for bad, why in (("2,SPCX,Class B Common Stock,D,,https://sec.gov/y,1302072285,1494730,\n", "without quoting"),
                     ("2,SPCX,Class B Common Stock,D,the remark,https://sec.gov/y,1302072285,,\n", "owner")):
        p.write_text("cik,ticker,security,direct,reason,source,shares,owner_cik,since\n" + bad, encoding="utf-8")
        try:
            read_exclusions(str(p)); assert False, why
        except ValueError as e:
            assert why in str(e)


def test_the_repo_entry_for_spacex_is_exactly_the_remark():
    ex = read_exclusions(os.path.join(ROOT, "universe", "exclusions.csv"))
    adds = ex.additions_for("SPCX")
    assert len(adds) == 1 and adds[0].shares == 1302072285 and adds[0].owner_cik == "1494730"
    assert "does not include 1,302,072,285" in adds[0].reason
    assert "000162828026044069" in adds[0].source
    assert [e.ticker for e in ex.for_issuer(1973266) if not e.is_addition] == ["TKO"], "the TKO exclusion is untouched"


def test_an_edited_entry_makes_the_carried_row_stale():
    from fle.panel import _addition_current, _reusable
    ex = read_exclusions(os.path.join(ROOT, "universe", "exclusions.csv"))
    a = ex.additions_for("SPCX")[0]
    key = f"SPCX:{int(a.shares)}:{a.source}"
    assert _addition_current({"ticker": "SPCX", "addition_key": key}, ex), "same entry: carry"
    assert not _addition_current({"ticker": "SPCX", "addition_key": "SPCX:1:x"}, ex), "changed entry: walk again"
    assert not _addition_current({"ticker": "SPCX"}, ex), "entry added since: walk again"
    assert _addition_current({"ticker": "TSLA"}, ex), "no entry, none before: carry"
    old = {"fingerprint": "abc", "error": "", "settled": "1"}
    assert not _reusable(old), "a row from before the fields existed walks again once"
    assert _reusable(dict(old, remarks="", addition_key="", opening_source="", lines_stated=""))


def test_stake_source_reaches_the_csv():
    from fle.panel import COLUMNS
    assert "stake_source" in COLUMNS and "shares_tabled" in COLUMNS and "remarks" in COLUMNS
