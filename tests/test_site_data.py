"""ops/build_site_data.py: the list files carry every column the page
reads, and a sealed row carries none of the columns that state its stake."""
import csv
import importlib.util
import os
import pathlib

HERE = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "build_site_data", HERE / "ops" / "build_site_data.py")
bsd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bsd)

# the columns index.html's mapPanel reads by name
PAGE_READS = {"ticker", "company", "ceo", "pct", "shares", "outstanding",
              "shares_as_of", "confidence", "cik", "form4_url",
              "excluded_shares", "excluded_detail", "problems", "cautions",
              "operating_partnership", "masked", "stake_source"}


def _write(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def test_list_files_carry_what_the_page_reads(tmp_path):
    bsd.OPEN_TOP = 0   # two-row fixture: the sealed row stays sealed
    panel_cols = ["cik", "ticker", "company", "ceo", "pct", "shares",
                  "outstanding", "shares_as_of", "confidence", "problems",
                  "cautions", "excluded_shares", "excluded_detail",
                  "operating_partnership", "flags", "error", "form4_url",
                  "cover_url", "stake_source"]
    rows = [
        dict(cik=1, ticker="BX", company="Blackstone", ceo="S. Schwarzman",
             pct="0.000", shares="0", outstanding="730000000",
             shares_as_of="2026-08-01", confidence="low", problems="",
             cautions="holds partnership units", excluded_shares="",
             excluded_detail="", operating_partnership="True", flags="",
             error="", form4_url="https://sec.gov/a", cover_url="", stake_source=""),
        dict(cik=2, ticker="ZZZ", company="Sealed Co", ceo="A. Founder",
             pct="12.5", shares="1000", outstanding="8000",
             shares_as_of="2026-07-01", confidence="high", problems="",
             cautions="", excluded_shares="50", excluded_detail="a trust",
             operating_partnership="False", flags="", error="",
             form4_url="https://sec.gov/b", cover_url="https://sec.gov/c",
             stake_source=""),
    ]
    _write(tmp_path / "panel.csv", panel_cols, rows)
    hcols = ["ticker", "date", "pct", "shares", "codes", "restated", "accession"]
    _write(tmp_path / "hist.csv", hcols,
           [dict(ticker="BX", date="2026-08-01", pct="0", shares="0",
                 codes="", restated="", accession="x")])
    ecols = ["ticker", "filed", "code"]
    _write(tmp_path / "events.csv", ecols,
           [dict(ticker="BX", filed="2026-08-01", code="P")])
    _write(tmp_path / "founders.csv", ["ticker", "founder"],
           [dict(ticker="BX", founder="yes"), dict(ticker="ZZZ", founder="yes")])
    _write(tmp_path / "sp.csv", ["ticker"], [dict(ticker="BX")])
    out = tmp_path / "site"
    assert bsd.main(str(tmp_path / "panel.csv"), str(tmp_path / "hist.csv"),
                    str(tmp_path / "events.csv"), str(tmp_path / "founders.csv"),
                    str(tmp_path / "sp.csv"), str(out)) == 0

    free = {r["ticker"]: r for r in csv.DictReader(open(out / "universe.csv"))}
    pro = {r["ticker"]: r for r in csv.DictReader(open(out / "pro" / "universe.csv"))}
    assert PAGE_READS <= set(free["BX"].keys()), \
        "the free list drops a column the page reads: " + \
        ", ".join(sorted(PAGE_READS - set(free["BX"].keys())))

    # the open row carries the structural facts the page renders
    assert free["BX"]["operating_partnership"] == "True"
    assert free["BX"]["shares_as_of"] == "2026-08-01"
    assert free["BX"]["cautions"] == "holds partnership units"
    assert free["BX"]["masked"] == "0"

    # the sealed row keeps the person and the date, loses the stake
    z = free["ZZZ"]
    assert z["masked"] == "1"
    for c in bsd.MASKED_COLS:
        assert z[c] == "", f"sealed row leaks {c}={z[c]!r}"
    assert z["ceo"] == "A. Founder" and z["shares_as_of"] == "2026-07-01"

    # the pro file is unmasked
    assert pro["ZZZ"]["masked"] == "0" and pro["ZZZ"]["pct"] == "12.5"
    assert pro["ZZZ"]["excluded_shares"] == "50"


def test_the_deploy_passes_the_live_files_and_the_member_list():
    """No overlay: the nightly's own files are the site's data, and the S&P
    list decides only what is open. A root copy of the full panel would
    publish every sealed stake."""
    sh = (HERE / "ops" / "deploy.sh").read_text()
    assert "panel.csv history.csv events.csv founders.csv" in sh
    assert "universe-data/" not in sh.replace("# ", "")  or "u-panel.csv" not in sh
    assert 'cp "$f" public/' not in sh.split("legacy")[-1] or "sp500.csv history-free.csv" not in sh
    assert "for f in sp500.csv history-free.csv" not in sh
    assert "universe.html public/" in sh


def test_nothing_still_calls_the_panel_sp500():
    """The panel held 500 rows once; it holds the universe now. The only
    thing named sp500 is the S&P list itself, universe/sp500-<date>.csv."""
    import re
    bad = []
    for sub in ("fle", "ops"):
        for p in (HERE / sub).rglob("*"):
            if p.suffix in (".py", ".sh") and p.is_file():
                for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                    if "sp500.csv" in line and "sp500-" not in line:
                        bad.append(f"{p.relative_to(HERE)}:{i}")
    for name in ("index.html", ".gitignore"):
        for i, line in enumerate((HERE / name).read_text(encoding="utf-8").splitlines(), 1):
            if "sp500.csv" in line and "sp500-" not in line:
                bad.append(f"{name}:{i}")
    assert not bad, "the panel is panel.csv now: " + ", ".join(bad)
    assert "panel.csv" in (HERE / ".gitignore").read_text()


def test_price_shards_are_public_for_every_ticker(tmp_path):
    """The seal is on the stake, never on the market: a sealed company's
    price file sits at the root like an open one's, straight from the
    daily store, so its page still draws the line."""
    from ops import build_site_data as bsd
    store = tmp_path / "store"
    store.mkdir()
    (store / "TSLA.csv").write_text("date,close\n2026-09-01,350.0000\n")
    (store / "SEALD.csv").write_text("date,close\n2026-09-01,10.0000\n")
    out = tmp_path / "site"
    assert bsd.write_price_shards(str(store), str(out)) == 2
    assert (out / "prices" / "SEALD.csv").read_text().splitlines()[1] == "2026-09-01,10.0000"
    assert bsd.write_price_shards(None, str(out)) == 0, "no store, no shards, no error"


def test_the_free_record_is_a_year_and_the_screener_has_its_counts(tmp_path):
    """PLAN.md section 2: an open company's free shard is its last twelve
    months with every figure; the archive is the Pro shard. The free feed
    keeps each S&P company's most recent trade whatever its date, so the
    screener's last-trade column stays true. screen-counts.json counts the
    screener's filters over every company."""
    import json
    b = bsd
    root = tmp_path
    (root / "universe").mkdir()
    (root / "sp.csv").write_text("ticker\nOPEN\n")
    (root / "panel.csv").write_text("ticker,company,ceo,pct,shares,outstanding,as_of,confidence,operating_partnership\n"
                                    "OPEN,Open Co,A,6.0,60,1000,2026-09-01,high,\nSEAL,Sealed Co,B,12.0,120,1000,2026-09-01,high,\nUNIT,Units Co,C,0,0,1000,2026-09-01,high,true\n")
    (root / "founders.csv").write_text("ticker,founder,evidence,source\nOPEN,yes,x,y\nSEAL,no,,\nUNIT,yes,x,y\n")
    (root / "history.csv").write_text("ticker,date,shares_raw,shares_adj,unexplained,outstanding,pct\nOPEN,2026-09-01,60,60,0,1000,6\nSEAL,2026-09-01,120,120,0,1000,12\n")
    cols = "ticker,cik,ceo,owner_cik,filed,traded,code,label,shares,value,avg_price,pct_of_holding,pct_approx,net_change,day_net,holding_after,outstanding,pct_after,residue,plan,other_codes,rows,unpriced_rows,securities,direct,form,accession,price_flag,url,registered,pre_ipo,avg_price_adjusted,traded_from,first_buy"
    def ev(tk, filed, code, label="open-market purchase"):
        d = {c: "" for c in cols.split(",")}
        d.update(ticker=tk, ceo="X", filed=filed, traded=filed, code=code, label=label, value="1000", pct_after="6", plan="discretionary")
        return ",".join(d[c] for c in cols.split(","))
    (root / "events.csv").write_text(cols + "\n" + "\n".join([
        ev("OPEN", "2019-03-01", "S", "discretionary sale"), ev("OPEN", "2026-08-01", "P"), ev("OPEN", "2024-01-01", "P"),
        ev("SEAL", "2026-08-15", "P"), ev("SEAL", "2020-01-01", "P")]) + "\n")
    out = root / "site-data"
    b.main(str(root / "panel.csv"), str(root / "history.csv"), str(root / "events.csv"), str(root / "founders.csv"),
           str(root / "sp.csv"), str(out))
    free_open = list(csv.DictReader(open(out / "events" / "OPEN.csv")))
    pro_open = list(csv.DictReader(open(out / "pro" / "events" / "OPEN.csv")))
    assert [r["filed"] for r in free_open] == ["2026-08-01"] and free_open[0]["value"] == "1000", "the free shard is the year, figures intact"
    assert len(pro_open) == 3, "the Pro shard is the whole record"
    feed = list(csv.DictReader(open(out / "events-free.csv")))
    open_rows = [r for r in feed if r["ticker"] == "OPEN"]
    assert [r["filed"] for r in open_rows] == ["2026-08-01"], "the feed carries the year; the most recent trade is inside it"
    counts = json.load(open(out / "screen-counts.json"))
    assert counts["m0f0h0"] == 2 and counts["m10f0h0"] == 1 and counts["m0f1h0"] == 1 and counts["m0f0h1"] == 1, counts
    # the named screens, counted over every company: SEAL never sold and owns 12%; OPEN is a founder who bought this year
    assert counts["s:never-sold"] == 1 and counts["s:over-10"] == 1 and counts["s:bought-this-year"] == 2 and counts["s:hired-under-1"] == 0, counts
    # never sold: OPEN sold in 2019, SEAL never did
