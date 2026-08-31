"""The market-cap universe: written rules, tested one at a time."""
import json

from fle.market_universe import (Row, Snapshot, classify, decide,
                                 eligibility, load_prior, newest_shares,
                                 write_snapshot)


def _subs(forms, sic=None):
    return {"_filings": [{"form": f} for f in forms], "sic": sic}


def test_foreign_filers_and_funds_are_out_by_construction():
    assert "no 10-K" in eligibility(_subs(["20-F", "6-K"]))
    assert "no 10-K" in eligibility(_subs(["N-CSR"]))


def test_a_10k_filer_with_no_section_16_is_out():
    assert "Section 16" in eligibility(_subs(["10-K", "10-Q", "8-K"]))


def test_blank_check_companies_are_out_by_sic():
    assert "blank-check" in eligibility(_subs(["10-K", "4"], sic="6770"))


def test_an_operating_company_is_eligible():
    assert eligibility(_subs(["10-K", "10-Q", "3", "4", "DEF 14A"])) == ""


def test_two_measures_agree_disagree_or_missing():
    r = Row(1, "A", "A Co", mcap_vendor=1.0e9, mcap_sec=1.1e9)
    classify(r); assert r.status == "sized"
    r = Row(1, "A", "A Co", mcap_vendor=1.0e9, mcap_sec=2.0e9)
    classify(r); assert r.status == "disagree"
    r = Row(1, "A", "A Co")
    classify(r); assert r.status == "unsized"
    # one measure alone is sized, not disagree -- there is nothing to disagree with
    r = Row(1, "A", "A Co", mcap_vendor=None, mcap_sec=1.5e9)
    classify(r); assert r.status == "sized"


def test_entry_needs_the_bar_and_exit_needs_two_strikes():
    # newcomer at $1.2B: in; newcomer at $900M: out
    r = Row(1, "A", "A", mcap_vendor=1.2e9); classify(r)
    decide(r, 1e9, 8e8, {}, "2026-09-01"); assert r.decision == "in" and r.added == "2026-09-01"
    r = Row(2, "B", "B", mcap_vendor=9e8); classify(r)
    decide(r, 1e9, 8e8, {}, "2026-09-01"); assert r.decision == "out"
    # a member at $900M stays (above exit bar) and keeps its original date
    r = Row(3, "C", "C", mcap_vendor=9e8); classify(r)
    decide(r, 1e9, 8e8, {3: ("2026-06-01", 0)}, "2026-09-01")
    assert r.decision == "in" and r.added == "2026-06-01"
    # a member at $700M: strike one, still kept
    r = Row(4, "D", "D", mcap_vendor=7e8); classify(r)
    decide(r, 1e9, 8e8, {4: ("2026-06-01", 0)}, "2026-09-01")
    assert r.decision == "kept" and r.strikes == 1
    # strike two: out
    r = Row(4, "D", "D", mcap_vendor=7e8); classify(r)
    decide(r, 1e9, 8e8, {4: ("2026-06-01", 1)}, "2026-12-01")
    assert r.decision == "out" and r.strikes == 2
    # recovery resets the count
    r = Row(4, "D", "D", mcap_vendor=1.5e9); classify(r)
    decide(r, 1e9, 8e8, {4: ("2026-06-01", 1)}, "2026-12-01")
    assert r.decision == "in" and r.strikes == 0


def test_a_counting_failure_never_evicts_and_never_admits():
    r = Row(5, "E", "E"); classify(r)
    decide(r, 1e9, 8e8, {5: ("2026-06-01", 0)}, "2026-09-01")
    assert r.decision == "kept" and "counting failure" in r.note
    r = Row(6, "F", "F"); classify(r)
    decide(r, 1e9, 8e8, {}, "2026-09-01")
    assert r.decision == "out"


class _Feed:
    def __init__(self, payload): self.p = payload
    def get(self, url, use_cache=True): return json.dumps(self.p)


def test_newest_shares_uses_one_filing_and_sums_classes():
    feed = _Feed({"units": {"shares": [
        {"val": 419.5e6, "end": "2026-07-15", "accn": "Q", "filed": "2026-08-05"},
        {"val": 170.1e6, "end": "2026-07-15", "accn": "Q", "filed": "2026-08-05"},
        {"val": 9.2e6, "end": "2026-07-15", "accn": "Q", "filed": "2026-08-05"},
        {"val": 598e6, "end": "2026-04-15", "accn": "Q1", "filed": "2026-05-05"},
        {"val": 598e6, "end": "2026-04-15", "accn": "Q1A", "filed": "2026-05-20"},
    ]}})
    assert newest_shares(feed, 1) == 598.8e6


def test_the_members_file_has_the_pipelines_columns(tmp_path):
    snap = Snapshot(date="2026-09-01")
    a = Row(10, "AAA", "Alpha", mcap_vendor=2e9); classify(a); decide(a, 1e9, 8e8, {}, "2026-09-01")
    b = Row(11, "BBB", "Beta", mcap_vendor=1e9, mcap_sec=3e9); classify(b); decide(b, 1e9, 8e8, {}, "2026-09-01")
    c = Row(12, "CCC", "Gamma", mcap_vendor=5e8); classify(c); decide(c, 1e9, 8e8, {}, "2026-09-01")
    snap.rows = [a, b, c]
    m, e, r = (str(tmp_path / f) for f in ("u.csv", "e.csv", "r.csv"))
    n_members, n_review = write_snapshot(snap, m, e, r)
    assert n_members == 2 and n_review == 1          # b is in but flagged
    head = open(m, encoding="utf-8-sig").readline().strip()
    assert head == "cik,ticker,company,added"
    prior = load_prior(e)
    assert set(prior) == {10, 11} and prior[10] == ("2026-09-01", 0)
