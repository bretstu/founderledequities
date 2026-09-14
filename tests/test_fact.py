"""The sentences the site can say: the reply per company, the day's lines,
the Monday thread. Nothing here posts anywhere."""
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
    assert s.startswith("Elon Musk owns 28.44% of Tesla (TSLA) as of the Jun 16 filing, a founder. Since 2016: 1 open-market buy, 1 sale that moved the stake. Last: bought $1B on the open market, Sep 12.")
    assert s.endswith("https://founderledequities.com/company/TSLA/"), "the entity's address, never the home page"
    assert "exercise" not in s, "compensation is not a sale that moved the stake"


def test_todays_lines_are_decisions_only_notable_first(tmp_path, monkeypatch):
    _data(tmp_path, monkeypatch)
    panel, founders, by = fact.load()
    lines = fact.today_lines(panel, founders, by, "2026-09-10")
    assert len(lines) == 3, lines
    assert "HIRE" in lines[0] and "$10M+ at discretion" in lines[0] and "stake -40%" in lines[0], "the notable line leads"
    assert any("first buy ever" in l for l in lines)
    assert not any("38.4M" in l for l in lines), "a plan is not a decision"
    assert all("/company/" in l for l in lines)
