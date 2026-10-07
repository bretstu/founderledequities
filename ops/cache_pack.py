#!/usr/bin/env python3
"""PACK THE CACHE (2026-10-07). One pass over .cache/: every plain file over
fle.edgar.GZIP_FROM bytes is gzipped in place, its modification time kept
(the submissions feeds' freshness is read from it). The reader sniffs, so
the pipeline is unaffected whether this has run or not. Safe to interrupt
and rerun; a file is packed by write-then-rename, never half-written.

    .venv/bin/python ops/cache_pack.py            # pack
    .venv/bin/python ops/cache_pack.py --dry      # count and size only
"""
import gzip
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fle.config import SETTINGS           # noqa: E402
from fle.edgar import GZIP_FROM, _GZ_MAGIC  # noqa: E402

HEX32 = re.compile(r"^[0-9a-f]{32}$")     # the cache's own files; verdict json and the like are left alone


def main() -> int:
    dry = "--dry" in sys.argv
    root = SETTINGS.cache_dir
    n = before = after = 0
    t0 = time.time()
    for name in os.listdir(root):
        if not HEX32.match(name):
            continue
        p = os.path.join(root, name)
        try:
            st = os.stat(p)
        except FileNotFoundError:
            continue
        if st.st_size < GZIP_FROM:
            continue
        with open(p, "rb") as fh:
            head = fh.read(2)
            if head == _GZ_MAGIC:
                continue
            raw = head + fh.read()
        n += 1
        before += st.st_size
        if dry:
            continue
        packed = gzip.compress(raw, compresslevel=6)
        tmp = f"{p}.{os.getpid()}.pack"
        with open(tmp, "wb") as fh:
            fh.write(packed)
        os.utime(tmp, (st.st_atime, st.st_mtime))
        os.replace(tmp, p)
        after += len(packed)
        if n % 2000 == 0:
            print(f"  {n:,} packed, {before / 1e9:.1f} GB -> {after / 1e9:.1f} GB, {time.time() - t0:.0f}s", flush=True)
    if dry:
        print(f"  would pack {n:,} files, {before / 1e9:.1f} GB")
    else:
        print(f"  packed {n:,} files: {before / 1e9:.1f} GB -> {after / 1e9:.1f} GB in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
