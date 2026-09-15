"""The sentence the site can say about one company: the stake now and a
year ago with the reason, the record, the URL. Nothing here posts anywhere.
The day's lines and the week's thread are ops/moves.py (tests/test_moves.py)."""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("fact", ROOT / "ops" / "fact.py")
fact = importlib.util.module_from_spec(spec)
sys.modules["fact"] = fact
spec.loader.exec_module(fact)


def _data(tmp_path, monkeypatch):
    (tmp_path / "panel.csv").write_text("ticker,company,ceo,pct,shares_as_of\nTSLA,Tesla,Elon Musk,28.4412,2026-06-16\nHIRE,Hired Co,A Hire,0.5,2026-06-01\n")
    (tmp_path / "founders.csv").write_text("ticker,founder\nTSLA,yes\nHIRE,no\n")
    cols = "ticker,ceo,filed,traded,code,label,value,pct_of_holding,pct_after,plan,pre_ipo,price_flag,first_buy"
    rows = [
        ("TSLA", "Elon Musk", "2026-09-12", "2026-09-12", "P", "open-market purchase", "1000000000", "0.51", "28.44", "discretionary", "", "", ""),
        ("TSLA", "Elon Musk", "2026-09-08", "2026-09-08", "S", "scheduled sale", "38400000", "-0.3", "28.4", "plan", "", "", ""),
        ("TSLA", "Elon Musk", "2019-01-01", "2019-01-01", "S", "exercise and sell", "1000", "", "", "plan", "", "", ""),
        ("HIRE", "A Hire", "2026-09-12", "2026-09-11", "S", "discretionary sale", "12000000", "-40", "0.5", "discretionary", "", "", ""),
        ("HIRE", "A Hire", "2026-09-12", "2026-09-11", "P", "open-market purchase", "5000", "1", "0.5", "discretionary", "", "", "1"),
    ]
    (tmp_path / "events.csv").write_text(cols + "\n" + "\n".join(",".join(r) for r in rows) + "\n")
    monkeypatch.setattr(fact, "ROOT", str(tmp_path))


def test_the_reply_is_the_stake_the_record_and_the_url(tmp_path, monkeypatch):
    _data(tmp_path, monkeypatch)
    panel, founders, by = fact.load()
    s = fact.fact("TSLA", panel, founders, by)
    assert s.startswith("Elon Musk owns 28.44% of Tesla (TSLA) as of the Jun 16 filing, a founder. Since 2016: 1 open-market buy, 1 sale that moved the stake. Last: bought $1B on the open market, Sep 12."), "no history file: the sentence stands without the year"
    assert s.endswith("https://founderledequities.com/company/TSLA/"), "the entity's address, never the home page"
    assert "exercise" not in s, "compensation is not a sale that moved the stake"




def test_the_reply_says_the_year_when_the_record_has_one(tmp_path, monkeypatch):
    _data(tmp_path, monkeypatch)
    (tmp_path / "history.csv").write_text(
        "ticker,date,accession,shares,shares_split_adjusted,outstanding,pct\n"
        "TSLA,2025-06-01,a1,400000000,400000000,3200000000,12.5\n"
        "TSLA,2026-06-16,a2,1120000000,1120000000,3950000000,28.4412\n")
    (tmp_path / "events.csv").write_text(
        "ticker,ceo,filed,traded,code,label,value,pct_of_holding,pct_after,plan,pre_ipo,price_flag,first_buy,net_change,accession\n"
        "TSLA,Elon Musk,2026-01-10,2026-01-10,A,award granted,,150,28.0,,,,,600000000,a2\n"
        "TSLA,Elon Musk,2026-06-16,2026-06-16,P,open-market purchase,1000000000,0.51,28.44,discretionary,,,,120000000,a2\n")
    panel, founders, by = fact.load()
    s = fact.fact("TSLA", panel, founders, by)
    assert "as of the Jun 16 filing, from 12.50% a year ago (compensation +150%, the share count -52%, bought +30%), a founder." in s, s
