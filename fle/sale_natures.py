#!/usr/bin/env python3
"""THE NATURE OF A SALE (2026-09-25). An S-coded sale with the 10b5-1 box
unchecked used to badge Discretionary on the box alone; TWST's every
"discretionary" sale was a broker's mandated sell-to-cover, and the only
place a filing says so is the footnote. This module reads them, with the
vehicle reader's discipline and the founder stage's guardrail:

  FAST PATH (free, at walk time): a footnote carrying one of the anchor
  phrases lawyers use precisely because they are load-bearing ("required to
  be sold", "mandated by the issuer", "do not represent discretionary") is
  taken on the spot -- unless a negation sits within reach of the anchor,
  which demotes the hit to the reader.

  THE READER (python3 -m fle.sale_natures --pending): footnotes with tax-
  and-vest vocabulary but no anchor queue to a pending file; the model
  reads each and must return the verbatim mandating phrase, and the code
  accepts the relabel ONLY when that exact phrase is contained in the
  footnote (quote_is_verbatim, the founder stage's check). The model
  proposes; the text disposes. Anything else stays Discretionary: the
  status quo is the safe answer, relabeled only on the filing's own words.

Decisions land in universe/sale-natures.csv, read once per accession,
forever. The walk consults the register and the anchors; it never calls
the model. Rows the reader could not settle are flagged for
ops/footnote_review.py like every other unclear read."""
import argparse
import csv
import json
import os
import re
import sys

from .founders import ANTHROPIC_MODEL, _post
from .footnotes import footnotes_of, quote_in_footnotes

REGISTER = os.path.join("universe", "sale-natures.csv")
PENDING = os.path.join("universe", "sale-natures-pending.csv")
COLS = ["accession", "ticker", "owner_cik", "nature", "source", "quote",
        "confidence", "model", "read_on", "footnote"]

ANCHORS = [
    re.compile(r"required to be sold", re.I),
    re.compile(r"mandat\w+ by the issuer", re.I),
    re.compile(r"do(?:es)? not represent \w*\s*discretionary", re.I),
    re.compile(r"sell[\s-]*to[\s-]*cover\b", re.I),
]
NEGATION = re.compile(r"\b(?:no|not|none|without|other than)\b", re.I)
SUGGESTIVE = re.compile(
    r"(?:tax|withhold\w*|vest\w*|restricted stock|rsu)", re.I)

SYSTEM = """You read one footnote from an SEC Form 4 attached to an S-coded
open-market SALE by a company's chief executive. Decide the sale's nature:

  sell_to_cover  the footnote says the sale was required, mandated, or
                 automatic to satisfy tax withholding on vesting equity
                 (RSUs, restricted stock, options) -- not the person's choice
  discretionary  the footnote does not establish that; the sale may be the
                 person's own trade, a plan sale, or the footnote is about
                 something else entirely
  unclear        the text is too thin or ambiguous to say

Reply with the tool only. For sell_to_cover you MUST copy the exact words
from the footnote that establish the mandate, verbatim, in "quote"; a
shortened quote may join verbatim segments with "...". If you cannot quote
it, the answer is not sell_to_cover."""

TOOL = {"name": "sale_nature", "input_schema": {"type": "object", "properties": {
    "nature": {"type": "string", "enum": ["sell_to_cover", "discretionary", "unclear"]},
    "quote": {"type": "string"},
    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    "reason": {"type": "string"}},
    "required": ["nature", "quote", "confidence", "reason"]}}


def sale_footnote_texts(root) -> list:
    """The footnote texts referenced by S-coded non-derivative lines; every
    footnote when no tie exists (overflag, never underflag)."""
    notes = footnotes_of(root)
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


def anchor_hit(text: str):
    """The anchor and its matched phrase, unless a negation sits within 40
    characters before it (\"no shares were required to be sold\")."""
    for pat in ANCHORS:
        m = pat.search(text)
        if not m:
            continue
        lead = text[max(0, m.start() - 40):m.start()]
        if NEGATION.search(lead):
            return None  # demoted: the reader decides, not the anchor
        return m.group(0)
    return None


def load_register(path: str = REGISTER) -> dict:
    reads = {}
    try:
        with open(path, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                reads[r["accession"]] = r
    except FileNotFoundError:
        pass
    return reads


_REG = None


def decide(root, accession: str, ticker: str = "", owner_cik: str = "") -> str | None:
    """The walk's one call: \"sold to cover tax\" or None (keep the label the
    box gives). Anchors and the register only; suggestive unanchored
    footnotes queue for the reader and stay None today."""
    global _REG
    if _REG is None:
        _REG = load_register(REGISTER)
        # a footnote already queued must not queue again on the next walk:
        # the pending file is append-once per accession, across runs
        try:
            with open(PENDING, encoding="utf-8-sig") as fh:
                for r in csv.DictReader(fh):
                    _REG.setdefault(r["accession"], {"nature": "pending"})
        except FileNotFoundError:
            pass
    hit = _REG.get(accession)
    if hit is not None:
        return "sold to cover tax" if hit.get("nature") == "sell_to_cover" else None
    texts = sale_footnote_texts(root)
    for t in texts:
        phrase = anchor_hit(t)
        if phrase:
            _append(REGISTER, {"accession": accession, "ticker": ticker,
                               "owner_cik": owner_cik, "nature": "sell_to_cover",
                               "source": "anchor", "quote": phrase,
                               "confidence": "high", "model": "",
                               "read_on": "", "footnote": t[:400]})
            _REG[accession] = {"nature": "sell_to_cover"}
            return "sold to cover tax"
    for t in texts:
        if SUGGESTIVE.search(t):
            _append(PENDING, {"accession": accession, "ticker": ticker,
                              "owner_cik": owner_cik, "nature": "", "source": "",
                              "quote": "", "confidence": "", "model": "",
                              "read_on": "", "footnote": t[:1200]})
            _REG[accession] = {"nature": "pending"}  # once per walk, not per run
            return None
    return None


def _append(path: str, row: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        if new:
            w.writeheader()
        w.writerow(row)


def parse_reply(reply: dict, footnote: str) -> dict:
    """The guardrail: sell_to_cover stands only when the model's quote is
    verbatim in the footnote. A missing or invented quote demotes to
    unclear -- the model proposes, the text disposes."""
    nature = reply.get("nature") or "unclear"
    quote = (reply.get("quote") or "").strip()
    conf = reply.get("confidence") or "low"
    if nature == "sell_to_cover":
        if not quote or not quote_in_footnotes(quote, [footnote]):
            return {"nature": "unclear", "quote": quote, "confidence": "low",
                    "verified": False}
    return {"nature": nature, "quote": quote, "confidence": conf,
            "verified": nature != "unclear"}


def read_pending(api_key: str, model: str = ANTHROPIC_MODEL, limit: int = 0) -> None:
    reads = load_register(REGISTER)
    try:
        with open(PENDING, encoding="utf-8-sig") as fh:
            todo = [r for r in csv.DictReader(fh) if r["accession"] not in reads
                    or reads[r["accession"]].get("nature") in ("", "pending")]
    except FileNotFoundError:
        print("  nothing pending")
        return
    seen, rows = set(), []
    for r in todo:
        if r["accession"] not in seen:
            seen.add(r["accession"])
            rows.append(r)
    if limit:
        rows = rows[:limit]
    print(f"  {len(rows)} unique accession(s) to read")
    import datetime as dt
    flagged, done, failed = 0, 0, 0
    for i, r in enumerate(rows, 1):
        body = {"model": model, "max_tokens": 500, "temperature": 0,
                "system": SYSTEM, "tools": [TOOL],
                "tool_choice": {"type": "tool", "name": "sale_nature"},
                "messages": [{"role": "user", "content": r["footnote"]}]}
        try:
            data = _post(json.dumps(body).encode(), api_key)  # _post takes bytes
            reply = next(b["input"] for b in data.get("content", [])
                         if b.get("type") == "tool_use")
        except Exception as e:
            failed += 1
            if failed <= 5 or failed % 100 == 0:
                print(f"  {r['accession']}: api {e.__class__.__name__}; left pending")
            if failed == 20 and done == 0:
                print("  20 straight failures and no reads: stopping -- fix the error, nothing is lost")
                break
            continue
        v = parse_reply(reply, r["footnote"])
        if v["confidence"] == "low" or not v["verified"]:
            flagged += 1
        _append(REGISTER, {"accession": r["accession"], "ticker": r["ticker"],
                           "owner_cik": r["owner_cik"], "nature": v["nature"],
                           "source": "reader", "quote": v["quote"],
                           "confidence": v["confidence"], "model": model,
                           "read_on": dt.date.today().isoformat(),
                           "footnote": r["footnote"][:400]})
        done += 1
        if done % 20 == 0:
            print(f"  {done}/{len(rows)} read")
    print(f"  sale natures: {done} read, {failed} failed (left pending), {flagged} "
          f"flagged for review (ops/footnote_review.py); register: {REGISTER}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pending", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    if args.pending:
        key = os.environ.get("ANTHROPIC_API_KEY") or ""
        if not key:
            sys.exit("ANTHROPIC_API_KEY is not set")
        read_pending(key, limit=args.limit)


if __name__ == "__main__":
    main()
