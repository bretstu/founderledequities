"""The Monday tape: drafted from the data, rendered in the site's look,
never sent by the pipeline."""
import importlib.util
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("letter", ROOT / "ops" / "letter.py")
letter = importlib.util.module_from_spec(spec)
sys.modules["letter"] = letter
spec.loader.exec_module(letter)


def _fixture(tmp_path):
    (tmp_path / "universe").mkdir()
    (tmp_path / "universe" / "sp500-2026-09-03.csv").write_text("ticker\nTSLA\nDDOG\n")
    (tmp_path / "panel.csv").write_text("ticker,company\nTSLA,Tesla\nEQPT,Equipment Co\nDDOG,Datadog\nBILL,Bill\nUTHR,United\n")
    (tmp_path / "founders.csv").write_text("ticker,founder\nTSLA,yes\nEQPT,yes\nDDOG,yes\nBILL,yes\nUTHR,yes\nHIRE,no\n")
    rows = [
        # ticker,cik,ceo,owner_cik,filed,traded,code,label,shares,value,avg_price,pct_of_holding,pct_approx,net_change,day_net,holding_after,outstanding,pct_after,residue,plan,other_codes,rows,unpriced_rows,securities,direct,form,accession,price_flag,url,registered,pre_ipo,avg_price_adjusted,traded_from,first_buy
        ("TSLA", "Elon Musk", "2026-09-11", "2026-09-11", "P", "open-market purchase", "1000000000", "0.51", "28.44", "discretionary", ""),
        ("UTHR", "Martine Rothblatt", "2026-09-10", "2026-09-10", "A", "award granted", "", "40", "2.20", "", ""),
        ("DDOG", "Olivier Pomel", "2026-09-11", "2026-09-10", "G", "gift", "", "-3", "2.52", "", ""),
        ("EQPT", "Jabbok Schlacks", "2026-09-06", "2026-09-05", "P", "open-market purchase", "9000000", "9", "13.0", "discretionary", ""),
        ("EQPT", "Jabbok Schlacks", "2026-09-10", "2026-09-09", "P", "open-market purchase", "271000", "0.05", "13.10", "discretionary", ""),
        ("EQPT", "Jabbok Schlacks", "2026-09-11", "2026-09-10", "P", "open-market purchase", "255000", "0.05", "13.15", "discretionary", "1"),
        ("BILL", "René Lacerte", "2026-09-09", "2026-09-08", "S", "discretionary sale", "10400000", "-7.15", "2.71", "discretionary", ""),
        ("DDOG", "Olivier Pomel", "2026-09-09", "2026-09-08", "S", "discretionary sale", "5600000", "-0.28", "2.60", "discretionary", ""),
        ("TSLA", "Elon Musk", "2026-09-08", "2026-09-08", "S", "scheduled sale", "38400000", "-0.30", "28.40", "plan", ""),
        ("UTHR", "Martine Rothblatt", "2026-09-08", "2026-09-08", "S", "exercise and sell", "", "", "1.56", "plan", ""),
        ("HIRE", "A Hire", "2026-09-08", "2026-09-08", "P", "open-market purchase", "5000000", "20", "1.0", "discretionary", ""),
        ("BILL", "René Lacerte", "2026-09-09", "2026-09-08", "D", "forfeited", "", "-100", "0", "", ""),
        ("TSLA", "Elon Musk", "2026-08-01", "2026-08-01", "P", "open-market purchase", "1000000", "0.01", "28.00", "discretionary", ""),
    ]
    with open(tmp_path / "events.csv", "w") as fh:
        fh.write("ticker,ceo,filed,traded,code,label,value,pct_of_holding,pct_after,plan,first_buy,price_flag,url\n")
        for r in rows:
            fh.write(",".join(r) + ",,https://www.sec.gov/x\n")
    return str(tmp_path)


def test_the_week_is_monday_to_friday_every_kind_and_the_rows_collapse(tmp_path):
    root = _fixture(tmp_path)
    assert letter.week_bounds("2026-09-12") == ("2026-09-07", "2026-09-11"), "a Saturday run: the week just closed"
    assert letter.week_bounds("2026-09-14") == ("2026-09-07", "2026-09-11"), "a Monday run: the last complete week, not the one starting"
    assert letter.week_bounds("2026-09-11") == ("2026-09-07", "2026-09-11"), "a Friday is its own week's end"
    rows, monday = letter.week_rows(root, "2026-09-12")
    assert monday == "2026-09-07"
    assert not any(r["tk"] == "HIRE" for r in rows), "a hired CEO is not in the founders' tape"
    assert not any(r["traded"] in ("2026-08-01", "2026-09-05") for r in rows), "outside the week: a September 5 purchase belongs to the week before"
    assert any(r["kind"] == "comp" and r["tk"] == "UTHR" and r["label"] == "award granted" for r in rows), "an award is a row of the week"
    assert any(r["kind"] == "xfer" and r["tk"] == "DDOG" for r in rows), "a gift is a row of the week"
    c = letter.collapse(rows)
    eq = [r for r in c if r["tk"] == "EQPT"]
    assert len(eq) == 1 and eq[0]["n"] == 2 and eq[0]["value"] == 526000 and eq[0]["after"] == 13.15 and eq[0]["first"]
    kinds_ = [r["kind"] for r in c]
    assert kinds_ == sorted(kinds_, key=lambda k: letter.KIND_ORDER[k])
    disc = [r["tk"] for r in c if r["kind"] == "disc"]
    assert disc[0] == "BILL", "the biggest cut leads the discretionary group"
    assert [r for r in rows if r["guarded"]][0]["tk"] == "BILL", "a forfeiture of the whole holding is guarded"


def test_the_kicker_is_the_largest_move_and_the_largest_buy(tmp_path):
    root = _fixture(tmp_path)
    rows, _ = letter.week_rows(root, "2026-09-12")
    k = letter.kicker(rows)
    assert k[0] == "Largest move: Martine Rothblatt, UTHR, award granted (stake in Pro).", k[0]
    assert k[1].startswith("Largest open-market buy: Elon Musk, TSLA, $1B (stake +0.51%)")
    assert "forfeited" not in " ".join(k), "the guarded row is never featured"


def test_the_draft_is_the_issues_skeleton_in_the_settled_template(tmp_path):
    """THE TEMPLATE (2026-09-20): the feature, two more decisions, moved the
    stake, the week's decisions, one ranking. The pipeline fills the
    tables and the shortlist; the writing is left in brackets."""
    root = _fixture(tmp_path)
    md = letter.draft_markdown(root, "2026-09-12")
    assert md.startswith("---\ndate: 2026-09-12\ntitle: ") and "\nfeatured: " in md and "\nweek: Sep 7 to Sep 11\n" in md
    for h in ("## [The feature:", "## Two more decisions", "## Moved the stake", "## The week's decisions", "## One ranking"):
        assert h in md, h
    assert "| Kind | Company | CEO | Amount | Shares | Of holding | Stake |" in md
    assert "| Bought | TSLA | Elon Musk | $1B |" in md and "+0.51% | 28.44% |" in md, "a decision row, with shares and the move as a share of the holding"
    assert "| Transfer | DDOG | Olivier Pomel |" in md and "-3.00% | 2.52% |" in md, "a gift that moved the holding by 3% is in Moved the stake"
    assert "Pro" not in md.split("## The feature")[0], "nothing is sealed (2026-09-18)"
    assert "NEEDS A LOOK BEFORE THE SEND (not in the tables): René Lacerte, BILL: forfeited took the position on record to zero." in md
    h, t, meta = letter.render(md, unsubscribe_url="{{{RESEND_UNSUBSCRIBE_URL}}}", postal="PO Box 1, Portland, ME")
    assert meta["title"] and "Georgia" in h and "#F7F4EE" in h and "every filing" in h
    assert "{{{RESEND_UNSUBSCRIBE_URL}}}" in h and "PO Box 1" in h
    assert "28.44%" in t and "Unsubscribe" in t, "a plain-text alternative too"
    page = letter.archive_page(md, '<div class="top">nav</div>', "/site.css?v=abc")
    assert 'class="ltable"' in page and 'href="/site.css?v=abc"' in page and 'rel="canonical" href="https://founderledequities.com/letter/' in page
    assert 'class="kind xfer"' in page and 'class="lh2"' in page



def test_a_list_send_refuses_without_a_postal_line(tmp_path, monkeypatch):
    root = _fixture(tmp_path)
    md_p, _ = letter.paths(root, "2026-09-14")
    open(md_p, "w").write(letter.draft_markdown(root, "2026-09-14"))
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.delenv("POSTAL_ADDRESS", raising=False)
    import argparse
    rc = letter.cmd_send(argparse.Namespace(root=root, date="2026-09-14", test=False, send=True, confirm=False, to=None))
    assert rc == 2, "refused: no postal line"


def test_a_list_send_refuses_without_the_audience_id(tmp_path, monkeypatch):
    root = _fixture(tmp_path)
    md_p, _ = letter.paths(root, "2026-09-14")
    open(md_p, "w").write(letter.draft_markdown(root, "2026-09-14"))
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("POSTAL_ADDRESS", "PO Box 1")
    monkeypatch.delenv("RESEND_AUDIENCE_ID", raising=False)
    monkeypatch.delenv("RESEND_SEGMENT_ID", raising=False)
    import argparse
    rc = letter.cmd_send(argparse.Namespace(root=root, date="2026-09-14", test=False, send=True, confirm=False, to=None))
    assert rc == 2, "a list send never guesses its audience"
    monkeypatch.setenv("RESEND_SEGMENT_ID", "seg_1")
    assert letter.list_target() == {"segment_id": "seg_1"}, "a segment meaning everyone is how the list is addressed"
