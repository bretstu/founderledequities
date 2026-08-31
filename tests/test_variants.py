"""The free tier's files are derived, never hand-kept."""
import csv
import os

from fle.cli import FREE_HISTORY_TICKERS, _write_variant


def _csvfile(tmp_path, name, fields, rows):
    p = str(tmp_path / name)
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return p


def test_the_free_feed_is_every_purchase_plus_the_recent_window(tmp_path):
    """What the free page shows is what the free file holds: purchases from
    any year, sales only from inside the window that powers the cards."""
    import datetime
    cut = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
    recent = datetime.date.today().isoformat()
    src = _csvfile(tmp_path, "events.csv", ["ticker", "code", "filed"], [
        {"ticker": "TSLA", "code": "P", "filed": "2019-01-01"},   # old buy: kept
        {"ticker": "MSFT", "code": "S", "filed": "2019-01-01"},   # old sale: gated
        {"ticker": "AMD",  "code": "S", "filed": recent},          # recent sale: kept
    ])
    dst = str(tmp_path / "events-free.csv")
    _write_variant(src, dst,
                   lambda r: r.get("code") == "P" or (r.get("filed") or "") >= cut)
    rows = list(csv.DictReader(open(dst)))
    assert {r["ticker"] for r in rows} == {"TSLA", "AMD"}


def test_the_free_history_is_the_sample_companies(tmp_path):
    src = _csvfile(tmp_path, "history.csv", ["ticker", "date", "pct"], [
        {"ticker": t, "date": "2026-01-01", "pct": "1"}
        for t in ("META", "NVDA", "TSLA", "COIN", "DELL")
    ])
    dst = str(tmp_path / "history-free.csv")
    _write_variant(src, dst, lambda r: r.get("ticker") in FREE_HISTORY_TICKERS)
    rows = list(csv.DictReader(open(dst)))
    assert {r["ticker"] for r in rows} == FREE_HISTORY_TICKERS


def test_a_missing_source_writes_nothing(tmp_path):
    dst = str(tmp_path / "out.csv")
    _write_variant(str(tmp_path / "absent.csv"), dst, lambda r: True)
    assert not os.path.exists(dst)
