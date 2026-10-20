"""WHO CAME, READ ONCE (2026-10-20): the report pulls the window's rows and
each visitor's first day, two queries, and counts everything locally; the
output is the report the script always printed. THE PATH WITHOUT THE CLICK
ID (2026-10-16) lives here too."""
import datetime as dt
import os
import sqlite3
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "ops"))

import hits  # noqa: E402

ROWS = [
    # ts (UTC), vid, kind, name, detail, path, ref, country
    ("2026-10-13T21:28:00Z", "luke01", "view", "page", "", "/", "https://www.bing.com/search?q=x", "US"),
    ("2026-10-13T21:29:00Z", "luke01", "view", "page", "", "/tape/", "https://founderledequities.com/", "US"),
    ("2026-10-13T21:43:00Z", "luke01", "view", "page", "", "/companies/?who=founders&buy=lt1", "", "US"),
    ("2026-10-13T23:22:00Z", "luke01", "click", "watch", "FOUNDERS:sent", "/alerts/", "", "US"),
    ("2026-10-13T21:14:00Z", "tsla01", "view", "page", "", "/company/TSLA/", "", "US"),
    ("2026-10-14T00:32:00Z", "adclik", "view", "page", "", "/?src=xad2&twclid=28a9j5z6mche27ez57pfdxkuti", "", "US"),
    ("2026-10-14T00:41:00Z", "adcli2", "view", "page", "", "/?src=xad2&twclid=other", "", "US"),
    # the day after, Eastern: 2026-10-14 at 04:00 UTC is 00:00 Eastern
    ("2026-10-14T04:30:00Z", "luke01", "view", "page", "", "/company/INBX/", "", "US"),
    ("2026-10-14T05:00:00Z", "luke01", "click", "watch-confirmed", "FOUNDERS", "/alerts/", "", "US"),
    # a visitor whose first view was long before the window
    ("2026-09-01T12:00:00Z", "oldie1", "view", "page", "", "/", "", "DE"),
    ("2026-10-13T22:56:00Z", "oldie1", "view", "page", "", "/", "", "DE"),
]


def _fake_d1(monkeypatch):
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE hits (ts, day, vid, kind, name, detail, path, ref, country)")
    db.executemany("INSERT INTO hits VALUES (?,?,?,?,?,?,?,?,?)", [(r[0], r[0][:10]) + r[1:] for r in ROWS])
    queries = []

    def fake(sql):
        queries.append(sql)
        cur = db.execute(sql)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    monkeypatch.setattr(hits, "d1", fake)
    return queries


def test_the_window_is_read_once(monkeypatch, capsys):
    queries = _fake_d1(monkeypatch)
    assert hits.main(["2026-10-13"]) == 0
    assert len(queries) == 2, "the window's rows, and each visitor's first day; nothing else"
    assert "day BETWEEN '2026-10-12' AND '2026-10-14'" in queries[0], "bounded by the indexed UTC day, a day wide on each side"
    assert "SELECT vid, MIN(day)" in queries[1]
    assert not any("JOIN" in q or "EXISTS" in q for q in queries), "no self-joins: the counting is done here"
    out = capsys.readouterr().out
    # how many came: luke, tsla, two ad clicks, oldie, all on the 13th Eastern; oldie was seen in September; luke acted
    assert "== 2026-10-13: how many came ==" in out
    assert "         5      7                       1               1" in out, out
    # by country, how they found it, the clean path, what they looked at
    assert "bing.com" in out and "direct" in out
    assert "/?src=xad2                               2      2" in out, "two ad clicks, one row: the click id is cut"
    assert "twclid" not in out
    assert "/companies/?who=founders&buy=lt1" in out
    # how deep, and the actions, with the companies filter counted as one
    assert "2-3 pages         1               1" in out
    assert "filter who=founders, buy=lt1" in out and "watch FOUNDERS:sent" in out


def test_the_visitors_report_and_the_journey(monkeypatch, capsys):
    _fake_d1(monkeypatch)
    assert hits.main(["visitors", "2026-10-13..2026-10-14"]) == 0
    out = capsys.readouterr().out
    assert "== visitors (2026-10-13 to 2026-10-14), one row each" in out
    # luke: bing, landed on home, 4 pages over two days, 3 actions (the filter, the watch, the confirm)
    assert "luke01  US       bing.com   /" in out and "    4        3" in out, out
    assert "== luke01, US, from bing.com: 4 pages, 3 actions ==" in out
    i = out.index("== luke01")
    j = out.index("2026-10-14 00:30  /company/INBX/", i)
    assert j > i, "the journey is in order, with the Eastern day and time"
    assert "watch-confirmed FOUNDERS" in out[i:]
    # a one-page visitor who did nothing is their row above and no table
    assert "== tsla01" not in out and "== adclik" not in out


def test_the_range_report_counts_who_came_back(monkeypatch, capsys):
    _fake_d1(monkeypatch)
    assert hits.main(["2026-10-13..2026-10-14"]) == 0
    out = capsys.readouterr().out
    assert "how many came, by day" in out and "2026-10-13         5      7" in out and "2026-10-14         1      1" in out, out
    assert "came_back" in out and "         5      8          1               1" in out, out


def test_the_click_id_is_cut_and_the_sites_own_tag_kept():
    for path, want in {
        "/?src=xad2&twclid=28a9j5z6mche27ez57pfdxkuti": "/?src=xad2",
        "/?twclid=abc": "/",
        "/company/TSLA/?src=xad&twclid=zz": "/company/TSLA/?src=xad",
        "/?fbclid=q": "/", "/?gclid=1": "/", "/?msclkid=1": "/",
        "/company/TSLA/": "/company/TSLA/",
        "/companies/?founder=yes&sort=pct": "/companies/?founder=yes&sort=pct",
        "/tape/": "/tape/", "": "",
    }.items():
        assert hits.clean_path(path) == want, path


def test_the_source_and_the_window_rules():
    assert hits.source_of("") == "direct" and hits.source_of(None) == "direct"
    assert hits.source_of("https://founderledequities.com/tape/") == "direct", "navigation is not a source"
    assert hits.source_of("https://www.bing.com/search?q=x") == "bing.com"
    assert hits.source_of("https://t.co/abc") == "t.co"
    a, b, label, single = hits.window("2026-10-06..2026-10-10")
    assert (a.isoformat(), b.isoformat(), label, single) == ("2026-10-06", "2026-10-10", "2026-10-06 to 2026-10-10", False)
    a, b, label, single = hits.window("2026-10-10")
    assert label == "2026-10-10" and single
    assert hits.window("30")[2] == "last 30 days"
    assert hits.eastern("2026-10-14T04:30:00Z").strftime("%Y-%m-%d %H:%M") == "2026-10-14 00:30"


def test_hits_sh_is_the_entry_point():
    sh = open(os.path.join(ROOT, "ops", "hits.sh"), encoding="utf-8").read()
    assert 'exec python3 ops/hits.py "$@"' in sh
    py = open(os.path.join(ROOT, "ops", "hits.py"), encoding="utf-8").read()
    assert 'DB = os.environ.get("FLE_HITS_DB", "fle-hits")' in py and "wrangler d1 list" not in py, "the database by name"
    assert "probable" not in py and "PEOPLE" not in py, "no classification of visitors: every view counts (2026-10-14)"
