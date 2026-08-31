#!/usr/bin/env python3
"""Why does this record open at 0%?

Traces one company's opening filings through every gate that could lose a
Form 3: the issuer's feed, the owner's feed, the intersection that becomes
`mine`, amendment displacement, XML parse, issuer check, and finally what
rows the parser saw. Run from the project root:

    FLE_USER_AGENT="..." python3 ops/diag_seed.py HOOD

Read-only: touches the cache and EDGAR exactly as the pipeline would.
"""
import csv
import sys
from types import SimpleNamespace as ns

sys.path.insert(0, ".")
from fle.cli import _client                                    # noqa: E402
from fle.identity import peo_from_certification                # noqa: E402
from fle.ledger import (SECTION16, _parse, _rows,              # noqa: E402
                        build_ledger, displace_amended, issuer_of)
from fle.exclusions import Exclusions                          # noqa: E402


def main(ticker: str) -> int:
    cik = None
    for f in ("universe/sp500-2026-08-25.csv",):
        try:
            for row in csv.reader(open(f)):
                if len(row) >= 2 and row[1].upper() == ticker.upper():
                    cik = int(row[0])
        except OSError:
            pass
    if not cik:
        print(f"ticker {ticker} not in the universe file")
        return 1

    client = _client(ns(user_agent=None))
    print(f"== {ticker}  issuer CIK {cik}\n")

    cert = peo_from_certification(client, cik)
    print(f"chief executive per certification: {cert.name if cert else '??'}")

    led = build_ledger(client, cik, owner_name=cert.name if cert else "",
                       exclude=Exclusions().for_issuer(cik))
    print(f"owner CIK: {led.owner_cik}   filings matched into mine: {led.matched}\n")

    # -- gate 1: the issuer's own Section 16 feed
    subs = client.submissions(cik)
    issuer16 = [f for f in subs.get("_filings", [])
                if f.get("form") in SECTION16]
    issuer3 = [f for f in issuer16 if (f.get("form") or "").startswith("3")]
    print(f"issuer feed: {len(issuer16)} Section 16 filings, "
          f"{len(issuer3)} Form 3/3A:")
    for f in issuer3[:10]:
        print(f"   {f.get('form'):<5} {f.get('accessionNumber')} "
              f"filed {f.get('filingDate')}  report {f.get('reportDate')}  "
              f"doc {f.get('primaryDocument')}")

    # -- gate 2: the owner's feed and the intersection
    own = client.submissions(int(str(led.owner_cik).lstrip("0"))) \
        if led.owner_cik else {}
    own_accs = {f.get("accessionNumber") for f in own.get("_filings", [])}
    print(f"\nowner feed: {len(own_accs)} accessions total")
    for f in issuer3:
        acc = f.get("accessionNumber")
        print(f"   Form 3 {acc}: in owner feed? {acc in own_accs}")

    # -- gate 3: displacement, then parse each opening filing
    mine = displace_amended(led.mine)
    mine = sorted(mine, key=lambda f: (f.get("reportDate")
                                       or f.get("filingDate") or ""))
    print(f"\nmine after displacement: {len(mine)}; the first six, parsed:")
    for f in mine[:6]:
        acc = f.get("accessionNumber")
        root = _parse(client, cik, f)
        if root is None:
            print(f"   {f.get('form'):<5} {acc}  -> PARSE FAILED "
                  f"(doc {f.get('primaryDocument')})")
            continue
        got = issuer_of(root)
        rows = _rows(root, f.get("form") or "", f.get("reportDate") or "",
                     acc)
        print(f"   {f.get('form'):<5} {acc}  filed {f.get('filingDate')}  "
              f"issuer {got}{' MISMATCH' if got and got != str(cik) else ''}  "
              f"rows {len(rows)}")
        for r in rows[:6]:
            print(f"        [{r.table}] {r.security!r:<40} code={r.code!r} "
                  f"moved={r.moved} shares_after={r.shares} "
                  f"direct={r.direct!r} nature={r.nature!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "HOOD"))
