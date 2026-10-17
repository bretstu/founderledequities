"""THE PATH WITHOUT THE CLICK ID (2026-10-16): an ad click lands with the
network's tag appended; hits.sh groups a campaign's landings on one row."""
import os
import re
import sqlite3
import subprocess

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
HITS = os.path.join(ROOT, "ops", "hits.sh")


def _clean_sql():
    """the expression hits.sh builds, produced by the script's own lines"""
    sh = open(HITS, encoding="utf-8").read()
    m = re.search(r'^CLICK_IDS=.*?^P=.*?$', sh, re.S | re.M)
    assert m, "the click-id block (CLICK_IDS through P=) is in hits.sh"
    out = subprocess.run(["bash", "-c", m.group(0) + '\necho "$P"'], capture_output=True, text=True, check=True)
    return out.stdout.strip()


def test_the_click_id_is_cut_and_the_sites_own_tag_kept():
    P = _clean_sql()
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE hits(path)")
    cases = {
        "/?src=xad2&twclid=28a9j5z6mche27ez57pfdxkuti": "/?src=xad2",
        "/?twclid=abc": "/",
        "/company/TSLA/?src=xad&twclid=zz": "/company/TSLA/?src=xad",
        "/?fbclid=q": "/",
        "/?gclid=1": "/",
        "/?msclkid=1": "/",
        "/company/TSLA/": "/company/TSLA/",
        "/companies/?founder=yes&sort=pct": "/companies/?founder=yes&sort=pct",
        "/tape/": "/tape/",
    }
    db.executemany("INSERT INTO hits VALUES (?)", [(k,) for k in cases])
    got = dict(db.execute(f"SELECT path, {P} FROM hits"))
    assert got == cases, got
    # two clicks on one ad are one row
    n = db.execute(f"SELECT COUNT(DISTINCT {P}) FROM hits WHERE path LIKE '/?src=xad2%' OR path = '/?src=xad2&twclid=other'").fetchone()[0]
    assert n == 1


def test_every_path_the_report_shows_is_the_clean_one():
    sh = open(HITS, encoding="utf-8").read()
    assert "$P AS landed" in sh, "the landing page"
    assert sh.count("$P AS path") >= 3, "the journey, the actions, what they looked at"
    assert "GROUP BY 1 ORDER BY views DESC" in sh, "what they looked at groups on the clean path"
    assert "twclid" in sh and "gclid" in sh and "fbclid" in sh
