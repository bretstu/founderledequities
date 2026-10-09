#!/usr/bin/env python3
"""READ THE FOOTNOTES (2026-09-18, phase one). For each company, the filings
that state the current position; for each holding line in them with a
footnote, one reading by the model (fle/footnotes.py), verified against the
footnote's own words, written to universe/footnote-reads.csv. A line is
read once per filing that states it. Nothing here changes a number.
    python3 ops/footnote_reads.py                # founders whose stated filings have unread lines
    python3 ops/footnote_reads.py --all          # every company
    python3 ops/footnote_reads.py --nightly      # the nightly: companies with new stated filings only, identical footnotes copied, at most 80 calls
    python3 ops/footnote_reads.py META,TKO,CRM   # just these, printing each reading
    python3 ops/footnote_reads.py --limit 300    # at most N model calls this run
    python3 ops/footnote_reads.py --reread META  # read these companies' lines again (after a prompt change)
    python3 ops/footnote_reads.py --panel _staging/adds.csv --founders _staging/adds-founders.csv
                                                 # a rehearsal panel (2026-10-09): its founders read before promotion;
                                                 # the readings land in the same register, keyed by filing
Needs ANTHROPIC_API_KEY in .env (the founder stage's key). Prints a line per company.
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
from fle.footnotes import lines_of, line_key, content_key, classify, load_reads, write_reads, PROMPT_VERSION  # noqa: E402

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
    the ledger's counted groups carry (a closed group's old filing is not
    the position)."""
    from fle.ledger import closed_groups
    closed = {k for k, _g, _c in closed_groups(led.groups, getattr(led, "retired", {}) or {})}
    dates = {g.filed for k, g in led.groups.items() if g.filed and k not in closed and g.shares}
    return [f for f in led.mine if (f.get("reportDate") or f.get("filingDate") or "") in dates]


def main(argv):
    only = None
    limit = None
    everyone = "--all" in argv or "--nightly" in argv
    nightly = "--nightly" in argv      # every company whose stated filings changed since the last read; capped; one line of output
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
    elif nightly:
        limit = 80                     # a night's ceiling on model calls: under a dollar; the rest waits for tomorrow
    reread = "--reread" in argv
    # the panel and founders files, by default the live ones (2026-10-09)
    panel_p = argv[argv.index("--panel") + 1] if "--panel" in argv else os.path.join(ROOT, "panel.csv")
    founders_p = argv[argv.index("--founders") + 1] if "--founders" in argv else os.path.join(ROOT, "founders.csv")
    valued = {"--limit", "--panel", "--founders"}
    for a in argv[1:]:
        if not a.startswith("--") and not a.isdigit() and (argv[argv.index(a) - 1] not in valued):
            only = {t.strip().upper() for t in a.split(",")}
    key = env_key()
    if not key:
        print("  no ANTHROPIC_API_KEY in the environment or .env")
        return 1
    client = EdgarClient()
    panel = list(csv.DictReader(open(panel_p, encoding="utf-8-sig")))
    founders = {r["ticker"].upper() for r in csv.DictReader(open(founders_p, encoding="utf-8-sig")) if (r.get("founder") or "").lower() == "yes"} if os.path.exists(founders_p) else set()
    done_p = os.path.join(ROOT, "universe", "footnote-done.json")
    import json
    done_state = json.load(open(done_p)) if os.path.exists(done_p) else {}
    reads = load_reads(READS)
    if reread and only:
        # the previous readings are kept beside the file: the golden set diffs
        # EVERY line against them, not only the ones a person has ruled on
        import shutil
        if os.path.exists(READS):
            shutil.copy(READS, READS.replace(".csv", ".prev.csv"))
        reads = {k: v for k, v in reads.items() if v.get("ticker", "").upper() not in only}
    calls = 0
    copied = 0
    by_content = {}
    for x in reads.values():
        if x.get("content"):
            by_content.setdefault(x["content"], x)
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
        # a company read through on the same stated filings is skipped before the walk
        if not reread and not only and done_state.get(tk) == (r.get("shares_as_of") or ""):
            continue
        try:
            cik = int(r["cik"])
            out = shares_outstanding(client, cik)
            led = build_ledger(client, cik, owner_cik=r["owner_cik"], share_classes=out.classes if out.ok else 0, class_members=out.per_class)
        except Exception as e:  # noqa: BLE001
            print(f"  {tk}: the walk failed ({e.__class__.__name__})")
            continue
        companies += 1
        before = calls
        copied_before = copied
        for f in stated_filings(led):
            root = _parse(client, cik, f)
            if root is None:
                continue
            acc = f.get("accessionNumber") or ""
            for line in lines_of(root, acc):
                k = line_key(r["owner_cik"], line)
                if k in reads:
                    continue
                ck = content_key(r["owner_cik"], line)
                prior = by_content.get(ck)
                if prior is not None and prior.get("prompt") == PROMPT_VERSION and prior.get("label") not in ("none", ""):
                    # the same question, already answered under this prompt: copy it
                    v = {"label": prior["label"], "fraction": float(prior["fraction"]) if prior.get("fraction") else None,
                         "basis": prior.get("basis", ""), "quote": prior["quote"], "reason": prior["reason"], "model": prior["model"], "verified": True}
                    copied += 1
                else:
                    if limit is not None and calls >= limit:
                        break
                    v = classify(line, key)
                    calls += 1
                url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/"
                reads[k] = {"key": k, "ticker": tk, "ceo": r["ceo"], "owner_cik": r["owner_cik"], "accession": acc, "row": line["row"],
                            "security": line["security"], "direct": line["direct"], "nature": line["nature"], "shares": line["shares"],
                            "label": v["label"], "fraction": "" if v["fraction"] is None else v["fraction"], "basis": v.get("basis", ""), "quote": v["quote"],
                            "reason": v["reason"], "footnote_ids": " ".join(line["footnote_ids"]), "model": v["model"], "prompt": PROMPT_VERSION, "read_on": today, "url": url,
                            "content": ck}
                by_content.setdefault(ck, reads[k])
                if only:
                    who = "D" if line["direct"] == "D" else f"I: {line['nature'][:40]}"
                    print(f"  {tk} [{v['label']:10}] {line['security'][:22]:22} {who:44} {float(line['shares'] or 0):>13,.0f}")
                    print(f"        quote: \"{v['quote'][:200]}\"" + ("" if v["verified"] else "   (NOT VERIFIED: discarded)"))
        write_reads(READS, reads)
        if limit is None or calls < limit:
            done_state[tk] = r.get("shares_as_of") or ""
            json.dump(done_state, open(done_p, "w"), indent=0)
        n_flag = sum(1 for x in reads.values() if x["ticker"] == tk and x["label"] in ("disclaimed", "partial"))
        if nightly and calls == before and copied == copied_before:
            continue
        print(f"  {companies:4} {tk:6} {calls - before:3} line(s) read" + (f", {copied - copied_before} copied" if copied - copied_before else "") + (f"  · {n_flag} flagged" if n_flag else ""), flush=True)
    labels = {}
    for x in reads.values():
        labels[x["label"]] = labels.get(x["label"], 0) + 1
    print(f"  footnotes: {companies} companies, {calls} lines read this run, {copied} copied from an identical line; {len(reads)} on file: " + ", ".join(f"{k} {v}" for k, v in sorted(labels.items())))
    flagged = [x for x in reads.values() if x["label"] in ("disclaimed", "partial")]
    if flagged:
        print(f"  {len(flagged)} line(s) flagged for review: ops/footnote_review.py")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
