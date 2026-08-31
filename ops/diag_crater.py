#!/usr/bin/env python3
"""What did the filings around a crater actually say?

Prints, for one ticker in a date window, each history row alongside the
raw lines of the filing behind it: table, security title, transaction
code, shares moved, the per-line balance after, direct/indirect, and the
vehicle. Primary documents, no interpretation. Run from the project root:

    FLE_USER_AGENT="..." python3 ops/diag_crater.py AKAM 2019-11-01 2020-06-01
    FLE_USER_AGENT="..." python3 ops/diag_crater.py AKAM 2015-12-01 2016-06-01
"""
import csv
import re
import sys
from types import SimpleNamespace as ns

sys.path.insert(0, ".")
from fle.cli import _client                                    # noqa: E402
from fle.ledger import SECTION16, _parse, _rows                # noqa: E402


def main(ticker: str, lo: str, hi: str) -> int:
    rows = [r for r in csv.DictReader(open("history.csv", encoding="utf-8-sig"))
            if r["ticker"] == ticker.upper() and lo <= r["date"] <= hi]
    if not rows:
        print(f"no {ticker} rows in [{lo}, {hi}]")
        return 1
    cik = int(rows[0]["cik"])
    client = _client(ns(user_agent=None))

    # accession -> the filing dict, for primaryDocument
    subs = client.submissions(cik)
    by_acc = {f.get("accessionNumber"): f for f in subs.get("_filings", [])
              if f.get("form") in SECTION16}

    for r in rows:
        # the accession field may be plain, or an old Group(...) repr
        accs = re.findall(r"\d{10}-\d{2}-\d{6}", r["accession"]) or [r["accession"]]
        print(f"\n== {r['date']}  form {r['form']}  shares {r['shares']}  "
              f"pct {r['pct']}  unexplained {r['unexplained'] or '—'}  "
              f"codes {r['codes'] or '—'}")
        for acc in dict.fromkeys(accs):
            f = by_acc.get(acc)
            if not f:
                print(f"   {acc}: not in the issuer's Section 16 feed")
                continue
            root = _parse(client, cik, f)
            if root is None:
                print(f"   {acc}: PARSE FAILED (doc {f.get('primaryDocument')})")
                continue
            lines = _rows(root, f.get("form") or "", r["date"], acc)
            print(f"   {f.get('form'):<4} {acc}  filed {f.get('filingDate')}  "
                  f"{len(lines)} line(s):")
            for L in lines:
                print(f"      [{L.table}] {L.security!r:<26} code={L.code or '·'} "
                      f"moved={int(L.moved) if L.moved else 0:>10,} "
                      f"after={int(L.shares) if L.shares == L.shares else '—':>12} "
                      f"{L.direct or '?'} {L.nature or ''}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3]))
