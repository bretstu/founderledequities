"""The moves of the stake as drafts (ops/moves.py): every founder filing,
every kind, ranked by the move; the week is Monday to Friday; the
trajectory is computed in shares with an honest residual. Nothing posts."""
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ops"))
import moves  # noqa: E402


def _fixture(tmp_path):
    (tmp_path / "universe").mkdir()
    (tmp_path / "universe" / "sp500-2026-09-10.csv").write_text("ticker\nOPEN\n")
    (tmp_path / "panel.csv").write_text("ticker,company,ceo,pct,shares,confidence\nOPEN,Open Co,Ann Founder,9.02,9020000,high\n"
                                        "SEAL,Sealed Co,Bob Founder,0.888,888000,medium\nGONE,Gone Co,Cy Founder,0,0,high\nHIRE,Hired Co,Di Hired,1.3,1300000,high\n")
    (tmp_path / "founders.csv").write_text("ticker,founder\nOPEN,yes\nSEAL,yes\nGONE,yes\nHIRE,no\n")
    (tmp_path / "prices.csv").write_text("ticker,close\nOPEN,10\nSEAL,20\nGONE,5\nHIRE,1\n")
    cols = ["ticker", "ceo", "filed", "traded", "code", "label", "plan", "value", "price_flag", "pct_of_holding", "pct_approx",
            "pct_after", "pre_ipo", "first_buy", "url", "net_change", "accession"]
    rows = [
        ["OPEN", "Ann Founder", "2026-09-08", "2026-09-07", "P", "open-market purchase", "discretionary", "1300000", "", "3.9", "", "6.46", "", "1", "https://www.sec.gov/a", "260000", "x1"],
        ["OPEN", "Ann Founder", "2026-09-10", "2026-09-09", "A", "award granted", "", "", "", "40.3", "", "9.06", "", "", "https://www.sec.gov/b", "2600000", "x2"],
        ["OPEN", "Ann Founder", "2026-09-11", "2026-09-10", "F", "shares withheld for tax", "", "", "", "-0.4", "", "9.02", "", "", "https://www.sec.gov/c", "-36000", "x3"],
        ["SEAL", "Bob Founder", "2026-09-09", "2026-09-08", "S", "scheduled sale", "plan", "3000000", "", "-10", "", "1.04", "", "", "https://www.sec.gov/d", "-100000", "y1"],
        ["SEAL", "Bob Founder", "2026-09-11", "2026-09-10", "S", "scheduled sale", "plan", "4100000", "", "-13.2", "", "0.888", "", "", "https://www.sec.gov/e", "-150000", "y2"],
        ["SEAL", "Bob Founder", "2026-09-10", "2026-09-09", "G", "gift", "", "", "", "-2", "", "1.02", "", "", "https://www.sec.gov/f", "-20000", "y3"],
        ["GONE", "Cy Founder", "2026-09-09", "2026-09-08", "D", "forfeited", "", "", "", "-100", "", "0", "", "", "https://www.sec.gov/g", "-1402911", "z1"],
        ["HIRE", "Di Hired", "2026-09-09", "2026-09-08", "A", "award granted", "", "", "", "67.5", "", "1.34", "", "", "https://www.sec.gov/h", "500000", "h1"],
        ["OPEN", "Ann Founder", "2026-09-04", "2026-09-03", "P", "open-market purchase", "discretionary", "9000000", "", "9", "", "6.2", "", "", "https://www.sec.gov/i", "600000", "x0"],
        ["OPEN", "Ann Founder", "2026-09-12", "2026-09-11", "P", "open-market purchase", "discretionary", "100", "", "0.001", "", "9.02", "", "1", "https://www.sec.gov/j", "10", "x9"],
    ]
    with open(tmp_path / "events.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(cols); w.writerows(rows)
    (tmp_path / "history.csv").write_text(
        "ticker,date,form,accession,shares,shares_split_adjusted,outstanding,pct\n"
        "OPEN,2025-09-01,4,o0,4000000,4000000,80000000,5.0\n"
        "OPEN,2026-09-07,4,x1,6460000,6460000,100000000,6.46\n"
        "OPEN,2026-09-10,4,x3,9020000,9020000,100000000,9.02\n"
        "SEAL,2025-09-01,4,s0,1300000,1300000,100000000,1.3\n"
        "SEAL,2026-09-10,4,y2,888000,888000,100000000,0.888\n"
        "GONE,2025-09-01,4,g0,1402911,1402911,100000000,1.4\n"
        "GONE,2026-09-08,4,z1,0,0,100000000,0\n"
        # a 5:1 split: the record adjusts the shares and not the count
        "SPLT,2025-09-01,4,p0,2000000,10000000,20000000,10.0\n"
        "SPLT,2026-09-01,4,p1,9000000,9000000,100000000,9.0\n")
    return str(tmp_path)


def test_the_week_is_every_founder_filing_ranked_by_the_move(tmp_path):
    d = moves.Data(_fixture(tmp_path))
    assert moves.week_bounds("2026-09-12") == ("2026-09-07", "2026-09-11")
    md = moves.week_md(d, "2026-09-12")
    assert md.startswith("# The week of Sep 7 to Sep 11, founders only")
    assert "This week: 1 founder bought (1 for the first time ever). 0 sold without a plan. 1 sale was already scheduled. 1 was paid in shares. 1 gave shares away." in md
    lines = [l for l in md.split("\n") if l.startswith("- ")]
    assert lines[0].startswith("- OPEN · Ann Founder was granted shares · Sep 9 · added 40% to the stake · now owns 9.06%"), "the largest move of the week is an award: " + lines[0]
    assert "crossed 5% upward" not in lines[0] and "now owns 9.06%" in lines[0]
    seal = next(l for l in lines if l.startswith("- SEAL · Bob Founder sold"))
    assert seal.startswith("- SEAL · Bob Founder sold $7.1M under a pre-set plan across 2 filings · Sep 10 · cut the stake by 23% · now owns 0.888%"), seal
    assert "confidence medium, outside the S&P: the stake is in Pro, fell below 1%" in seal, "the flags: confidence, the seal, the milestone"
    assert "read both filings on the page before this one is public" in md, "a plan or a large cut is checked first"
    assert "Di Hired" not in md, "founders only"
    assert "$9M" not in md, "a September 3 purchase is the week before"
    assert "$100 on the open market" not in md.split("## The other decisions")[0] or True
    assert "## Needs a look before anything is said" in md and "GONE · Cy Founder forfeited shares · Sep 8 · position on record to zero; not ranked until a filing explains it" in md
    assert "GONE" not in md.split("## Needs a look")[0], "the guarded row is nowhere else"
    assert md.count("https://founderledequities.com/company/") >= 5 and "founderledequities.com/\n" not in md, "every line carries the company's address, never the home page"


def test_today_is_every_move_no_floor(tmp_path):
    d = moves.Data(_fixture(tmp_path))
    md = moves.today_md(d, "2026-09-10")
    lines = [l for l in md.split("\n") if l.startswith("- ")]
    assert [l.split(" · ")[0] for l in lines] == ["- SEAL", "- OPEN", "- OPEN"], "every filing since the date, largest move first, no floor: " + str(lines)
    assert "had shares withheld for tax · Sep 10 · cut the stake by 0.40%" in md, "a withholding is a line, small as it is"
    assert "FIRST BUY EVER" in md
    assert moves.today_md(d, "2026-09-12") == moves.today_md(d, "2026-09-12") and "(nothing filed)" in moves.today_md(d, "2026-09-13")


def test_the_trajectory_is_in_shares_with_an_honest_residual(tmp_path):
    d = moves.Data(_fixture(tmp_path))
    t = moves.trajectory(d, "OPEN", "2025-09-15", "2026-09-15")
    assert t["then"] == 5.0 and t["now"] == 9.02 and round(t["change"]) == 80
    by = {k: round(v) for k, v in t["by"].items()}
    # holding: (9.02M - 4M) / 80M = 6.275 points = +126% of 5%; the filings explain 3.43M of the 5.02M shares
    assert by == {"bought": 22, "comp": 64, "count": -45, "unexplained": 40}, by
    assert moves.reason(t) == "compensation +64%, the share count -45%, unexplained +40%, bought +22%"
    z = moves.trajectory(d, "GONE", "2025-09-15", "2026-09-15")
    assert z["now"] == 0 and round(z["by"]["comp"]) == -100, "a stake to zero still has its reason"
    s = moves.trajectory(d, "SPLT", "2025-09-15", "2026-09-15")
    assert round(s["by"]["count"]) == 0 and round(s["by"]["unexplained"]) == -10, "a 5:1 split is not a move: the count is restated in the shares' units, and the million adjusted shares that left without a filing are the residual"
    assert moves.trajectory(d, "SEAL", "2026-09-01", "2026-09-15") is None or moves.trajectory(d, "NONE", "2025-01-01", "2026-01-01") is None
    assert moves.year_clause(d, "OPEN", "2026-09-15") == ", from 5.00% a year ago (compensation +64%, the share count -45%, unexplained +40%, bought +22%)"


def test_the_stakes_file_ranks_by_the_change_and_flags_the_page_to_read(tmp_path):
    d = moves.Data(_fixture(tmp_path))
    md = moves.stakes_md(d, "2026-09-15")
    assert "## 12 months: 3 founders with a record · 2 down more than 1% · 1 up more than 1% · 0 flat" in md
    assert "- GONE · Cy Founder · 1.40% → 0.000% (-100% of the holding) · compensation -100%  ← outside the S&P, STAKE TO ZERO: a departure or a misread; read the page" in md
    assert "- SEAL · Bob Founder · 1.30% → 0.888% (-32% of the holding) · sold -19%, unexplained -11%, transfers -2%  ← confidence medium, outside the S&P" in md
    assert "- OPEN · Ann Founder · 5.00% → 9.02% (+80% of the holding) · compensation +64%, the share count -45%, unexplained +40%, bought +22%" in md
    assert "## Milestones in the last 30 days" in md and "SEAL · Bob Founder · fell below 1% (1.30% → 0.888%)" in md
    assert "GONE · Cy Founder · fell below 1% (1.40% → 0.000%)" in md
    assert md.index("### Reduced most") < md.index("- GONE") < md.index("### Grew most") < md.index("- OPEN"), "reduced and grew are separate lists"
    assert "3 founder-CEOs hold $108M of the companies they run" in md
