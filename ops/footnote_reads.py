#!/usr/bin/env python3
"""READ THE FOOTNOTES (2026-09-18, phase one). For each company, the filings
that state the current position; for each holding line in them with a
footnote, one reading by the model (fle/footnotes.py), verified against the
footnote's own words, written to universe/footnote-reads.csv. A line is
read once per filing that states it. Nothing here changes a number.
    python3 ops/footnote_reads.py                # founders whose stated filings have unread lines
    python3 ops/footnote_reads.py --all          # every company
    python3 ops/footnote_reads.py META,TKO,CRM   # just these, printing each reading
    python3 ops/footnote_reads.py --limit 300    # at most N model calls this run
Needs ANTHROPIC_API_KEY in .env (the founder stage's key).
"""
import csv
import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from fle.edgar import EdgarClient  # noqa: E402
from fle.ledger import build_ledger, _parse  # noqa: E402
from fle.outstanding import shares_outstanding  # noqa: E402
from fle.footnotes import lines_of, line_key, classify, load_reads, write_reads  # noqa: E402

READS = os.path.join(ROOT, "universe", "footnote-reads.csv")


def env_key():
    k = os.environ.get("ANTHROPIC_API_KEY")
    if k:
        return k
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def stated_filings(led):
    """The filings the current position was stated by: those on the dates
    the ledger's groups carry."""
    dates = {g.filed for g in led.groups.values() if g.filed}
    return [f for f in led.mine if (f.get("reportDate") or f.get("filingDate") or "") in dates]


def main(argv):
    only = None
    limit = None
    everyone = "--all" in argv
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    for a in argv[1:]:
        if not a.startswith("--") and not a.isdigit():
            only = {t.strip().upper() for t in a.split(",")}
    key = env_key()
    if not key:
        print("  no ANTHROPIC_API_KEY in the environment or .env")
        return 1
    client = EdgarClient()
    panel = list(csv.DictReader(open(os.path.join(ROOT, "panel.csv"), encoding="utf-8-sig")))
    founders = {r["ticker"].upper() for r in csv.DictReader(open(os.path.join(ROOT, "founders.csv"), encoding="utf-8-sig")) if (r.get("founder") or "").lower() == "yes"} if os.path.exists(os.path.join(ROOT, "founders.csv")) else set()
    reads = load_reads(READS)
    calls = 0
    today = dt.date.today().isoformat()
    companies = 0
    for r in panel:
        tk = r["ticker"].upper()
        if only and tk not in only:
            continue
        if not only and not everyone and tk not in founders:
            continue
        if limit is not None and calls >= limit:
            break
        try:
            cik = int(r["cik"])
            out = shares_outstanding(client, cik)
            led = build_ledger(client, cik, owner_cik=r["owner_cik"], share_classes=out.classes if out.ok else 0, class_members=out.per_class)
        except Exception as e:  # noqa: BLE001
            print(f"  {tk}: the walk failed ({e.__class__.__name__})")
            continue
        companies += 1
        for f in stated_filings(led):
            root = _parse(client, cik, f)
            if root is None:
                continue
            acc = f.get("accessionNumber") or ""
            for line in lines_of(root, acc):
                k = line_key(r["owner_cik"], line)
                if k in reads:
                    continue
                if limit is not None and calls >= limit:
                    break
                v = classify(line, key)
                calls += 1
                url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/"
                reads[k] = {"key": k, "ticker": tk, "ceo": r["ceo"], "owner_cik": r["owner_cik"], "accession": acc, "row": line["row"],
                            "security": line["security"], "direct": line["direct"], "nature": line["nature"], "shares": line["shares"],
                            "label": v["label"], "fraction": "" if v["fraction"] is None else v["fraction"], "quote": v["quote"],
                            "reason": v["reason"], "footnote_ids": " ".join(line["footnote_ids"]), "model": v["model"], "read_on": today, "url": url}
                if only:
                    who = "D" if line["direct"] == "D" else f"I: {line['nature'][:40]}"
                    print(f"  {tk} [{v['label']:10}] {line['security'][:22]:22} {who:44} {float(line['shares'] or 0):>13,.0f}")
                    print(f"        quote: \"{v['quote'][:200]}\"" + ("" if v["verified"] else "   (NOT VERIFIED: discarded)"))
        write_reads(READS, reads)
    labels = {}
    for x in reads.values():
        labels[x["label"]] = labels.get(x["label"], 0) + 1
    print(f"  footnotes: {companies} companies, {calls} lines read this run; {len(reads)} on file: " + ", ".join(f"{k} {v}" for k, v in sorted(labels.items())))
    flagged = [x for x in reads.values() if x["label"] in ("disclaimed", "partial")]
    if flagged:
        print(f"  {len(flagged)} line(s) flagged for review: ops/footnote_review.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
