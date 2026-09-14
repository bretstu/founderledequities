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
