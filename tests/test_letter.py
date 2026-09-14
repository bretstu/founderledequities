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
        ("TSLA", "Elon Musk", "2026-09-12", "2026-09-12", "P", "open-market purchase", "1000000000", "0.51", "28.44", "discretionary", ""),
        ("EQPT", "Jabbok Schlacks", "2026-09-10", "2026-09-09", "P", "open-market purchase", "271000", "0.05", "13.10", "discretionary", ""),
        ("EQPT", "Jabbok Schlacks", "2026-09-11", "2026-09-10", "P", "open-market purchase", "255000", "0.05", "13.15", "discretionary", "1"),
        ("BILL", "René Lacerte", "2026-09-09", "2026-09-08", "S", "discretionary sale", "10400000", "-7.15", "2.71", "discretionary", ""),
        ("DDOG", "Olivier Pomel", "2026-09-09", "2026-09-08", "S", "discretionary sale", "5600000", "-0.28", "2.60", "discretionary", ""),
        ("TSLA", "Elon Musk", "2026-09-08", "2026-09-08", "S", "scheduled sale", "38400000", "-0.30", "28.40", "plan", ""),
        ("UTHR", "Martine Rothblatt", "2026-09-08", "2026-09-08", "S", "exercise and sell", "", "", "1.56", "plan", ""),
        ("HIRE", "A Hire", "2026-09-08", "2026-09-08", "P", "open-market purchase", "5000000", "20", "1.0", "discretionary", ""),
        ("TSLA", "Elon Musk", "2026-08-01", "2026-08-01", "P", "open-market purchase", "1000000", "0.01", "28.00", "discretionary", ""),
    ]
    with open(tmp_path / "events.csv", "w") as fh:
        fh.write("ticker,ceo,filed,traded,code,label,value,pct_of_holding,pct_after,plan,first_buy,price_flag,url\n")
        for r in rows:
            fh.write(",".join(r) + ",,https://www.sec.gov/x\n")
    return str(tmp_path)


def test_the_week_is_founders_only_and_the_rows_collapse(tmp_path):
    root = _fixture(tmp_path)
    rows, since = letter.week_rows(root, "2026-09-14")
    assert since == "2026-09-07"
    assert not any(r["tk"] == "HIRE" for r in rows), "a hired CEO is not in the founders' tape"
    assert not any(r["traded"] == "2026-08-01" for r in rows), "outside the window"
    c = letter.collapse(rows)
    eq = [r for r in c if r["tk"] == "EQPT"]
    assert len(eq) == 1 and eq[0]["n"] == 2 and eq[0]["value"] == 526000 and eq[0]["after"] == 13.15 and eq[0]["first"]
    # kind order, ranked by the stake's move within each; a sale ranks by its cut
    kinds = [r["kind"] for r in c]
    assert kinds == sorted(kinds, key=lambda k: letter.KIND_ORDER[k])
    disc = [r["tk"] for r in c if r["kind"] == "disc"]
    assert disc[0] == "BILL", "the biggest cut leads the discretionary group"


def test_the_kicker_never_features_a_plan_or_compensation(tmp_path):
    root = _fixture(tmp_path)
    rows, _ = letter.week_rows(root, "2026-09-14")
    k = letter.kicker(rows)
    assert k[0].startswith("Largest open-market buy: Elon Musk, TSLA, $1B (stake +0.51%)")
    assert k[1].startswith("Largest discretionary sale: René Lacerte, BILL, $10.4M (stake in Pro)")
    assert "38.4M" not in " ".join(k), "Musk's $38.4M plan is not the sale of the week"


def test_the_draft_renders_in_the_sites_look_and_seals_the_stake(tmp_path):
    root = _fixture(tmp_path)
    md = letter.draft_markdown(root, "2026-09-14")
    assert md.startswith("---\ndate: 2026-09-14\nsubject: This week's tape: 2 CEOs bought, 2 cut a stake")
    assert "**2** CEOs bought · **1** for the first time ever · **2** cut a stake · **1** sold on a plan · **1** compensation filing did not move a stake" in md
    assert "| Bought | EQPT | Jabbok Schlacks (first buy) | $526K | Pro | Open market · 2 filings |" in md
    assert "| Bought | TSLA | Elon Musk | $1B | 28.44% | Open market |" in md
    h, t, meta = letter.render(md, postal="PO Box 1, Portland, ME 04101")
    assert meta["subject"].startswith("This week's tape")
    assert "Georgia" in h and "#F7F4EE" in h and "Read the full tape" in h
    assert h.count(">Pro</a>") == 3, "a small Pro tag where the stake is sealed (EQPT, BILL, UTHR sealed; DDOG and TSLA shown)"
    assert "{{{RESEND_UNSUBSCRIBE_URL}}}" in h and "PO Box 1" in h
    assert "28.44%" in t and "Unsubscribe" in t, "a plain-text alternative too"
    # the archive page uses the site's table classes and blurs, not the tag
    page = letter.archive_page(md, '<div class="top">nav</div>', "/site.css?v=abc")
    assert 'class="tape"' in page and page.count('class="sealed"') == 3 and 'href="/site.css?v=abc"' in page


def test_a_list_send_refuses_without_a_postal_line(tmp_path, monkeypatch):
    root = _fixture(tmp_path)
    md_p, _ = letter.paths(root, "2026-09-14")
    open(md_p, "w").write(letter.draft_markdown(root, "2026-09-14"))
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.delenv("POSTAL_ADDRESS", raising=False)
    import argparse
    rc = letter.cmd_send(argparse.Namespace(root=root, date="2026-09-14", test=False, send=True, confirm=False, to=None))
    assert rc == 2, "refused: no postal line"
