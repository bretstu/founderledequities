"""The market-cap universe: written rules, tested one at a time."""
import json

from fle.market_universe import (Row, Snapshot, classify, decide,
                                 eligibility, load_prior, newest_shares,
                                 write_snapshot)


def _subs(forms, sic=None, insiders=1):
    return {"_filings": [{"form": f, "accessionNumber": "0001193125-26-000001"}
                         for f in forms],
            "sic": sic, "insiderTransactionForIssuerExists": insiders}


def test_foreign_filers_and_funds_are_out_by_construction():
    assert "no domestic" in eligibility(_subs(["20-F", "6-K"]))
    assert "no domestic" in eligibility(_subs(["N-CSR"]))


def test_a_company_too_young_for_a_10k_is_still_domestic():
    """ExxonMobil Holdings (a 2025 holdco with a new CIK) and a fresh
    spin-off have 10-Qs or a Form 10 and no 10-K yet."""
    assert eligibility(_subs(["10-Q", "4", "3"])) == ""
    assert eligibility(_subs(["10-12B", "8-K12B", "3"])) == ""
    assert eligibility(_subs(["S-1", "S-1/A", "3", "4"])) == ""


def test_controlled_companies_without_proxies_are_still_companies():
    """Blackstone and Erie elect directors through a private class and file
    no DEF 14A; FedEx Freight filed a 10-K before its first meeting. A
    missing proxy is not a missing board."""
    assert eligibility(_subs(["10-K", "10-Q", "3", "4"], sic="6282")) == ""
    assert eligibility(_subs(["10-K", "4"], sic="6411")) == ""


def test_investment_companies_are_out_by_the_forms_only_they_file():
    assert "investment company" in eligibility(_subs(["10-K", "4", "DEF 14A", "N-CSR"]))
    assert "investment company" in eligibility(_subs(["10-K", "4", "DEF 14A", "40-17G", "N-2"]))


def test_n_px_is_filed_by_ordinary_corporations_and_excludes_nobody():
    """Amazon, NVIDIA, J&J and Walmart all file N-PX (say-on-pay votes)."""
    assert eligibility(_subs(["10-K", "10-Q", "4", "DEF 14A", "N-PX"], sic="5961")) == ""


def test_a_self_described_fund_with_no_meetings_is_out_whatever_its_sic():
    assert "self-described fund" in eligibility(_subs(["10-K", "10-Q", "3"], sic=""),
                                                "Fidelity Ethereum Fund")
    # a REIT called a Trust with meetings is a company; so is a bank called Trust
    assert eligibility(_subs(["10-K", "4", "DEF 14A"], sic="6798"), "American Assets Trust, Inc.") == ""
    assert eligibility(_subs(["10-K", "4", "DEF 14A"], sic="6022"), "NORTHERN TRUST CORP") == ""


def test_non_operating_entities_are_out_by_sic_unless_they_hold_meetings():
    for sic, why in (("6221", "commodity pool"), ("6792", "royalty trust"),
                     ("6726", "investment company")):
        assert why in eligibility(_subs(["10-K", "4"], sic=sic))
    # Texas Pacific Land: SIC 6792 kept from its trust days, but a board,
    # annual meetings and a chief executive -- rescued by the DEF 14A
    assert eligibility(_subs(["10-K", "10-Q", "4", "DEF 14A"], sic="6792"),
                       "Texas Pacific Land Corp") == ""
    # a royalty trust or an ETP also files proxies -- and says what it is
    assert "royalty trust" in eligibility(_subs(["10-K", "10-Q", "4", "DEF 14A"], sic="6792"),
                                          "PERMIAN BASIN ROYALTY TRUST")
    assert "commodity pool" in eligibility(_subs(["10-K", "4", "DEF 14A"], sic="6221"),
                                           "Grayscale Bitcoin Trust ETF")
    assert "commodity pool" in eligibility(_subs(["10-K", "4", "DEF 14A"], sic="6221"),
                                           "INVESCO DB AGRICULTURE FUND")
    # a SPAC is never rescued: it files proxies for extension votes
    assert "blank-check" in eligibility(_subs(["10-K", "4", "DEF 14A"], sic="6770"))


def test_a_successor_issuer_passes_through_for_the_panel_to_resolve():
    """ExxonMobil Holdings: 10-Qs and an 8-K12B, no insider filings of its
    own -- a successor DECLARED itself one. Imperial Oil also has zero
    insider filings, but no 8-K12B: a Canadian MJDS filer whose insiders
    report at home. Quiet is not the same as succeeded."""
    assert eligibility(_subs(["10-Q", "8-K12B"], sic="2911", insiders=0)) == "successor"
    assert "no Section 16" in eligibility(_subs(["10-K", "10-Q"], sic="2911", insiders=0))
    assert "no Section 16" in eligibility(_subs(["10-K", "10-Q"], sic="2911", insiders=1))


def test_a_10k_filer_with_no_section_16_is_out():
    assert "Section 16" in eligibility(_subs(["10-K", "10-Q", "8-K"]))


def test_blank_check_companies_are_out_by_sic():
    assert "blank-check" in eligibility(_subs(["10-K", "4", "DEF 14A"], sic="6770"))


def test_an_operating_company_is_eligible():
    assert eligibility(_subs(["10-K", "10-Q", "3", "4", "DEF 14A"])) == ""
    # REITs and property trusts are operating companies with real CEOs
    assert eligibility(_subs(["10-K", "4", "DEF 14A"], sic="6798")) == ""


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


def test_the_newest_snapshot_is_found_by_date(tmp_path):
    from fle.market_universe import newest_snapshot
    d = tmp_path / "universe"; d.mkdir()
    assert newest_snapshot(str(d)) is None          # the S&P site: no snapshot
    for day in ("2026-09-01", "2026-12-01", "2026-06-01"):
        (d / f"universe-{day}.csv").write_text("cik,ticker,company,added\n")
        (d / f"universe-{day}-evidence.csv").write_text("cik\n")
    members, evidence, taken = newest_snapshot(str(d))
    assert members.endswith("universe-2026-12-01.csv")
    assert evidence.endswith("universe-2026-12-01-evidence.csv")
    assert taken.isoformat() == "2026-12-01"


def test_the_published_page_lists_every_member_and_the_rules(tmp_path):
    from fle.market_universe import write_page
    about = tmp_path / "about.html"
    about.write_text("<html><head><title>About</title></head><body>"
                     "<main><h1>old</h1></main><footer>f</footer></body></html>")
    ev = tmp_path / "e.csv"
    ev.write_text("cik,ticker,company,mcap_vendor,mcap_sec,status,decision,added\n"
                  "1,AAA,Alpha Inc,2500000000,,sized,in,2026-09-01\n"
                  "2,BBB,Beta Corp,1200000000,3000000000,disagree,in,2026-09-01\n"
                  "3,CCC,Gamma,500000000,,sized,out,\n")
    out = write_page(str(tmp_path / "u.csv"), str(ev), "2026-09-01",
                     str(about), str(tmp_path / "universe.html"))
    page = open(out).read()
    assert "2 US public companies" in page and "2026-09-01" in page
    assert "Alpha Inc" in page and "Beta Corp" in page and "Gamma" not in page
    assert "$2.5B" in page and "flagged" in page
    assert "two consecutive quarterly snapshots" in page      # the rules ship with the list
    assert "<footer>f</footer>" in page                        # the site's own shell


def test_a_snapshot_never_reads_sizing_or_indexes_from_cache():
    """Market caps, share counts and filing indexes are fetched fresh; a
    quarterly snapshot on last quarter's cache would be a dated list with
    the wrong date on it."""
    from fle.market_universe import (newest_shares, recent_submissions,
                                     vendor_mcap)
    seen = []

    class Spy:
        def get(self, url, use_cache=True):
            seen.append(("get", use_cache)); return '{"units":{"shares":[]},"results":{}}'
        def get_json(self, url, use_cache=True):
            seen.append(("json", use_cache))
            return {"filings": {"recent": {"form": ["10-K", "4"],
                                            "accessionNumber": ["a", "b"]}},
                    "sic": "3571"}
    newest_shares(Spy(), 1)
    vendor_mcap(Spy(), "AAA", "k")
    subs = recent_submissions(Spy(), 1)
    assert all(cache is False for _, cache in seen), seen
    assert {f["form"] for f in subs["_filings"]} == {"10-K", "4"}
    assert subs["sic"] == "3571"


def test_a_run_resumes_from_its_checkpoint_on_the_same_day(tmp_path):
    from fle.market_universe import build_snapshot
    from fle.universe import Member
    import fle.market_universe as MU
    calls = []

    class Feed:
        def get(self, url, use_cache=True):
            calls.append(url)
            if "grouped" in url: return '{"results":[{"T":"AAA","c":10},{"T":"BBB","c":10}]}'
            if "companyconcept" in url: return '{"units":{"shares":[{"val":2e8,"end":"2026-06-30","accn":"a","filed":"2026-08-01"}]}}'
            if "reference/tickers" in url: return '{"results":{"market_cap":2.1e9}}'
            return "{}"
        def get_json(self, url, use_cache=True):
            calls.append(url)
            return {"filings": {"recent": {"form": ["10-K", "4", "DEF 14A"], "accessionNumber": ["x", "y", "z"]}}, "sic": "1"}
    MU.fetch_all_tickers = lambda client: [Member(1, "AAA", "Alpha"), Member(2, "BBB", "Beta")]
    ck = str(tmp_path / "u.jsonl")
    # first run decides both and writes the checkpoint
    s1 = build_snapshot(Feed(), "k", snapshot="2026-09-01", checkpoint=ck)
    assert len(s1.members) == 2 and open(ck).read().count("\n") == 2
    # second run on the same day: no per-company fetches at all
    calls.clear()
    s2 = build_snapshot(Feed(), "k", snapshot="2026-09-01", checkpoint=ck)
    assert len(s2.members) == 2
    assert not any("submissions" in u or "companyconcept" in u or "reference" in u for u in calls)
    # a different day ignores the checkpoint and fetches again
    calls.clear()
    build_snapshot(Feed(), "k", snapshot="2026-12-01", checkpoint=ck)
    assert any("submissions" in u for u in calls)


def test_sizing_respects_each_measures_unit_domain():
    """The four false admissions of the first full snapshot, by root cause.
    AKTX/CMMB/SCNI are ADSs: EDGAR counts ORDINARY shares, the close
    prices the DEPOSITARY share -- the product is not a market cap. EAI
    is a first-mortgage BOND under an equity-looking ticker."""
    from fle.market_universe import (COMMON_TYPES, Row, classify, decide,
                                     newest_shares)

    # bonds, preferreds, warrants are not common-stock listings
    assert "SP" not in COMMON_TYPES and "ADRC" in COMMON_TYPES and "CS" in COMMON_TYPES

    # an ADS row: sec measure withheld, sized on vendor, honest note
    r = Row(cik=1, ticker="CMMB", company="Chemomab")
    r.mcap_vendor, r.mcap_sec = 19_857_959.0, None
    r.note = "ADS: ordinary-share count is not price-comparable; sized on the vendor figure"
    classify(r); decide(r, 1e9, 8e8, {}, "2026-08-31")
    assert r.status == "sized" and r.decision == "out"

    # the 50e9 backstop still refuses impossible counts at source
    class Feed:
        def get(self, url, use_cache=True):
            import json
            return json.dumps({"units": {"shares": [
                {"val": 155758529533, "accn": "a", "filed": "2026-08-01",
                 "end": "2026-06-30"}]}})
    assert newest_shares(Feed(), 1) is None

    # the 50x poisoned-ratio backstop still guards CS-typed collisions
    r = Row(cik=2, ticker="XYZ", company="Colliding Close Co")
    r.mcap_vendor, r.mcap_sec = 1_700_728.0, 35_237_164_943.0
    classify(r); decide(r, 1e9, 8e8, {}, "2026-08-31")
    assert r.status == "disagree" and r.mcap_sec is None and r.decision == "out"

    # no vendor record at all: a newcomer waits for a human; a member is kept
    r = Row(cik=3, ticker="NOV", company="No Vendor Co")
    r.mcap_vendor, r.mcap_sec = None, 9_114_954_766.0
    classify(r); decide(r, 1e9, 8e8, {}, "2026-08-31")
    assert r.decision == "out" and "sec-only newcomers" in r.note
    r2 = Row(cik=3, ticker="NOV", company="No Vendor Co")
    r2.mcap_vendor, r2.mcap_sec = None, 9_114_954_766.0
    classify(r2); decide(r2, 1e9, 8e8, {3: ("2026-05-01", 0)}, "2026-08-31")
    assert r2.decision in ("in", "kept")

    # an honest two-measure common is untouched
    r = Row(cik=4, ticker="OK", company="Fine Co")
    r.mcap_vendor, r.mcap_sec = 2.0e9, 2.1e9
    classify(r); decide(r, 1e9, 8e8, {}, "2026-08-31")
    assert r.status == "sized" and r.decision == "in"


# THE COVER COUNT IN THE CLOSE'S UNITS (2026-10-09). The $200M snapshot admitted
# New Fortress at $1.3B (285.6M shares x $4.55, after a 1-for-50) and Granite
# Point at $347M (48.2M x $7.20, after a 1-for-10 three days earlier); Polygon
# had them at $28M and $36M. Fifteen of 882 adds were reverse-split artifacts.
class _Vendor:
    """facts for the cover, splits for the ticker, both from one fake."""
    def __init__(self, facts, splits):
        self.facts, self.splits, self.asked = facts, splits, []

    def get(self, url, use_cache=True):
        return json.dumps(self.facts)

    def get_json(self, url, use_cache=True, max_age=None):
        self.asked.append(max_age)
        return {"results": self.splits}


def test_newest_cover_returns_the_counts_own_date():
    from fle.market_universe import newest_cover
    v = _Vendor({"units": {"shares": [
        {"val": 285_634_650, "end": "2026-07-28", "accn": "Q2", "filed": "2026-08-06"},
        {"val": 285_000_000, "end": "2026-04-28", "accn": "Q1", "filed": "2026-05-06"}]}}, [])
    assert newest_cover(v, 1) == (285_634_650, "2026-07-28")
    assert newest_cover(_Vendor({"units": {"shares": []}}, []), 1) == (None, "")


def test_a_reverse_split_after_the_cover_restates_the_count_for_sizing():
    from fle.market_universe import in_todays_shares
    nfe = _Vendor({}, [{"execution_date": "2026-09-14", "split_from": 50, "split_to": 1}])
    shares, note = in_todays_shares(nfe, "NFE", 285_634_650, "2026-07-28", "k")
    assert abs(shares - 5_712_693) < 1, "1-for-50: today's shares"
    assert abs(shares * 4.55 - 26e6) < 0.5e6, "and the product is a $26M company, not $1.3B"
    assert note.startswith("cover count 285,634,650 as of 2026-07-28 restated 0.02x")
    gpmt = _Vendor({}, [{"execution_date": "2026-10-05", "split_from": 10, "split_to": 1}])
    shares, note = in_todays_shares(gpmt, "GPMT", 48_198_166, "2026-06-30", "k")
    assert abs(shares - 4_819_817) < 1 and "0.1x" in note
    # a split BEFORE the cover is already in the count; a forward split scales up
    assert in_todays_shares(gpmt, "GPMT", 4_819_817, "2026-10-06", "k") == (4_819_817, "")
    sfbs = _Vendor({}, [{"execution_date": "2026-08-18", "split_from": 1, "split_to": 2}])
    assert in_todays_shares(sfbs, "SFBS", 54_672_510, "2026-07-31", "k")[0] == 109_345_020
    # nothing to size, nothing to ask
    assert in_todays_shares(sfbs, "X", None, "2026-07-31", "k") == (None, "")
    assert in_todays_shares(sfbs, "X", 100.0, "", "k") == (100.0, "")


def test_the_split_history_ages_like_a_feed():
    """Cached without a clock, a company's splits were frozen at its first
    walk (2026-10-09); they are now reread within a day and refetched after."""
    from fle.splits import fetch_splits
    from fle.config import SPLITS_MAX_AGE
    v = _Vendor({}, [{"execution_date": "2026-10-05", "split_from": 10, "split_to": 1}])
    sp = fetch_splits(v, "GPMT", "k")
    assert sp.events and sp.events[0].factor == 0.1
    assert v.asked == [SPLITS_MAX_AGE] and 0 < SPLITS_MAX_AGE <= 7 * 86400


def test_a_rehearsal_snapshot_does_not_write_the_universe_page():
    """A snapshot taken to _staging/ at another bar must leave the tracked
    universe.html describing the universe the site is running (2026-10-09)."""
    import inspect
    import fle.cli as C
    src = inspect.getsource(C.cmd_market_universe)
    assert '== "universe"' in src and "not written" in src
    guard = src[src.index("page = None"):src.index("by = {}")]
    assert "write_page(" in guard and guard.index('== "universe"') < guard.index("write_page(")
