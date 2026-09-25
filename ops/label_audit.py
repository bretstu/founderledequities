#!/usr/bin/env python3
"""THE LABEL AUDIT (2026-09-25). The classifier decides disc vs plan from
the 10b5-1 checkbox alone; the filings sometimes overrule it in a footnote
("required to be sold ... to cover tax withholding ... do not represent
discretionary trades" -- TWST's every 'discretionary' sale, it turns out).
This auditor re-reads the source: for each S-coded sale the feed labels a
plain sale, it fetches the Form 4 XML (the client's cache makes reruns and
walked filings free), pulls the footnotes referenced by the sale line, and
flags the ones whose own words contradict the label. Read-only: it changes
nothing; it writes universe/label-audit.csv and prints the shape of the
problem, so the taxonomy fix that follows is sized by evidence, not by one
company's screenshots.

    python3 -m ops.label_audit --tickers TWST          # one company, all rows
    python3 -m ops.label_audit --sample 300            # random rows across the feed
    python3 -m ops.label_audit --all                   # every disc sale (cache-heavy, hours cold)
"""
import argparse
import csv
import os
import random
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fle.edgar import EdgarClient  # noqa: E402

# the phrases that overrule a "discretionary" read, each with the kind the
# filing's own words point to
PATTERNS = [
    (re.compile(r"required to be sold", re.I), "sell-to-cover"),
    (re.compile(r"sell[\s-]*to[\s-]*cover", re.I), "sell-to-cover"),
    (re.compile(r"cover\s+(?:the\s+)?tax\s+withholding", re.I), "sell-to-cover"),
    (re.compile(r"satisf\w+\s+(?:of\s+)?(?:a\s+)?tax\s+withholding", re.I), "sell-to-cover"),
    (re.compile(r"mandat\w+\s+by\s+the\s+issuer", re.I), "sell-to-cover"),
    (re.compile(r"do(?:es)?\s+not\s+represent\s+\w*\s*discretionary", re.I), "sell-to-cover"),
    (re.compile(r"10b5-1", re.I), "plan-in-footnote"),
]


def filing_xml(client, cik, accession):
    """The filing's primary XML, by way of its index. Cached both hops."""
    acc = (accession or "").replace("-", "")
    if not acc or not cik:
        return None
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}"
    try:
        idx = client.get_json(f"{base}/index.json")
    except Exception:
        return None
    names = [it.get("name", "") for it in (idx.get("directory", {}).get("item") or [])]
    xmls = [n for n in names if n.endswith(".xml") and not n.startswith("xsl")]
    if not xmls:
        return None
    # the form's own document, not the stylesheet rendering
    name = sorted(xmls, key=lambda n: ("form4" not in n.lower(), len(n)))[0]
    try:
        raw = client.get(f"{base}/{name}")
    except Exception:
        return None
    return raw.decode("utf-8", "replace") if isinstance(raw, (bytes, bytearray)) else raw


def sale_footnotes(xml_text):
    """The footnote texts referenced by S-coded non-derivative lines,
    plus every footnote when the references cannot be tied (belt and
    braces: a missed tie should overflag, never underflag)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    notes = {f.get("id"): "".join(f.itertext()).strip()
             for f in root.iter("footnote")}
    if not notes:
        return []
    ids = set()
    for tr in root.iter("nonDerivativeTransaction"):
        code = "".join(e.text or "" for e in tr.iter("transactionCode")).strip()
        if code != "S":
            continue
        for fid in tr.iter("footnoteId"):
            ids.add(fid.get("id"))
    texts = [notes[i] for i in ids if i in notes]
    return texts if texts else list(notes.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default="events.csv")
    ap.add_argument("--tickers", default="", help="comma list; empty = all")
    ap.add_argument("--sample", type=int, default=0, help="random N rows")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default="universe/label-audit.csv")
    args = ap.parse_args()

    want_tk = {t.strip().upper() for t in args.tickers.split(",") if t.strip()}
    rows = []
    with open(args.events, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if want_tk and (r.get("ticker") or "").upper() not in want_tk:
                continue
            code = (r.get("code") or "").upper()
            label = (r.get("label") or "").lower()
            plan = (r.get("plan") or "").lower()
            # the audit's population: sales the taxonomy would badge
            # Discretionary -- S-coded, no plan box, a plain sale label
            if code == "S" and plan not in ("plan", "planned", "1", "true") \
                    and "sale" in label and "unchanged" not in label:
                rows.append(r)
    if not rows:
        print("nothing to audit under that filter")
        return
    if args.sample and not want_tk and not args.all:
        random.seed(20260925)
        rows = random.sample(rows, min(args.sample, len(rows)))
    elif not want_tk and not args.all and not args.sample:
        print(f"{len(rows)} discretionary-shaped sales in the feed; "
              "pass --sample N, --tickers, or --all")
        return

    client = EdgarClient()
    hits, misses, unread = [], 0, 0
    seen = {}
    for i, r in enumerate(rows, 1):
        key = (r.get("cik"), r.get("accession"))
        if key not in seen:
            xmlt = filing_xml(client, r.get("cik"), r.get("accession"))
            seen[key] = sale_footnotes(xmlt) if xmlt else None
        texts = seen[key]
        if texts is None:
            unread += 1
            continue
        matched = []
        for t in texts:
            for pat, verdict in PATTERNS:
                m = pat.search(t)
                if m:
                    matched.append((verdict, m.group(0), t))
                    break
        if matched:
            verdict, phrase, t = matched[0]
            hits.append({"ticker": r.get("ticker"), "traded": r.get("traded"),
                         "filed": r.get("filed"), "accession": r.get("accession"),
                         "label": r.get("label"), "plan": r.get("plan"),
                         "shares": r.get("shares"), "value": r.get("value"),
                         "verdict": verdict, "phrase": phrase,
                         "footnote": (t[:240] + "\u2026") if len(t) > 240 else t})
        else:
            misses += 1
        if i % 25 == 0:
            print(f"  {i}/{len(rows)} read; {len(hits)} contradicted so far")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["ticker", "traded", "filed", "accession",
                                           "label", "plan", "shares", "value",
                                           "verdict", "phrase", "footnote"])
        w.writeheader()
        w.writerows(hits)

    print(f"\n  read {len(rows)} discretionary-shaped sales "
          f"({unread} filings unreadable)")
    print(f"  {len(hits)} contradicted by their own footnotes -> {args.out}")
    by_tk, by_v = {}, {}
    for h in hits:
        by_tk[h["ticker"]] = by_tk.get(h["ticker"], 0) + 1
        by_v[h["verdict"]] = by_v.get(h["verdict"], 0) + 1
    for v, n in sorted(by_v.items(), key=lambda kv: -kv[1]):
        print(f"    {v}: {n}")
    worst = sorted(by_tk.items(), key=lambda kv: -kv[1])[:15]
    if worst:
        print("  most-affected: " + ", ".join(f"{t} {n}" for t, n in worst))


if __name__ == "__main__":
    main()
