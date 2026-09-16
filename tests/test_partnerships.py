"""THE PARTNERSHIP REGISTER (fle/partnerships.py, 2026-09-15): a company
whose founder's ownership is partnership units the site does not count is
excluded before the panel walks, and its page says why; one whose paired
class is on the cover is kept with a note. Nothing else changes."""
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "ops"))
from fle.partnerships import read_register, read_hand, excluded, kept, note_for, path_for  # noqa: E402
from fle.universe import read_universe  # noqa: E402
import build_company_pages as bcp  # noqa: E402

REG = ("ticker,action,structure,company,ceo,cik,cover_classes,paired_class,units_reported,reason,source,as_of\n"
       "BX,exclude,up-c,Blackstone Inc.,Stephen A. Schwarzman,1393818,Common stock only,,Holdings units in Table II,"
       "The founder's ownership is Holdings units the site does not count.,https://www.sec.gov/x,2026-09-15\n"
       "CVNA,keep,up-c,CARVANA CO.,Ernest C. Garcia,1690820,Class A and Class B,Class B Common Stock,27666483 = Class B,"
       "Paired class on the cover and in Table I.,https://www.sec.gov/y,2026-09-15\n"
       "ZZZ,maybe,up-c,,,,,,,not a decision,,\n")


def test_the_register_reads_decisions_only(tmp_path):
    p = tmp_path / "partnerships.csv"; p.write_text(REG)
    r = read_register(str(p))
    assert set(r) == {"BX", "CVNA"}, "a row without a decision is not a row"
    assert set(excluded(str(p))) == {"BX"} and set(kept(str(p))) == {"CVNA"}
    assert "does not count" in note_for(r["BX"]) and "Schwarzman" in note_for(r["BX"])
    assert "Class B Common Stock" in note_for(r["CVNA"]) and "one for one" in note_for(r["CVNA"])
    assert read_register(str(tmp_path / "missing.csv")) == {}


def test_an_excluded_company_leaves_the_universe_before_the_panel_walks(tmp_path):
    (tmp_path / "universe").mkdir()
    u = tmp_path / "universe" / "universe-2026-08-31.csv"
    u.write_text("cik,ticker,company,added\n1393818,BX,Blackstone Inc.,\n1690820,CVNA,Carvana Co.,\n1318605,TSLA,Tesla,\n")
    assert [m.ticker for m in read_universe(str(u))] == ["BX", "CVNA", "TSLA"], "no register: everyone"
    (tmp_path / "universe" / "partnerships.csv").write_text(REG)
    assert path_for(str(u)).endswith(os.path.join("universe", "partnerships.csv"))
    assert [m.ticker for m in read_universe(str(u))] == ["CVNA", "TSLA"], "BX is gone; CVNA (keep) and TSLA stay"
    assert [m.ticker for m in read_universe(str(u), register=False)] == ["BX", "CVNA", "TSLA"], "and can be read whole on request"


def test_the_excluded_company_has_no_page_and_the_kept_page_carries_a_note(tmp_path):
    panel = tmp_path / "panel.csv"
    with open(panel, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "cik", "company", "ceo", "pct", "shares", "outstanding", "shares_as_of", "confidence", "form4_url"])
        w.writerow(["CVNA", "1690820", "CARVANA CO.", "Ernest C. Garcia", "13.36", "147049214", "1100463770", "2026-09-01", "high", "https://sec.gov/x"])
    (tmp_path / "universe").mkdir()
    sp = tmp_path / "universe" / "sp500-2026-09-10.csv"; sp.write_text("cik,ticker,company,added\n1690820,CVNA,Carvana,\n")
    (tmp_path / "universe" / "partnerships.csv").write_text(REG)
    prices = tmp_path / "prices.csv"; prices.write_text("ticker,close,as_of\nCVNA,67.80,2026-09-15\n")
    founders = tmp_path / "founders.csv"; founders.write_text('ticker,founder,evidence,source\nCVNA,yes,"co-founded",DEF 14A\n')
    out = tmp_path / "public"
    bcp.main(str(panel), str(founders), str(prices), str(sp), str(out))
    assert not (out / "company" / "BX").exists(), "an excluded company has no page: the real 404"
    cv = open(out / "company" / "CVNA" / "index.html", encoding="utf-8").read()
    assert 'class="sub structure-note"' in cv and "Class B Common Stock" in cv and "one for one" in cv
    sm = open(out / "sitemap.xml", encoding="utf-8").read()
    assert "/company/BX/" not in sm and "/company/CVNA/" in sm, "the kept page is in the sitemap; the excluded one is not"
    idx = open(out / "companies" / "index.html", encoding="utf-8").read()
    assert "/company/BX/" not in idx, "an excluded company is not in the screener"


def test_the_seeded_register_is_well_formed():
    """The hand file alone: on the mini PC the generated file sits beside it
    and read_register merges the two, which is right for the pipeline and
    wrong for this check."""
    p = os.path.join(ROOT, "universe", "partnerships.csv")
    r = read_hand(p)
    assert set(r) >= {"CVNA", "BX", "MLTX", "PEB"}
    for tk, row in r.items():
        assert row["source"].startswith("https://www.sec.gov/") and row["as_of"] and row["reason"], tk
        assert row["structure"] in ("up-c", "upreit"), tk
    assert r["CVNA"]["action"] == "keep" and r["BX"]["action"] == "exclude"


def test_the_generated_register_sits_under_the_hand_rows(tmp_path):
    (tmp_path / "universe").mkdir()
    hand = tmp_path / "universe" / "partnerships.csv"; hand.write_text(REG)
    auto = tmp_path / "universe" / "partnerships-auto.csv"
    auto.write_text("ticker,action,structure,company,ceo,cik,cover_classes,paired_class,units_reported,reason,source,as_of,by\n"
                    "OWL,keep,partnership,Blue Owl,Doug Ostrover,1823945,3,Class C Shares,units,Units equal the paired class.,https://www.sec.gov/o,2026-09-20,census\n"
                    "CVNA,exclude,partnership,Carvana,Ernest C. Garcia,1690820,2,Class B,units,The facts conflict. REVIEW.,https://www.sec.gov/c,2026-09-20,census\n"
                    "PJT,exclude,partnership,PJT,Paul Taubman,1626115,2,,Partnership Units 5352000,no paired class,https://www.sec.gov/p,2026-09-20,census\n")
    r = read_register(str(hand))
    assert r["CVNA"]["action"] == "keep" and r["CVNA"]["by"] == "hand", "the hand row wins over the census's REVIEW exclusion"
    assert r["OWL"]["action"] == "keep" and r["OWL"]["by"] == "census"
    assert r["PJT"]["action"] == "exclude" and r["BX"]["action"] == "exclude"
    assert set(excluded(str(hand))) == {"BX", "PJT"} and set(kept(str(hand))) == {"CVNA", "OWL"}
    u = tmp_path / "universe" / "universe-2026-08-31.csv"
    u.write_text("cik,ticker,company,added\n1393818,BX,Blackstone,\n1690820,CVNA,Carvana,\n1823945,OWL,Blue Owl,\n1626115,PJT,PJT,\n1318605,TSLA,Tesla,\n")
    assert [m.ticker for m in read_universe(str(u))] == ["CVNA", "OWL", "TSLA"], "both files exclude; the hand keep survives"


def test_the_stage_delta_names_every_change():
    import partnerships_stage as st
    old = {"OWL": {"action": "keep", "reason": "x"}, "PJT": {"action": "exclude", "reason": "y"}, "GONE": {"action": "exclude", "reason": "z"}}
    new = {"OWL": {"action": "exclude", "reason": "lost the paired class"}, "PJT": {"action": "exclude", "reason": "y"},
           "NEWC": {"action": "exclude", "reason": "new units"}, "RSI": {"action": "exclude", "reason": "The facts conflict. REVIEW."}}
    hand = {"OWL": {"action": "keep", "reason": "read the filing"}}
    lines = st.delta(old, new, hand)
    joined = "\n".join(lines)
    assert "GONE: removed" in joined and "returns to the site" in joined
    assert "NEWC: added, exclude" in joined
    assert "OWL: keep -> exclude" in joined and "OWL: the hand row says keep, the census says exclude" in joined and "the hand row stands" in joined
    assert "RSI: added, exclude" in joined and "REVIEW" in joined
    assert "PJT" not in joined, "an unchanged row is not a line"


def test_the_stage_generates_keep_and_exclude_from_the_four_facts():
    import partnerships_stage as st
    import upc_census as U
    doc_keep = ('<ownershipDocument><periodOfReport>2026-06-01</periodOfReport><issuer><issuerCik>0001</issuerCik></issuer>'
                '<nonDerivativeHolding><securityTitle><value>Class B Common Stock</value></securityTitle><postTransactionAmounts><sharesOwnedFollowingTransaction><value>1000</value></sharesOwnedFollowingTransaction></postTransactionAmounts><ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature></nonDerivativeHolding>'
                '<derivativeHolding><securityTitle><value>LLC Units</value></securityTitle><underlyingSecurity><underlyingSecurityTitle><value>Class A Common Stock</value></underlyingSecurityTitle></underlyingSecurity><postTransactionAmounts><sharesOwnedFollowingTransaction><value>1000</value></sharesOwnedFollowingTransaction></postTransactionAmounts></derivativeHolding></ownershipDocument>')
    doc_excl = doc_keep.replace('<value>1000</value></sharesOwnedFollowingTransaction></postTransactionAmounts><ownershipNature>', '<value>0</value></sharesOwnedFollowingTransaction></postTransactionAmounts><ownershipNature>', 1)

    class C:
        def __init__(self, d): self.d = d
        def submissions(self, cik): return {"_filings": [{"form": "4", "accessionNumber": "0000000001-26-000001", "filingDate": "2026-06-03", "reportDate": "2026-06-01", "primaryDocument": "d.xml"}]}
        def filing_index(self, cik, acc): return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}
        def get(self, url, use_cache=True): return self.d
    panel = [{"ticker": "KEEP", "cik": "1", "owner_cik": "2", "company": "Keep Co", "ceo": "K"}]
    out = st.generate(C(doc_keep), panel, {"KEEP": "us-gaap:CommonClassAMember|us-gaap:CommonClassBMember"})
    assert out["KEEP"]["action"] == "keep" and "Units equal the paired class" in out["KEEP"]["reason"] and out["KEEP"]["by"] == "census"
    assert out["KEEP"]["source"].startswith("https://www.sec.gov/Archives/edgar/data/1/000000000126000001/")
    panel = [{"ticker": "EXCL", "cik": "1", "owner_cik": "2", "company": "Excl Co", "ceo": "E"}]
    out = st.generate(C(doc_excl), panel, {"EXCL": "c-2"})
    assert out["EXCL"]["action"] == "exclude" and "does not count" in out["EXCL"]["reason"]
    assert st.generate(C("<ownershipDocument><issuer><issuerCik>1</issuerCik></issuer></ownershipDocument>"), panel, {}) == {}, "no unit rows: not in the register"


def test_a_titles_rows_are_summed_within_the_filing_and_a_keep_needs_one_filing():
    """MEDLINE, RUSH STREET, SOLARIS (2026-09-16): a founder's units sit in
    several vehicles, one row each under one title; the first version read
    the first row and called exact matches conflicts. And RED ROCK: units
    last stated in 2016, the paired class restated since; counts from
    different dates prove nothing, so the census says read, not keep."""
    import upc_census as U
    head = '<ownershipDocument><periodOfReport>{p}</periodOfReport><issuer><issuerCik>0001</issuerCik></issuer>'
    paired = lambda amt, di, nat: (f'<nonDerivativeHolding><securityTitle><value>Class B Common Stock</value></securityTitle><postTransactionAmounts><sharesOwnedFollowingTransaction><value>{amt}</value></sharesOwnedFollowingTransaction></postTransactionAmounts>'  # noqa: E731
                                   f'<ownershipNature><directOrIndirectOwnership><value>{di}</value></directOrIndirectOwnership><natureOfOwnership><value>{nat}</value></natureOfOwnership></ownershipNature></nonDerivativeHolding>')
    unit = lambda amt, di: (f'<derivativeHolding><securityTitle><value>LLC Units</value></securityTitle><underlyingSecurity><underlyingSecurityTitle><value>Class A Common Stock</value></underlyingSecurityTitle></underlyingSecurity>'  # noqa: E731
                            f'<postTransactionAmounts><sharesOwnedFollowingTransaction><value>{amt}</value></sharesOwnedFollowingTransaction></postTransactionAmounts><ownershipNature><directOrIndirectOwnership><value>{di}</value></directOrIndirectOwnership></ownershipNature></derivativeHolding>')

    class C:
        def __init__(self, docs, bodies): self.docs, self.bodies = docs, bodies
        def submissions(self, cik): return {"_filings": [{"form": "4", "accessionNumber": k, "filingDate": d, "reportDate": d, "primaryDocument": "d.xml"} for k, d in self.docs]}
        def filing_index(self, cik, acc): return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}
        def get(self, url, use_cache=True): return next(b for (k, d), b in zip(self.docs, self.bodies) if k in url)
    same = head.format(p="2026-03-01") + paired(726819, "D", "") + paired(3513496, "I", "By Solaris Energy Capital") + unit(726819, "D") + unit(3513496, "I") + '</ownershipDocument>'
    r = U.facts(C([("s1", "2026-03-01")], [same]), {"ticker": "SEI", "cik": "1", "owner_cik": "2"}, {"A", "B"})
    assert r["suggest"] == "keep" and r["units"]["LLC Units"][0] == 4240315 and r["paired_total"] == 4240315, "two rows, one title, summed"
    # RED ROCK: the 2016 filing states units and paired shares together; a 2026 filing restates only the
    # paired class. The match is proved on the 2016 date, the pairing is structural, and the ledger's
    # current Class B is the 2026 statement as usual: keep.
    old = head.format(p="2016-05-18") + paired(22613985, "I", "Fertitta") + unit(22613985, "I") + '</ownershipDocument>'
    new = head.format(p="2026-06-01") + paired(45385804, "I", "Fertitta") + '</ownershipDocument>'
    r = U.facts(C([("n1", "2026-06-01"), ("o1", "2016-05-18")], [new, old]), {"ticker": "RRR", "cik": "1", "owner_cik": "2"}, {"A", "B"})
    assert r["suggest"] == "keep" and r["paired_total"] == 22613985, "the paired rows of the units' own filing are compared"
    # a units-only filing (no paired rows in it) with the paired class stated elsewhere: counts agree, but not on one date
    units_only = head.format(p="2026-03-01") + unit(22613985, "I") + '</ownershipDocument>'
    r = U.facts(C([("u1", "2026-03-01"), ("n1", "2026-02-01")], [units_only, new.replace("45385804", "22613985")]), {"ticker": "RRR", "cik": "1", "owner_cik": "2"}, {"A", "B"})
    assert r["suggest"] == "read", "counts that agree across different filings do not prove the pairing"
    # SYMBOTIC: a gift's before-and-after rows for one vehicle are one balance (the second row's balance is the
    # first's minus its shares); MEDLINE: two lines told apart only by a footnote add (the balances are independent)
    dtx = lambda title, shares, after, di, code: (f'<derivativeTransaction><securityTitle><value>{title}</value></securityTitle><transactionCoding><transactionCode>{code}</transactionCode></transactionCoding>'  # noqa: E731
                                                  f'<transactionAmounts><transactionShares><value>{shares}</value></transactionShares></transactionAmounts><underlyingSecurity><underlyingSecurityTitle><value>Class A Common Stock</value></underlyingSecurityTitle></underlyingSecurity>'
                                                  f'<postTransactionAmounts><sharesOwnedFollowingTransaction><value>{after}</value></sharesOwnedFollowingTransaction></postTransactionAmounts><ownershipNature><directOrIndirectOwnership><value>{di}</value></directOrIndirectOwnership></ownershipNature></derivativeTransaction>')
    gift = head.format(p="2025-12-11") + paired(2215990, "I", "By RJJRP") + dtx("LLC Units", 1000000, 166940810, "I", "J") + dtx("LLC Units", 1000000, 165940810, "I", "G") + unit(43765590, "I") + '</ownershipDocument>'
    r = U.facts(C([("g1", "2025-12-11")], [gift]), {"ticker": "SYM", "cik": "1", "owner_cik": "2"}, {"A", "B"})
    assert r["units"]["LLC Units"][0] == 165940810 + 43765590, "one vehicle's successive balances replace; a separate holding line adds"
    med = head.format(p="2025-12-16") + paired(24313, "D", "") + paired(514876, "I", "See Footnote") + dtx("LLC Units", 24313, 24313, "I", "A") + dtx("LLC Units", 514876, 514876, "I", "A") + '</ownershipDocument>'
    r = U.facts(C([("m1", "2025-12-16")], [med]), {"ticker": "MDLN", "cik": "1", "owner_cik": "2"}, {"A", "B"})
    assert r["suggest"] == "keep" and r["units"]["LLC Units"][0] == 539189, "two lines with the same D/I and an empty nature, distinguished by their balances"


def test_the_stage_excludes_a_keep_that_stands_on_a_partial_filing():
    import partnerships_stage as st
    import upc_census as U
    doc = ('<ownershipDocument><periodOfReport>2026-06-01</periodOfReport><issuer><issuerCik>0001</issuerCik></issuer>'
           '<nonDerivativeHolding><securityTitle><value>Class B Common Stock</value></securityTitle><postTransactionAmounts><sharesOwnedFollowingTransaction><value>1000</value></sharesOwnedFollowingTransaction></postTransactionAmounts><ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature></nonDerivativeHolding>'
           '<derivativeHolding><securityTitle><value>LLC Units</value></securityTitle><underlyingSecurity><underlyingSecurityTitle><value>Class A Common Stock</value></underlyingSecurityTitle></underlyingSecurity><postTransactionAmounts><sharesOwnedFollowingTransaction><value>1000</value></sharesOwnedFollowingTransaction></postTransactionAmounts></derivativeHolding></ownershipDocument>')

    class C:
        def submissions(self, cik): return {"_filings": [{"form": "4", "accessionNumber": "0000000001-26-000001", "filingDate": "2026-06-03", "reportDate": "2026-06-01", "primaryDocument": "d.xml"}]}
        def filing_index(self, cik, acc): return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}
        def get(self, url, use_cache=True): return doc
    clean = [{"ticker": "OK", "cik": "1", "owner_cik": "2", "company": "Ok", "ceo": "K", "cautions": ""}]
    partial = [{"ticker": "PART", "cik": "1", "owner_cik": "2", "company": "Part", "ceo": "P", "cautions": "the newest filing names fewer lines than the one before it"}]
    covers = {"OK": "us-gaap:CommonClassAMember|us-gaap:CommonClassBMember", "PART": "us-gaap:CommonClassAMember|us-gaap:CommonClassBMember"}
    assert st.generate(C(), clean, covers)["OK"]["action"] == "keep"
    p = st.generate(C(), partial, covers)["PART"]
    assert p["action"] == "exclude" and "fewer lines" in p["reason"] and "REVIEW" in p["reason"]


def test_the_stage_reads_the_universe_not_the_panel(tmp_path, monkeypatch):
    """The first version read the panel, which no longer held the companies
    the register had excluded, called their absence a collapse, and put
    them back on the site the next morning."""
    import partnerships_stage as st
    (tmp_path / "universe").mkdir()
    (tmp_path / "universe" / "universe-2026-08-31.csv").write_text("cik,ticker,company,ceo,owner_cik,added\n1393818,BX,Blackstone,Stephen Schwarzman,1227945,\n1318605,TSLA,Tesla,Elon Musk,1494730,\n")
    (tmp_path / "panel.csv").write_text("ticker,cik,company,ceo,owner_cik,cautions\nTSLA,1318605,Tesla,Elon Musk,1494730,the newest filing names fewer lines than the one before it\n")
    monkeypatch.setattr(st, "ROOT", str(tmp_path))
    m = st.members(str(tmp_path))
    assert [r["ticker"] for r in m] == ["BX", "TSLA"], "the excluded company is still a member to be judged"
    assert m[0]["owner_cik"] == "1227945" and m[1]["cautions"].startswith("the newest filing")
    # the universe file has no owner CIK (the real one: cik,ticker,company,added); the register remembers it
    (tmp_path / "universe" / "universe-2026-08-31.csv").write_text("cik,ticker,company,added\n1393818,BX,Blackstone,\n1318605,TSLA,Tesla,\n")
    (tmp_path / "universe" / "partnerships-auto.csv").write_text("ticker,action,structure,company,ceo,cik,owner_cik,cover_classes,paired_class,units_reported,reason,source,as_of,by\nBX,exclude,partnership,Blackstone,Stephen Schwarzman,1393818,1227945,1,,units,no paired,https://www.sec.gov/x,2026-09-13,census\n")
    m = st.members(str(tmp_path))
    assert m[0]["owner_cik"] == "1227945", "off the panel, the owner CIK comes from last week's row"
    # a company nobody can judge keeps its row: removal needs positive evidence
    (tmp_path / "universe" / "partnerships-auto.csv").write_text("ticker,action,structure,company,ceo,cik,owner_cik,cover_classes,paired_class,units_reported,reason,source,as_of,by\nBX,exclude,partnership,Blackstone,Stephen Schwarzman,1393818,,1,,units,no paired,https://www.sec.gov/x,2026-09-13,census\n")
    m = st.members(str(tmp_path)); assert m[0]["owner_cik"] == ""
    unjudged = set()
    class _C:
        def submissions(self, cik): raise AssertionError("must not be called without an owner CIK")
    out = st.generate(_C(), m, {}, None, unjudged)
    assert "BX" in unjudged and "BX" not in out
