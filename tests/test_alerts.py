"""The nightly's half of the watches: which filings are posted, and the
high-water mark."""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("alerts", ROOT / "ops" / "alerts.py")
alerts = importlib.util.module_from_spec(spec)
sys.modules["alerts"] = alerts
spec.loader.exec_module(alerts)


def test_only_decisions_are_posted(tmp_path):
    """An open-market purchase and a discretionary sale are posted; a plan,
    compensation, a pre-IPO catch-up and anything filed before the mark are
    not. Nobody asked for those."""
    cols = "ticker,ceo,filed,traded,code,label,value,pct_after,plan,pre_ipo,price_flag,accession,url"
    rows = [
        ("TSLA", "Elon Musk", "2026-09-12", "2026-09-12", "P", "open-market purchase", "1000000000", "28.44", "discretionary", "", "", "0001-A", "https://www.sec.gov/a"),
        ("BILL", "René Lacerte", "2026-09-11", "2026-09-10", "S", "discretionary sale", "10400000", "2.71", "discretionary", "", "", "0001-B", "https://www.sec.gov/b"),
        ("ABNB", "Brian Chesky", "2026-09-11", "2026-09-10", "S", "scheduled sale", "38400000", "12.22", "plan", "", "", "0001-C", ""),
        ("UTHR", "Martine Rothblatt", "2026-09-11", "2026-09-10", "S", "exercise and sell", "", "1.56", "plan", "", "", "0001-D", ""),
        ("NEWC", "New Co", "2026-09-11", "2019-01-01", "P", "open-market purchase", "5000", "10", "discretionary", "1", "", "0001-E", ""),
        ("OLDX", "Old Trade", "2026-09-01", "2026-09-01", "P", "open-market purchase", "5000", "10", "discretionary", "", "", "0001-F", ""),
        ("FLAG", "No Price", "2026-09-12", "2026-09-12", "P", "open-market purchase", "5000", "10", "discretionary", "", "unpriced", "0001-G", ""),
    ]
    p = tmp_path / "events.csv"
    p.write_text(cols + "\n" + "\n".join(",".join(r) for r in rows) + "\n")
    out = alerts.decisions(str(p), "2026-09-05")
    assert [e["accession"] for e in out] == ["0001-A", "0001-B", "0001-G"]
    assert out[0]["value"] == 1e9 and out[1]["code"] == "S" and out[2]["value"] is None, "a flagged price is not a value"
    assert out[0]["url"] == "https://www.sec.gov/a" and out[0]["pct_after"] == "28.44"


def test_a_watch_mails_any_move_of_the_stake(tmp_path):
    """ONE DEFINITION OF A MOVE (2026-09-17): buys and discretionary sales of
    any size; anything else at 1% of the holding or more; nothing for a
    0.3% planned sale, a pre-IPO row, or a share-count restatement."""
    import csv
    import os
    import sys
    sys.path.insert(0, os.path.join(str(ROOT), "ops"))
    import alerts
    p = tmp_path / "events.csv"
    cols = ["ticker", "ceo", "filed", "traded", "code", "label", "value", "pct_of_holding", "pct_after", "plan", "price_flag", "pre_ipo", "accession", "url"]
    rows = [
        {"ticker": "UPST", "ceo": "Paul Gu", "filed": "2026-09-10", "traded": "2026-09-10", "code": "P", "label": "purchase", "value": "1300000", "pct_of_holding": "3.9", "pct_after": "1.38"},
        {"ticker": "BOX", "ceo": "Aaron Levie", "filed": "2026-09-11", "traded": "2026-09-10", "code": "S", "label": "sale", "value": "513660", "pct_of_holding": "-0.52", "plan": "plan"},
        {"ticker": "DBX", "ceo": "Andrew W. Houston", "filed": "2026-09-14", "traded": "2026-09-10", "code": "S", "label": "sale", "value": "13400000", "pct_of_holding": "-1.4", "plan": "plan"},
        {"ticker": "SECZ", "ceo": "Carlos Domingo", "filed": "2026-09-14", "traded": "2026-09-10", "code": "A", "label": "award granted", "value": "", "pct_of_holding": "5.0"},
        {"ticker": "PCVX", "ceo": "Grant Pickering", "filed": "2026-09-09", "traded": "2026-09-08", "code": "F", "label": "withheld for tax", "value": "", "pct_of_holding": "-0.4"},
        {"ticker": "CMPR", "ceo": "Robert S. Keane", "filed": "2026-09-15", "traded": "2026-09-11", "code": "S", "label": "sale", "value": "2400000", "pct_of_holding": "-0.3"},
        {"ticker": "NEWCO", "ceo": "X", "filed": "2026-09-15", "traded": "2026-09-15", "code": "P", "label": "purchase", "value": "100", "pct_of_holding": "99", "pre_ipo": "1"},
    ]
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
        for r in rows: w.writerow({c: r.get(c, "") for c in cols})
    got = {e["tk"]: e for e in alerts.decisions(str(p), since="2026-09-01", founders={"UPST", "DBX", "CMPR"}, names={})}
    assert set(got) == {"UPST", "DBX", "SECZ", "CMPR"}, sorted(got)
    assert got["UPST"]["kind"] == "decision" and "bought $1.3M of UPST on the open market." == got["UPST"]["sentence"].split(" ", 2)[2], got["UPST"]["sentence"]
    assert got["UPST"]["shares"] == "" and got["UPST"]["move"] == "3.9" and got["UPST"]["company"] == "UPST", "no panel here: the ticker stands for the name"
    assert got["CMPR"]["kind"] == "decision" and "at their own discretion" in got["CMPR"]["sentence"], "a discretionary sale of any size"
    assert got["DBX"]["kind"] == "move" and "under a pre-set plan" in got["DBX"]["sentence"], "a planned sale that moved the stake 1.4%"
    assert got["SECZ"]["kind"] == "move" and "award granted moved the SECZ stake +5.0%." in got["SECZ"]["sentence"]
    assert "BOX" not in got and "PCVX" not in got, "under 1%: not a move"
    assert got["UPST"]["founder"] and got["SECZ"]["founder"] is False, "the founder flag is the live alert's scope"
    run = open(os.path.join(str(ROOT), "functions", "api", "watch", "run.js"), encoding="utf-8").read()
    assert "e.sentence" in run and '(e.sentence || e.code === "P" || e.code === "S")' in run, "the mail says what the tape says"
    # THE MAIL (2026-09-17): the day and the size, the stake after and before, one link, a footer naming the alert
    assert "function dayLine" in run and "function stakeLine" in run and "on Founder Led Equities" in run and "Stop everything" in run
    assert "The filing." not in run and "plans and compensation never come this way" not in run
    from alerts import short_name, before_pct
    assert short_name("Upstart Holdings, Inc.", "UPST") == "Upstart" and short_name("", "X") == "X"
    assert round(before_pct({"holding_after": "1000", "net_change": "100", "outstanding": "100000"}), 3) == 0.9
