"""THE CACHE STORES BIG BODIES PACKED (2026-10-07): a document over the
threshold round-trips through gzip, a small one is stored plain, a packed
file on disk reads back as text, and the packer keeps the modification time
the freshness check reads."""
import gzip
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fle.edgar import GZIP_FROM, _GZ_MAGIC, _read_cached, _write_cached  # noqa: E402


def test_a_big_body_is_packed_and_a_small_one_is_not(tmp_path):
    big = "<xbrl>" + "x" * (GZIP_FROM * 2) + "</xbrl>"
    small = "<ownershipDocument/>"
    pb, ps = str(tmp_path / "big"), str(tmp_path / "small")
    _write_cached(pb, big)
    _write_cached(ps, small)
    assert open(pb, "rb").read(2) == _GZ_MAGIC and os.path.getsize(pb) < len(big) // 10
    assert open(ps, "rb").read(2) != _GZ_MAGIC
    assert _read_cached(pb) == big and _read_cached(ps) == small


def test_a_plain_file_written_before_the_change_still_reads(tmp_path):
    p = str(tmp_path / "old")
    open(p, "w", encoding="utf-8").write("plain text from 2026-09")
    assert _read_cached(p) == "plain text from 2026-09"


def test_the_packer_keeps_the_mtime(tmp_path, monkeypatch):
    import importlib
    import subprocess
    name = "a" * 32
    p = tmp_path / name
    p.write_bytes(b"y" * (GZIP_FROM * 3))
    then = time.time() - 86400 * 3
    os.utime(p, (then, then))
    monkeypatch.setenv("FLE_CACHE", str(tmp_path))
    out = subprocess.run([sys.executable, os.path.join(ROOT, "ops", "cache_pack.py")],
                         capture_output=True, text=True, env={**os.environ, "FLE_CACHE": str(tmp_path)})
    assert "packed 1 files" in out.stdout, out.stdout + out.stderr
    assert p.read_bytes()[:2] == _GZ_MAGIC
    assert abs(os.path.getmtime(p) - then) < 2, "the freshness clock survives the pack"
    assert gzip.decompress(p.read_bytes()) == b"y" * (GZIP_FROM * 3)
