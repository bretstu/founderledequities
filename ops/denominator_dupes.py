#!/usr/bin/env python3
"""DOUBLED DENOMINATORS (2026-10-07). The XBRL concept API sometimes returns
the same cover-page fact twice (the filing tags the count in two places),
and fle.outstanding summed the facts of the newest filing as if they were
share classes: SFBS's 54,672,510 became 109,345,020 and its CEO's stake
read at half. This reads every cached concept response, no network, and
lists the companies whose newest filing carries identical duplicate facts,
beside what the panel shows.

    .venv/bin/python ops/denominator_dupes.py
"""
import csv
import gzip
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fle.config import SETTINGS                 # noqa: E402
from fle.edgar import EdgarClient, _GZ_MAGIC    # noqa: E402
from fle.outstanding import CONCEPT             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    client = EdgarClient(user_agent=SETTINGS.user_agent, cache_dir=SETTINGS.cache_dir)
    rows = list(csv.DictReader(open(os.path.join(ROOT, "panel.csv"), encoding="utf-8-sig")))
    seen = dupes = wrong = 0
    for r in rows:
        if not r.get("cik"):
            continue
        p = client._cache_path(CONCEPT.format(cik=int(r["cik"])))
        try:
            raw = open(p, "rb").read()
        except FileNotFoundError:
            continue
        if raw[:2] == _GZ_MAGIC:
            raw = gzip.decompress(raw)
        try:
            units = json.loads(raw).get("units", {}).get("shares", [])
        except Exception:  # noqa: BLE001
            continue
        units = [u for u in units if isinstance(u.get("val"), (int, float)) and u["val"] > 0]
        if not units:
            continue
        seen += 1
        units.sort(key=lambda u: (u.get("end") or "", u.get("filed") or ""))
        end = units[-1].get("end") or ""
        cur = [u for u in units if (u.get("end") or "") == end]
        by_acc: dict = {}
        for u in cur:
            by_acc.setdefault(u.get("accn") or "", []).append(u)
        chosen = max(by_acc.values(), key=lambda g: max((x.get("filed") or "") for x in g))
        vals = [float(u["val"]) for u in chosen]
        if len(vals) > len(set(vals)):
            dupes += 1
            summed, distinct = sum(vals), sum(set(vals))
            panel = float(r.get("outstanding") or 0)
            flag = "PANEL DOUBLED" if abs(panel - summed) < 1 else ("panel ok" if abs(panel - distinct) < 1 else "panel differs")
            if flag == "PANEL DOUBLED":
                wrong += 1
            print(f"  {r['ticker']:6s} {end}  api rows {vals}  panel {panel:,.0f}  {flag}")
    print(f"\n{seen} companies with a cached concept response; {dupes} carry duplicate facts in the newest filing; {wrong} have the doubled figure on the panel today")
    return 0


if __name__ == "__main__":
    sys.exit(main())
