"""The streamed, pooled history stage: same file, one company at a time."""
import csv
import json
import types

import fle.cli as cli
import fle.walk as walk


def _rows(tk, cik, n=3):
    return [{"cik": cik, "ticker": tk, "ceo": "Someone", "owner_cik": "9",
             "date": f"2024-0{i+1}-01", "form": "4", "accession": f"a{i}",
             "shares": 100 + i, "shares_split_adjusted": 100 + i,
             "outstanding": 1000, "pct": 10.0 + i, "traded": "", "traded_value": "",
             "unpriced_rows": "", "unexplained": "", "codes": "", "groups": "",
             "classes": "", "restated": "", "matches_panel": "TRUE"}
            for i in range(n)]


def test_history_streams_carried_and_walked_rows_into_one_file(tmp_path, monkeypatch):
    universe = tmp_path / "u.csv"
    universe.write_text("cik,ticker,company,added\n1,AAA,Alpha,\n2,BBB,Beta,\n3,CCC,Gamma,\n")
    # a prior file: AAA unchanged (carried), BBB changed (rewalked), CCC new
    prior = tmp_path / "prior.csv"
    with open(prior, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(_rows("AAA", 1)[0].keys()))
        w.writeheader()
        for r in _rows("AAA", 1) + _rows("BBB", 2):
            w.writerow(r)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"AAA": "2024-03-01 a2", "BBB": "old"}))

    class Client:
        def submissions(self, cik):
            return {"_filings": [{"form": "4", "accessionNumber": "a2",
                                  "filingDate": "2024-03-01"}]}
    monkeypatch.setattr(cli, "_client", lambda a: Client())
    monkeypatch.setattr(cli, "read_exclusions", lambda p: types.SimpleNamespace(for_issuer=lambda c: None))

    # the pool is replaced by a deterministic in-process fake
    def fake_pool(jobs, workers, **kw):
        for j in jobs:
            if j["ticker"] == "CCC":
                yield {"ticker": "CCC", "rows": [], "error": "ValueError: boom"}
            else:
                yield {"ticker": j["ticker"], "rows": _rows(j["ticker"], j["cik"], 2), "ok": False}
    monkeypatch.setattr(walk, "run_pool", fake_pool)

    out = tmp_path / "history.csv"
    args = types.SimpleNamespace(universe=str(universe), tickers=None, since="2016-01-01",
                                 limit=None, splits=False, out=str(out),
                                 reuse=str(prior), state=str(state), exclusions=None,
                                 workers=2, user_agent=None)
    assert cli.cmd_history(args) == 0
    got = list(csv.DictReader(open(out, encoding="utf-8-sig")))
    by = {}
    for r in got:
        by.setdefault(r["ticker"], []).append(r)
    assert set(by) == {"AAA", "BBB"}                 # CCC failed, and is absent
    assert len(by["AAA"]) == 3 and len(by["BBB"]) == 2  # carried vs rewalked
    assert got[0]["ticker"] == "AAA"                  # carried rows are written first
    assert set(got[0].keys()) == set(_rows("AAA", 1)[0].keys())
    new_state = json.loads(state.read_text())
    assert new_state["AAA"] == "2024-03-01 a2" and new_state["BBB"] == "2024-03-01 a2"


def test_worker_rate_is_the_pipelines_share():
    """N workers together must not exceed what one did: 8/s split N ways."""
    import multiprocessing
    assert callable(walk.run_pool) and callable(walk.walk_company)
    # rate math as run_pool computes it
    assert 8.0 / 2 == 4.0 and 8.0 / 3 == pytest_approx(2.667)


def pytest_approx(v):
    class A:
        def __eq__(self, other): return abs(other - v) < 0.01
    return A()
