"""The targeted refresh's merges: the fresh rows for the named companies
replace theirs in last night's file, every other row stays in place, a
partial file is never the result."""
import json
import os

from fle.cli import _merge_rows, _merge_state


def test_rows_are_replaced_in_place_and_nothing_else_moves(tmp_path):
    live = tmp_path / "panel.csv"
    live.write_text("ticker,ceo,pct\nAAA,a,1.0\nUPST,Paul Gu,1.33\nZZZ,z,9.0\n")
    fresh = tmp_path / "panel-stage.csv"
    fresh.write_text("ticker,ceo,pct\nUPST,Paul Gu,1.38\n")
    assert _merge_rows(str(live), str(fresh), ["UPST"], "ticker") == 1
    assert fresh.read_text() == "ticker,ceo,pct\nAAA,a,1.0\nUPST,Paul Gu,1.38\nZZZ,z,9.0\n", "the new row where the old one stood; the rest untouched"
    assert live.read_text().count("1.33") == 1, "the live file is not written by the merge; the publish step does that"


def test_history_rows_many_per_company_and_a_company_new_to_the_file(tmp_path):
    live = tmp_path / "history.csv"
    live.write_text("ticker,date,pct\nAAA,2026-01-01,1\nUPST,2026-01-01,1.2\nUPST,2026-06-01,1.33\nZZZ,2026-01-01,9\n")
    fresh = tmp_path / "history-stage.csv"
    fresh.write_text("ticker,date,pct\nUPST,2026-01-01,1.2\nUPST,2026-06-01,1.33\nUPST,2026-09-10,1.38\nNEWC,2026-09-10,5\n")
    assert _merge_rows(str(live), str(fresh), ["UPST", "NEWC"], "ticker") == 2
    assert fresh.read_text() == ("ticker,date,pct\nAAA,2026-01-01,1\nUPST,2026-01-01,1.2\nUPST,2026-06-01,1.33\nUPST,2026-09-10,1.38\n"
                                 "ZZZ,2026-01-01,9\nNEWC,2026-09-10,5\n")


def test_no_live_file_means_no_merge(tmp_path):
    fresh = tmp_path / "panel-stage.csv"
    fresh.write_text("ticker,pct\nUPST,1.38\n")
    assert _merge_rows(str(tmp_path / "missing.csv"), str(fresh), ["UPST"], "ticker") is None


def test_only_the_targeted_state_entries_move(tmp_path):
    live = tmp_path / "history-state.json"
    live.write_text(json.dumps({"AAA": "old-a", "UPST": "old-u"}))
    scratch = tmp_path / "scratch.json"
    scratch.write_text(json.dumps({"AAA": "scratch-a", "UPST": "new-u", "NEWC": "new-n"}))
    _merge_state(str(live), str(scratch), ["UPST", "NEWC"])
    assert json.loads(live.read_text()) == {"AAA": "old-a", "UPST": "new-u", "NEWC": "new-n"}


def test_the_confidence_cap_writes_its_note_once(tmp_path):
    """A targeted run carries rows over; the cap must not grow a copy of its
    note on every run (SPSC, the first targeted run)."""
    from fle.cli import edge_confidence
    panel = tmp_path / "panel.csv"
    panel.write_text("cik,ticker,pct,shares,confidence,cautions\n1,SPSC,0.48,174238,high,an earlier caution\n")
    hist = tmp_path / "history.csv"
    hist.write_text("ticker,date,shares,codes,restated,matches_panel\nSPSC,2026-01-01,5381717,,,\nSPSC,2026-02-20,174238,,,\n")
    n1 = edge_confidence(str(panel), str(hist))
    first = panel.read_text()
    n2 = edge_confidence(str(panel), str(hist))
    assert panel.read_text() == first, "a second cap changes nothing"
    assert first.count("balance far below") <= 1


def test_the_weekly_walk_has_its_flags_and_its_report(tmp_path, monkeypatch):
    """THE WEEKLY WALK (2026-09-20): --full (or a Sunday) forgets the nightly's
    memory; the odd moves are reported and mailed rather than refused; the
    report is written to drafts/ even with nothing to say."""
    import csv
    from fle import cli
    import inspect
    src = inspect.getsource(cli.main)
    assert '"--full"' in src and '"--no-full"' in src
    before, after = tmp_path / "before.csv", tmp_path / "after.csv"
    for pth, sh in ((before, "100"), (after, "90")):
        with open(pth, "w", newline="") as fh:
            w = csv.writer(fh); w.writerow(["ticker", "ceo", "shares", "pct", "shares_as_of"]); w.writerow(["AAA", "Some One", sh, "1.0", "2026-01-01"])
    monkeypatch.delenv("LIVE_TO", raising=False)
    cli._mail_weekly_diff(lambda m: None, str(tmp_path), ["AAA"], str(before), str(after))
    rep = next((tmp_path / "drafts").glob("weekly-walk-*.md")).read_text()
    assert "AAA" in rep and "100 ->" in rep and "90" in rep and "1 share count(s) moved" in rep
    cli._mail_weekly_diff(lambda m: None, str(tmp_path), [], str(before), str(after))
    assert "nothing moved without a filing" in next((tmp_path / "drafts").glob("weekly-walk-*.md")).read_text()


def test_a_company_that_leaves_the_site_is_named_the_same_night(tmp_path, monkeypatch):
    """WHO LEFT (2026-10-09): eight listed companies left on a misread Form 15
    and were not missed for three weeks. A company published yesterday and
    absent tonight is named with the files' reason, in its own report and in
    the weekly one; a targeted or nightly run alike."""
    import csv
    import inspect
    from fle import cli
    (tmp_path / "universe").mkdir()
    with open(tmp_path / "universe" / "delisted.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["ticker", "cik", "company", "ceo", "form", "date", "noted"])
        w.writerow(["CRNX", "1", "Crinetics", "R. Scott Struthers", "15-12B", "2026-09-15", "2026-09-17"])
    before, after = tmp_path / "before.csv", tmp_path / "after.csv"
    with open(before, "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["ticker", "company", "ceo", "shares", "pct", "shares_as_of"])
        w.writerow(["BMY", "BRISTOL MYERS SQUIBB CO", "Christopher Boerner", "100", "0.01", "2026-03-02"])
        w.writerow(["CRNX", "Crinetics", "R. Scott Struthers", "0", "0.0", "2026-09-01"])
        w.writerow(["TSLA", "Tesla", "Elon Musk", "1", "28.4", "2026-06-16"])
    with open(after, "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["ticker", "company", "ceo", "shares", "pct", "shares_as_of"])
        w.writerow(["TSLA", "Tesla", "Elon Musk", "1", "28.4", "2026-06-16"])
        w.writerow(["NEWCO", "New Co", "A Founder", "5", "5.0", "2026-10-01"])
    left = cli._departures(str(tmp_path), str(before), str(after))
    assert [t for t, _, _ in left] == ["BMY", "CRNX"]
    assert "Form 15-12B filed 2026-09-15" in left[1][2] and "vendor confirms" in left[1][2]
    assert "not in tonight's universe" in left[0][2], "no delisting on file: the universe dropped it, and the report says so"
    assert cli._departures(str(tmp_path), str(after), str(after)) == []
    monkeypatch.delenv("LIVE_TO", raising=False)
    logged = []
    cli._mail_departures(logged.append, str(tmp_path), left)
    rep = next((tmp_path / "drafts").glob("left-*.md")).read_text()
    assert "BMY" in rep and "CRNX" in rep and "2 companies published yesterday" in rep
    assert any("left the site: BMY, CRNX" in m for m in logged)
    cli._mail_weekly_diff(lambda m: None, str(tmp_path), [], str(before), str(after), left)
    wk = next((tmp_path / "drafts").glob("weekly-walk-*.md")).read_text()
    assert "2 companies left the site tonight" in wk and "BMY" in wk and "1 joined: NEWCO" in wk
    src = inspect.getsource(cli._refresh)
    assert "_departures(" in src and "_mail_departures(" in src
    assert src.index("_departures(") < src.index("_mail_weekly_diff(")
