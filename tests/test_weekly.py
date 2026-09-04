"""The weekly briefing notices what the week produced, by the site's rules:
founders only for the founder sections, kept-apart trades never counted as
stake moves, firsts flagged, and week-over-week milestones from its own
snapshot."""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ops"))
import weekly  # noqa: E402


def _fixture(tmp_path):
    def w(name, rows, cols):
        with open(tmp_path / name, "w", newline="", encoding="utf-8") as fh:
            x = csv.DictWriter(fh, fieldnames=cols); x.writeheader(); x.writerows(rows)
    ev_cols = ["ticker", "ceo", "filed", "traded", "code", "label", "shares", "value", "avg_price",
               "pct_of_holding", "pct_approx", "plan", "url", "price_flag", "pre_ipo", "registered"]
    w("events.csv", [
        {"ticker": "FND", "ceo": "A Founder", "filed": "2026-09-02", "traded": "2026-09-01", "code": "P", "label": "purchase",
         "shares": 1000, "value": 100000, "avg_price": 100, "pct_of_holding": 2.0, "pct_approx": "", "plan": "discretionary",
         "url": "https://sec.gov/f1", "price_flag": "", "pre_ipo": "0", "registered": "2015-01-01"},
        {"ticker": "FND", "ceo": "A Founder", "filed": "2026-09-03", "traded": "2026-09-02", "code": "S", "label": "sale",
         "shares": 500, "value": 60000, "avg_price": 120, "pct_of_holding": 1.0, "pct_approx": "", "plan": "discretionary",
         "url": "https://sec.gov/f2", "price_flag": "", "pre_ipo": "0", "registered": "2015-01-01"},
        {"ticker": "FND", "ceo": "A Founder", "filed": "2026-09-03", "traded": "2026-09-02", "code": "S", "label": "exercise and sell",
         "shares": 5000, "value": 900000, "avg_price": 180, "pct_of_holding": "", "pct_approx": "", "plan": "plan",
         "url": "https://sec.gov/f3", "price_flag": "", "pre_ipo": "0", "registered": "2015-01-01"},
        {"ticker": "HIRE", "ceo": "A Hire", "filed": "2026-09-02", "traded": "2026-09-01", "code": "P", "label": "purchase",
         "shares": 100, "value": 5000000, "avg_price": 50000, "pct_of_holding": 8.0, "pct_approx": "", "plan": "discretionary",
         "url": "https://sec.gov/h1", "price_flag": "", "pre_ipo": "0", "registered": "2010-01-01"},
        {"ticker": "NEWC", "ceo": "A Newcomer", "filed": "2026-09-01", "traded": "2026-06-01", "code": "S", "label": "sale",
         "shares": 10, "value": 1000, "avg_price": 100, "pct_of_holding": "", "pct_approx": "", "plan": "",
         "url": "https://sec.gov/n1", "price_flag": "", "pre_ipo": "1", "registered": "2026-09-01"},
    ], ev_cols)
    w("panel.csv", [
        {"ticker": "FND", "company": "Founder Co", "ceo": "A Founder", "pct": "12.0", "shares": "12000000"},
        {"ticker": "HIRE", "company": "Hired Co", "ceo": "A Hire", "pct": "0.5", "shares": "1000"},
        {"ticker": "NEWC", "company": "New Co", "ceo": "A Newcomer", "pct": "30.0", "shares": "300"},
    ], ["ticker", "company", "ceo", "pct", "shares"])
    w("founders.csv", [{"ticker": "FND", "founder": "yes"}, {"ticker": "HIRE", "founder": "no"}, {"ticker": "NEWC", "founder": "yes"}],
      ["ticker", "founder"])
    w("prices.csv", [{"ticker": "FND", "close": "110"}, {"ticker": "HIRE", "close": "1"}, {"ticker": "NEWC", "close": "2"}], ["ticker", "close"])
    (tmp_path / "universe").mkdir()
    w("universe/sp500-2026-09-03.csv", [{"ticker": "FND"}, {"ticker": "HIRE"}], ["ticker"])
    return str(tmp_path)


def test_the_briefing_follows_the_sites_rules(tmp_path):
    root = _fixture(tmp_path)
    md = tmp_path / "b.md"; js = tmp_path / "b.json"
    weekly.build(root, "2026-08-28", "2026-09-04", str(md), str(js))
    text = md.read_text(encoding="utf-8"); b = json.load(open(js))
    assert "**A Founder**, FND — $100,000 · +2.0% of stake · discretionary" in text, "the founder's purchase, exact below $1M, labelled"
    assert "paid $100.00, now $110.00 (+10.0%)" in text, "and where the stock is now against what he paid"
    assert len(b["sections"]["founder_buys"]) == 1, "the hired CEO's purchase is not a founder purchase"
    assert "NON-FOUNDER" in text and "A Hire" in text, "but it appears in the comparison section, marked"
    assert "FIRST SALE ON RECORD" in text, "the founder's first stake-moving sale is flagged"
    assert "KEPT APART: exercise and sell" in text and "$900,000" in text, "options cashed is headline-vs-filing, never a stake move"
    assert "$900,000" not in "".join(b["sections"]["founder_sells_discretionary"]), "and never in the sales list"
    assert "NEWC (New Co) began Section 16 reporting on 2026-09-01" in text, "a new registrant is a milestone"
    assert "1 of 2 S&P 500 CEOs own more than 5%" in text
    assert os.path.exists(tmp_path / "weekly" / "snapshots" / "2026-09-04.csv"), "the snapshot for next week"


def test_milestones_come_from_the_prior_snapshot(tmp_path):
    root = _fixture(tmp_path)
    weekly.build(root, "2026-08-21", "2026-08-28", str(tmp_path / "a.md"), str(tmp_path / "a.json"))
    # a week later the founder's stake has crossed 25%
    rows = list(csv.DictReader(open(tmp_path / "panel.csv", encoding="utf-8")))
    for r in rows:
        if r["ticker"] == "FND":
            r["pct"] = "26.0"
    with open(tmp_path / "panel.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    weekly.build(root, "2026-08-28", "2026-09-04", str(tmp_path / "b.md"), str(tmp_path / "b.json"))
    text = (tmp_path / "b.md").read_text(encoding="utf-8")
    assert "stake crossed above 25% (12.00% → 26.00%)" in text
    assert "never-sold streak ended" in text, "his first-ever sale this week ended a streak"
