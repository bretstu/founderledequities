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
