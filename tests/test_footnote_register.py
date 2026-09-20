"""The register from the decisions (2026-09-19)."""
import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ops"))
import footnote_register as FR  # noqa: E402


def test_decided_disclaimed_lines_become_vehicle_rows_and_hand_rows_stay(tmp_path, monkeypatch):
    root = tmp_path
    (root / "universe").mkdir()
    with open(root / "panel.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["ticker", "cik", "ceo"]); w.writerow(["META", "1326801", "Mark Zuckerberg"]); w.writerow(["SNAP", "1564408", "Evan Spiegel"])
    with open(root / "universe" / "footnote-reads.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["key", "ticker", "ceo", "owner_cik", "accession", "row", "security", "direct", "nature", "shares", "label", "quote", "url"])
        w.writerow(["1|a|1|h1", "META", "Mark Zuckerberg", "1", "a", "1", "Class A Common Stock", "I", "By Chan Zuckerberg Biohub, Inc.", "1231037", "disclaimed", "has no pecuniary interest in these shares", "https://sec.gov/a"])
        w.writerow(["1|b|1|h1", "META", "Mark Zuckerberg", "1", "b", "1", "Class A Common Stock", "I", "By Chan Zuckerberg Biohub, Inc.", "1231037", "disclaimed", "has no pecuniary interest in these shares", "https://sec.gov/b"])
        w.writerow(["1|a|2|h2", "META", "Mark Zuckerberg", "1", "a", "2", "Class A Common Stock", "I", "By CZI Holdings, LLC", "340000000", "economic", "", "https://sec.gov/a"])
        w.writerow(["2|c|1|h3", "SNAP", "Evan Spiegel", "2", "c", "1", "Class A Common Stock", "I", "See footnote", "2027844", "disclaimed", "has no financial interest", "https://sec.gov/c"])
        w.writerow(["2|c|2|h4", "SNAP", "Evan Spiegel", "2", "c", "2", "Class A Common Stock", "I", "See footnote", "500", "economic", "", "https://sec.gov/c"])
    with open(root / "universe" / "footnote-reviewed.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["key", "verdict", "note", "label"])
        w.writerow(["1|a|1|h1", "ok", "a charity", "disclaimed"]); w.writerow(["1|b|1|h1", "ok", "a charity", "disclaimed"]); w.writerow(["2|c|1|h3", "ok", "no financial interest", "disclaimed"])
    with open(root / "universe" / "exclusions.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FR.COLUMNS); w.writeheader()
        w.writerow({"cik": "1973266", "ticker": "TKO", "security": "Class B Common Stock", "direct": "I", "reason": "hand", "source": "https://sec.gov/t"})
    monkeypatch.setattr(FR, "ROOT", str(root))
    monkeypatch.setattr(FR, "READS", str(root / "universe" / "footnote-reads.csv"))
    monkeypatch.setattr(FR, "REVIEWED", str(root / "universe" / "footnote-reviewed.csv"))
    assert FR.main([]) == 0
    rows = list(csv.DictReader(open(root / "universe" / "exclusions.csv", encoding="utf-8-sig")))
    assert [r["ticker"] for r in rows] == ["TKO", "META"], "the hand row stays; the Biohub is one row across two filings; Snap's anonymous line beside another is skipped"
    assert open(root / "universe" / "rewalk-next.txt").read().split() == ["META"], "a changed company is listed for the next walk (2026-09-20)"
    (root / "universe" / "rewalk-next.txt").unlink()
    FR.main([])
    assert not (root / "universe" / "rewalk-next.txt").exists(), "nothing changed: nothing to rewalk"
    meta = rows[1]
    assert meta["vehicle"] == "By Chan Zuckerberg Biohub, Inc." and meta["reason"] == "has no pecuniary interest in these shares" and meta["decided"].startswith("reader ")
    # a later `no` removes the row
    with open(root / "universe" / "footnote-reviewed.csv", "a", newline="") as fh:
        csv.writer(fh).writerow(["1|a|1|h1", "no", "changed my mind", "disclaimed"]); csv.writer(fh).writerow(["1|b|1|h1", "no", "changed my mind", "disclaimed"])
    FR.main([])
    rows = list(csv.DictReader(open(root / "universe" / "exclusions.csv", encoding="utf-8-sig")))
    assert [r["ticker"] for r in rows] == ["TKO"]


def test_a_copied_reading_inherits_the_ruling_of_the_line_it_was_copied_from():
    """THE NIGHTLY (2026-09-20): a founder's next filing repeats last month's
    footnote; the reader copies the reading, and the decision comes with it."""
    import footnote_review as FRv
    reads = [
        {"key": "1|a|1|h", "label": "disclaimed", "content": "C1"},     # decided by hand
        {"key": "1|b|1|h", "label": "disclaimed", "content": "C1"},     # the next filing, same words: inherits
        {"key": "1|b|2|h", "label": "disclaimed", "content": "C2"},     # new words: not decided
        {"key": "1|c|1|h", "label": "economic", "content": "C1"},       # same words, a different label: not the same ruling
    ]
    reviewed = {"1|a|1|h": {"key": "1|a|1|h", "verdict": "ok", "note": "a charity", "label": "disclaimed"}}
    d = FRv.decided(reads, reviewed)
    assert d["1|a|1|h"][0] == "ok" and d["1|b|1|h"][0] == "ok" and "(inherited)" in d["1|b|1|h"][1] and d["1|b|1|h"][2] == "1|a|1|h"
    assert "1|b|2|h" not in d and "1|c|1|h" not in d
