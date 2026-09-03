"""One curated file, two directions. universe/exclusions.csv removes what a
filing attributes to the CEO but the company says is not theirs (TKO), and
adds what a filer states in a remark is held of record but left out of
the tables (SpaceX). No regex or model reads the sentence; a person does,
once, and the entry carries the filing as its source."""
import os

from fle.exclusions import Exclusion, read_exclusions
from fle.panel import apply_additions

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _add(**kw):
    base = dict(cik="1181412", ticker="SPCX", security="Class B Common Stock (restricted; disclosed in a remark)",
                direct="D", reason="This Form 4 does not include 1,302,072,285 shares ...",
                source="https://www.sec.gov/Archives/edgar/data/1181412/000162828026044069/wk-form4_1781740812.xml",
                shares=1302072285.0, owner_cik="1494730", since="2026-06-11")
    base.update(kw)
    return Exclusion(**base)


def test_an_addition_adds_the_shares_and_labels_the_source():
    row = {"shares": 4766475230.0, "outstanding": 13181779945.0, "pct": 36.16,
           "cautions": "convertible class counted (Class B Common Stock)",
           "remarks": "This Form 4 does not include 1,302,072,285 shares of unvested ...",
           "direct_classes": "", "owner_cik": "1494730"}
    apply_additions(row, [_add()])
    assert row["shares"] == 4766475230.0 + 1302072285
    assert abs(row["pct"] - 46.04) < 0.01, "6.07B over the same 13.18B outstanding"
    assert row["shares_tabled"] == 4766475230.0, "the tables' figure rides beside it"
    assert row["stake_source"] == "manual"
    assert "in a remark rather than a table" in row["cautions"] and "wk-form4_1781740812" in row["cautions"]
    assert row["cautions"].startswith("convertible class counted"), "earlier cautions kept"


def test_the_tables_win_when_the_class_appears_held_directly():
    """A vesting tranche, or a change of filing position, puts Class B in a
    table as a direct holding. The walk sees it; the addition suspends;
    nothing is counted twice."""
    row = {"shares": 4766475230.0 + 66_700_000, "outstanding": 13181779945.0, "pct": 36.7, "cautions": "",
           "remarks": "This Form 4 does not include 1,235,372,285 shares ...",
           "direct_classes": "class:B", "owner_cik": "1494730"}
    apply_additions(row, [_add()])
    assert row["shares"] == 4766475230.0 + 66_700_000, "the tables' figure stands alone"
    assert "suspended" in row["cautions"] and "held directly" in row["cautions"]
    assert "stake_source" not in row and "shares_tabled" not in row


def test_the_figure_must_still_be_asserted_commas_or_not():
    from fle.panel import _digits_present
    assert _digits_present("does not include 1,302,072,285 shares", 1302072285)
    assert _digits_present("does not include 1302072285 shares", 1302072285)
    assert _digits_present("does not include 1 302 072 285 shares", 1302072285)
    assert not _digits_present("does not include 1,235,372,285 shares", 1302072285), "a vested tranche changes the figure"
    assert not _digits_present("does not include 1,302,072,258 shares", 1302072285), "a typo is a changed figure"
    assert not _digits_present("11,302,072,285", 1302072285), "not a substring of a longer number"
    row = {"shares": 4766475230.0, "outstanding": 13181779945.0, "pct": 36.16, "cautions": "",
           "remarks": "This Form 4 does not include 1,235,372,285 shares of unvested ...", "direct_classes": "", "owner_cik": "1494730"}
    apply_additions(row, [_add()])
    assert row["shares"] == 4766475230.0 and "no longer states that figure" in row["cautions"]


def test_an_addition_lapses_when_the_newest_filing_carries_no_remark():
    row = {"shares": 4766475230.0, "outstanding": 13181779945.0, "pct": 36.16, "cautions": "", "remarks": "", "owner_cik": "1494730"}
    apply_additions(row, [_add()])
    assert row["shares"] == 4766475230.0 and abs(row["pct"] - 36.16) < 0.01
    assert "lapsed" in row["cautions"] and "read it" in row["cautions"]
    assert "stake_source" not in row


def test_applied_once_and_only_once():
    row = {"ticker": "SPCX", "shares": 4766475230.0, "outstanding": 13181779945.0, "pct": 36.16,
           "cautions": "", "remarks": "does not include 1,302,072,285 shares ...", "owner_cik": "1494730"}
    for _ in range(2):
        if row.get("shares_tabled") in (None, ""):
            apply_additions(row, [_add()])
    assert row["shares"] == 4766475230.0 + 1302072285
    assert row["cautions"].count("in a remark rather than a table") == 1


def test_the_loader_separates_the_two_directions_and_demands_a_receipt(tmp_path):
    p = tmp_path / "exclusions.csv"
    p.write_text("cik,ticker,security,direct,reason,source,shares,owner_cik,since\n"
                 "1,TKO,Class B Common Stock,I,attributed not owned,https://sec.gov/x,,,\n"
                 "2,SPCX,Class B Common Stock,D,the remark says so,https://sec.gov/y,1302072285,1494730,2026-06-11\n",
                 encoding="utf-8")
    ex = read_exclusions(str(p))
    assert [e.ticker for e in ex.for_issuer(1)] == ["TKO"], "the walk sees exclusions"
    assert ex.for_issuer(2) == [], "an addition is not an exclusion"
    assert [e.shares for e in ex.additions_for("SPCX")] == [1302072285.0]
    p.write_text("cik,ticker,security,direct,reason,source,shares,owner_cik,since\n"
                 "2,SPCX,Class B Common Stock,D,,https://sec.gov/y,1302072285,1494730,2026-06-11\n", encoding="utf-8")
    try:
        read_exclusions(str(p)); assert False, "an addition without the quoted sentence is a guess"
    except ValueError as e:
        assert "without quoting" in str(e)
    p.write_text("cik,ticker,security,direct,reason,source,shares,owner_cik,since\n"
                 "2,SPCX,Class B Common Stock,D,the remark,https://sec.gov/y,1302072285,,2026-06-11\n", encoding="utf-8")
    try:
        read_exclusions(str(p)); assert False, "an addition without an owner would pass to a successor"
    except ValueError as e:
        assert "owner" in str(e)


def test_the_repo_entry_for_spacex_is_exactly_the_remark():
    ex = read_exclusions(os.path.join(ROOT, "universe", "exclusions.csv"))
    adds = ex.additions_for("SPCX")
    assert len(adds) == 1 and adds[0].shares == 1302072285
    assert "does not include 1,302,072,285" in adds[0].reason
    assert "000162828026044069" in adds[0].source
    assert [e.ticker for e in ex.for_issuer(1973266)] == ["TKO"], "the TKO exclusion is untouched"


def test_a_row_from_an_older_schema_is_recomputed_not_carried():
    """A carried row computed before `remarks` existed has nothing to test a
    curated addition against; it must be walked again once, not reported
    lapsed forever."""
    from fle.panel import _reusable
    old = {"fingerprint": "abc", "error": "", "settled": "1", "shares": 1.0}
    assert not _reusable(old)
    new = dict(old, remarks="", direct_classes="")
    assert _reusable(new), "an empty remark is a value; a missing field is not"


def test_stake_source_reaches_the_csv():
    from fle.panel import COLUMNS
    assert "stake_source" in COLUMNS and "shares_tabled" in COLUMNS and "remarks" in COLUMNS


def test_the_guard_reads_class_titles_the_way_the_walk_does():
    """'Class B', 'Class B Common Stock' and 'Restricted Class B Common
    Stock, par value $0.001' are one class to the walk; the guard must not
    miss a table line because the filer phrased the title differently."""
    from fle.ledger import title_letter
    for title in ("Class B", "Class B Common Stock", "Restricted Class B Common Stock, par value $0.001",
                  "Class B common stock"):
        assert title_letter(title) == ("class", "B"), title
    row = {"shares": 100.0, "outstanding": 1000.0, "pct": 10.0, "cautions": "",
           "remarks": "does not include 50 shares", "direct_classes": "class:B", "owner_cik": "1494730"}
    apply_additions(row, [_add(security="Restricted Class B Common Stock, par value $0.001", shares=50.0)])
    assert row["shares"] == 100.0 and "suspended" in row["cautions"], "a differently worded table line still wins"


def test_an_edited_entry_makes_the_carried_row_stale():
    from fle.panel import _addition_current
    ex = read_exclusions(os.path.join(ROOT, "universe", "exclusions.csv"))
    a = ex.additions_for("SPCX")[0]
    key = f"SPCX:{int(a.shares)}:{a.source}"
    assert _addition_current({"ticker": "SPCX", "addition_key": key}, ex), "same entry: carry"
    assert not _addition_current({"ticker": "SPCX", "addition_key": "SPCX:1:x"}, ex), "changed entry: walk again"
    assert not _addition_current({"ticker": "SPCX"}, ex), "entry added since: walk again"
    assert _addition_current({"ticker": "TSLA"}, ex), "no entry, none before: carry"
    assert not _addition_current({"ticker": "TSLA", "addition_key": "TSLA:5:y"}, ex), "entry removed since: walk again"


def test_a_successor_does_not_inherit_the_addition():
    row = {"shares": 100.0, "outstanding": 1000.0, "pct": 10.0, "cautions": "",
           "remarks": "does not include 1,302,072,285 shares", "direct_classes": "", "owner_cik": "999"}
    apply_additions(row, [_add()])
    assert row["shares"] == 100.0 and "belongs to owner CIK 1494730" in row["cautions"]


def test_the_repo_entry_names_the_owner_and_the_date():
    ex = read_exclusions(os.path.join(ROOT, "universe", "exclusions.csv"))
    a = ex.additions_for("SPCX")[0]
    assert a.owner_cik == "1494730" and a.since == "2026-06-11"


def test_the_addition_reaches_the_record_from_its_date():
    """The chart under the band must end where the band says."""
    from fle.history import apply_additions_to_series
    rows = [{"ticker": "SPCX", "owner_cik": "0001494730", "date": "2026-06-10", "shares": 4.0e9, "shares_split_adjusted": 4.0e9, "outstanding": 1.3e10, "pct": 30.77},
            {"ticker": "SPCX", "owner_cik": "0001494730", "date": "2026-06-15", "shares": 4766475230.0, "shares_split_adjusted": 4766475230.0, "outstanding": 13181779945.0, "pct": 36.16},
            {"ticker": "SPCX", "owner_cik": "0000000999", "date": "2026-07-01", "shares": 10.0, "shares_split_adjusted": 10.0, "outstanding": 1000.0, "pct": 1.0}]
    apply_additions_to_series(rows, [_add()])
    assert abs(rows[0]["pct"] - 30.77) < 0.01, "before the since date: untouched"
    assert abs(rows[1]["pct"] - 46.04) < 0.01 and rows[1]["shares_split_adjusted"] == 4766475230.0 + 1302072285
    assert rows[2]["pct"] == 1.0, "another owner's point: untouched"
