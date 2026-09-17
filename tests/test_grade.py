"""THE GRADE (fle/grade.py, 2026-09-17): four checks on the shapes read this
week -- Amplitude (a partial statement), Bloom (a retired class), EquipmentShare
(a convertible class and nothing else), Ubiquiti (an old numerator, a fresh
count), and a clean founder."""
import csv
import datetime as dt
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fle.grade import chain, statement, classes, denominator, grade_row, apply_grades, FEWER_LINES  # noqa: E402

TODAY = dt.date(2026, 9, 17)


def _row(**kw):
    base = {"ticker": "X", "owner_cik": "1", "pct": "5.0", "shares": "1000000", "outstanding": "20000000",
            "outstanding_as_of": "2026-06-30", "problems": "", "cautions": "", "lines_stated": "2026-09-01",
            "operating_partnership": "false"}
    base.update(kw)
    return base


def _h(date, shares, unexplained, form="4", owner="1"):
    return {"ticker": "X", "date": date, "form": form, "shares": str(shares), "unexplained": str(unexplained), "owner_cik": owner, "accession": date}


def test_the_chain_is_the_last_year_filing_to_filing():
    clean = [_h("2026-03-01", 1000000, 0), _h("2026-06-01", 990000, 0)]
    assert chain(clean, "1", TODAY) == ("pass", "")
    # AMPLITUDE: the newest filing named the direct line only; 800,000 of 1,000,000 left with no transaction
    partial = clean + [_h("2026-09-01", 190000, -800000)]
    lvl, text = chain(partial, "1", TODAY)
    assert lvl == "fail" and "2026-09-01" in text and "fell 81%" in text, "800,000 of the 990,000 before"
    # a small open step is a warn; a step from two years ago is outside the window
    assert chain(clean + [_h("2026-09-01", 1030000, 30000)], "1", TODAY)[0] == "warn"
    assert chain([_h("2024-01-01", 500000, -400000)] + clean, "1", TODAY) == ("pass", "")
    # a Form 3 is a statement, not a step; another person's rows are not this chain
    assert chain([_h("2026-05-01", 1000000, 1000000, form="3")] + clean, "1", TODAY) == ("pass", "")
    assert chain([_h("2026-05-01", 3000000, -2000000, owner="9")] + clean, "1", TODAY) == ("pass", "")
    assert chain([], "1", TODAY) == ("pass", "")


def test_the_statement_check_reads_freshness_and_wholeness():
    assert statement(_row(), TODAY) == ("pass", "")
    assert statement(_row(lines_stated="2026-09-01|2024-06-01"), TODAY)[0] == "warn", "a line eighteen months old"
    lvl, text = statement(_row(lines_stated="2026-09-01|2010-03-12"), TODAY)
    assert lvl == "fail" and "2010-03-12" in text, "Lithia's 2010 Class B, before the retirement rule closed it"
    assert statement(_row(cautions=FEWER_LINES + ", with no transaction"), TODAY)[0] == "warn"
    assert statement(_row(problems="3 line(s) only ever footnoted, so the total is a floor"), TODAY)[0] == "fail"


def test_the_classes_check():
    assert classes(_row()) == ("pass", "")
    assert classes(_row(cautions="convertible class counted (Class B Common Stock); confirm the ratio is 1:1"))[0] == "warn", "EquipmentShare"
    assert classes(_row(cautions="a class the company retired is not counted: Class B Common Stock last stated 2021-05-10"))[0] == "warn", "Bloom"
    assert classes(_row(problems="class(es) counted from the person's filings but absent from the cover page: Class C"))[0] == "fail"
    assert classes(_row(problems="walk did not settle; the total is a floor"))[0] == "fail"
    assert classes(_row(operating_partnership="true", pct="0.001"))[0] == "fail", "Blackstone's units"


def test_the_denominator_check_is_the_counts_age_against_today():
    assert denominator(_row(), TODAY) == ("pass", "")
    assert denominator(_row(outstanding_as_of="2026-03-31"), TODAY)[0] == "warn", "170 days old"
    assert denominator(_row(outstanding_as_of="2025-06-30"), TODAY)[0] == "fail", "more than a year"
    assert denominator(_row(outstanding=""), TODAY)[0] == "fail"
    assert denominator(_row(shares="30000000"), TODAY)[0] == "fail", "a stake over 100%"
    # UBIQUITI: Pera has not filed since 2017; the count is fresh; the numerator's age is not graded
    r = _row(lines_stated="2017-06-01", outstanding_as_of="2026-06-30")
    assert denominator(r, TODAY) == ("pass", "")


def test_the_grade_is_the_worst_check_and_the_reason_is_its_sentence():
    clean = [_h("2026-06-01", 1000000, 0)]
    g = grade_row(_row(), clean, TODAY)
    assert g["confidence"] == "high" and g["reason"] == "" and all(g[c] == "pass" for c in ("chain", "statement", "classes", "denominator"))
    # EquipmentShare: a convertible class and nothing else -> medium, not low (the empty-class problem is gone)
    g = grade_row(_row(cautions="convertible class counted (Class B Common Stock); confirm the ratio is 1:1"), clean, TODAY)
    assert g["confidence"] == "medium" and g["classes"].startswith("warn") and "one for one" in g["reason"]
    # Amplitude: the chain fails and the statement warns; the reason is the fail's sentence
    g = grade_row(_row(cautions=FEWER_LINES, lines_stated="2026-09-01"), clean + [_h("2026-09-01", 190000, -800000)], TODAY)
    assert g["confidence"] == "low" and g["chain"].startswith("fail") and g["statement"].startswith("warn") and "does not close" in g["reason"]
    # Ubiquiti: an old numerator alone is a statement fail (a line last stated nine years ago), the count itself fine
    g = grade_row(_row(lines_stated="2017-06-01"), [], TODAY)
    assert g["confidence"] == "low" and g["statement"].startswith("fail") and g["denominator"] == "pass"
    # identity: the matched insider is not flagged as an officer -> low even with the four passing
    g = grade_row(_row(problems="the matched insider (X) is not flagged as an officer or director"), clean, TODAY)
    assert g["confidence"] == "low" and "not flagged" in g["reason"]
    assert grade_row(_row(pct="", shares=""), clean, TODAY)["confidence"] == "none"


def test_apply_grades_writes_the_columns_and_puts_the_reason_first(tmp_path):
    panel = tmp_path / "panel.csv"
    with open(panel, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["ticker", "owner_cik", "pct", "shares", "outstanding", "outstanding_as_of", "problems", "cautions", "lines_stated", "operating_partnership", "confidence"])
        w.writeheader()
        w.writerow({"ticker": "AMPL", "owner_cik": "1", "pct": "1.2", "shares": "190000", "outstanding": "120000000", "outstanding_as_of": "2026-06-30",
                    "problems": "", "cautions": "numerator and denominator 200 days apart", "lines_stated": "2026-09-01", "operating_partnership": "false", "confidence": "high"})
        w.writerow({"ticker": "OK", "owner_cik": "2", "pct": "5", "shares": "1000000", "outstanding": "20000000", "outstanding_as_of": "2026-06-30",
                    "problems": "", "cautions": "", "lines_stated": "2026-09-01", "operating_partnership": "false", "confidence": "medium"})
    hist = tmp_path / "history.csv"
    with open(hist, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["ticker", "owner_cik", "date", "form", "shares", "unexplained", "accession"])
        w.writeheader()
        w.writerow({"ticker": "AMPL", "owner_cik": "1", "date": "2026-06-01", "form": "4", "shares": "990000", "unexplained": "0", "accession": "a"})
        w.writerow({"ticker": "AMPL", "owner_cik": "1", "date": "2026-09-01", "form": "4", "shares": "190000", "unexplained": "-800000", "accession": "b"})
    out = apply_grades(str(panel), str(hist), TODAY)
    assert out["tally"] == {"low": 1, "high": 1} and ("AMPL", "high", "low") in out["moved"] and ("OK", "medium", "high") in out["moved"]
    rows = {r["ticker"]: r for r in csv.DictReader(open(panel, encoding="utf-8-sig"))}
    assert rows["AMPL"]["confidence"] == "low" and rows["AMPL"]["chain"].startswith("fail") and rows["AMPL"]["problems"].startswith("the arithmetic does not close")
    assert rows["AMPL"]["cautions"] == "numerator and denominator 200 days apart", "the old caution stays, after the grade's reason"
    assert rows["OK"]["confidence"] == "high" and rows["OK"]["chain"] == "pass" and rows["OK"]["problems"] == ""
    # idempotent: a second pass does not duplicate the reason
    apply_grades(str(panel), str(hist), TODAY)
    rows = {r["ticker"]: r for r in csv.DictReader(open(panel, encoding="utf-8-sig"))}
    assert rows["AMPL"]["problems"].count("does not close") == 1


def test_history_names_a_retirements_closing_as_explained():
    """ACV, BRAZE: the group counted until the first cover without its class
    and stopped on it; that row's drop is our own rule, not an open step."""
    from fle.history import _newly_closed
    from fle.ledger import Group
    g = Group(security="Class B Common Stock", direct="D")
    g.shares = 861722
    g.filed = "2025-01-02"
    groups = {"class b common stock": g}
    retired = {("class", "B"): "2025-02-14"}
    assert _newly_closed(groups, retired, "2025-02-14", "2025-01-02", None) == 861722, "closed on the cover date: explained"
    assert _newly_closed(groups, retired, "2025-03-01", "2025-02-14", None) == 0, "already closed before: nothing new"
    assert _newly_closed(groups, retired, "2025-01-10", "2025-01-02", None) == 0, "before the cut: still open"
    assert _newly_closed(groups, {}, "2025-02-14", "2025-01-02", None) == 0
