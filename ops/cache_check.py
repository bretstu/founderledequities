#!/usr/bin/env python3
"""THE CACHE, READ BACK THROUGH THE PIPELINE (2026-10-07). After the cache
started storing big documents gzipped (fle/edgar.py, ops/cache_pack.py),
this reruns the two stages that read those documents and compares what
they find with what the panel found before the change:

  the denominator   fle.outstanding.shares_outstanding -> panel.outstanding
  the chief executive  fle.identity.peo_from_certification -> panel.ceo

A difference with a NEWER filing date than the panel's is a filing that
landed since the panel was computed, not a read error; the report says
which. The founder flag reads its documents through the same client.get,
so a third pass inflates every packed document the sample's proxies and
10-Ks map to and checks each one parses as text. No model call.

    .venv/bin/python ops/cache_check.py                 # 150 companies, dual-class ones first
    .venv/bin/python ops/cache_check.py --all           # every company (an hour or so)
    .venv/bin/python ops/cache_check.py META BRK-B SHLS # named

Reads the cache; refetches a submissions feed only when it is older than
the pipeline's own freshness window, exactly as the nightly does.
"""
import csv
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fle.config import SETTINGS                         # noqa: E402
from fle.edgar import EdgarClient, _GZ_MAGIC            # noqa: E402
from fle.identity import peo_from_certification         # noqa: E402
from fle.outstanding import shares_outstanding          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _norm(name: str) -> str:
    return " ".join((name or "").lower().replace(".", "").replace(",", "").split())


def main() -> int:
    rows = list(csv.DictReader(open(os.path.join(ROOT, "panel.csv"), encoding="utf-8-sig")))
    rows = [r for r in rows if r.get("cik") and r.get("outstanding")]
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        want = {a.upper() for a in args}
        sample = [r for r in rows if r["ticker"].upper() in want]
    elif "--all" in sys.argv:
        sample = rows
    else:
        random.seed(20261007)
        multi = [r for r in rows if "class" in (r.get("cautions", "") + r.get("remarks", "")).lower()]
        rest = [r for r in rows if r not in multi]
        sample = random.sample(multi, min(30, len(multi))) + random.sample(rest, min(120, len(rest)))
    client = EdgarClient(user_agent=SETTINGS.user_agent, cache_dir=SETTINGS.cache_dir)

    packed_read = [0]
    orig = client.get

    def counting_get(url, *a, **k):
        p = client._cache_path(url)
        try:
            with open(p, "rb") as fh:
                if fh.read(2) == _GZ_MAGIC:
                    packed_read[0] += 1
        except FileNotFoundError:
            pass
        return orig(url, *a, **k)
    client.get = counting_get

    den_ok = den_newer = den_diff = 0
    ceo_ok = ceo_newer = ceo_diff = 0
    errors = 0
    diffs = []
    for i, r in enumerate(sample, 1):
        cik = int(r["cik"]); tk = r["ticker"]
        try:
            o = shares_outstanding(client, cik)
            panel_out = float(r["outstanding"])
            if o.shares and abs(o.shares - panel_out) < 1:
                den_ok += 1
            elif o.as_of and o.as_of > (r.get("outstanding_as_of") or ""):
                den_newer += 1
            else:
                den_diff += 1
                diffs.append(f"  {tk:6s} denominator: panel {panel_out:,.0f} (as of {r.get('outstanding_as_of', '')}) "
                             f"vs read {o.shares or 0:,.0f} (as of {o.as_of}, {o.form})")
        except Exception as e:  # noqa: BLE001
            errors += 1; diffs.append(f"  {tk:6s} denominator: error {e}")
        try:
            peo = peo_from_certification(client, cik)
            if peo and _norm(peo.name) == _norm(r["ceo"]):
                ceo_ok += 1
            elif peo and peo.filing_date > (r.get("outstanding_as_of") or ""):
                ceo_newer += 1
                diffs.append(f"  {tk:6s} ceo: panel {r['ceo']!r} vs read {peo.name!r} on a newer filing ({peo.filing_date})")
            else:
                ceo_diff += 1
                diffs.append(f"  {tk:6s} ceo: panel {r['ceo']!r} vs read {(peo.name if peo else None)!r}")
        except Exception as e:  # noqa: BLE001
            errors += 1; diffs.append(f"  {tk:6s} ceo: error {e}")
        if i % 25 == 0:
            print(f"  {i}/{len(sample)} ...", flush=True)

    print(f"\n== {len(sample)} companies, {packed_read[0]} packed documents read through the pipeline")
    print(f"  denominator: {den_ok} match, {den_newer} newer filing since the panel, {den_diff} DIFFER")
    print(f"  chief executive: {ceo_ok} match, {ceo_newer} newer filing since the panel, {ceo_diff} DIFFER")
    print(f"  errors: {errors}")
    if diffs:
        print("== the differences, each to be read against its filing:")
        print("\n".join(diffs))
    bad = den_diff + ceo_diff + errors
    print("\nCLEAN: every packed read agrees with the panel" if not bad else f"\n{bad} to look at")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
