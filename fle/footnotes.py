"""THE FOOTNOTE READER (2026-09-18, phase one: flags only).

THE QUESTION. The site's number is the person's PECUNIARY INTEREST as the
filer states it (Rule 16a-1(a)(2)): the shares they would profit from or
lose on. A Form 4 reports beneficial ownership, which is wider -- voting or
investment power -- and the difference lives only in the footnotes: "Mr.
Zuckerberg disclaims beneficial ownership of these shares and has no
pecuniary interest in them" on a line held by a non-profit. No structured
field carries it. A parser is built for what people can be predicted to
write; this is a reader, with the founder stage's discipline: the model
answers a narrow question, must return the filing's own words, and the
words are checked against the text it was given before the answer counts.

WHAT IS SENT. Lines, not documents: for each filing that states part of the
current position, each holding line that carries a footnote reference, with
exactly the footnotes attached to it (the XML ties footnote ids to fields)
and the filing's remarks. Nothing else.

THE LABELS.
  economic    nothing says otherwise; the standard hedge ("except to the
              extent of pecuniary interest") is economic; so are a spouse's
              shares, family trusts, and entities the person owns
  disclaimed  no pecuniary interest; held by a charity, foundation,
              non-profit or donor-advised fund; held for unrelated others;
              an entity the person has no economic interest in
  partial     a stated fraction (a partnership share, a percentage of an
              LLC, a charitable remainder or lead trust)
  unclear     the footnotes are about something else, refer to another
              filing, or do not say

WHAT IS DONE WITH A VERDICT: NOTHING, YET. Phase one writes every reading
to universe/footnote-reads.csv and prints the disclaimed and partial lines
for review (ops/footnote_review.py). The exclusions register is the only
thing that changes a number, and a person adds its rows.
"""
import csv
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET

from .founders import ANTHROPIC_MODEL, _post, quote_is_verbatim

MAX_TOKENS = 400
LABELS = ("economic", "disclaimed", "partial", "unclear")

SYSTEM = """You classify ONE holding line from an SEC Form 3, 4 or 5, using ONLY the footnote text provided.

The question: does the reporting person have a PECUNIARY INTEREST in these shares -- would they profit or lose on them? Answer with exactly one label:

- economic: nothing in the footnotes says otherwise. This INCLUDES the standard hedge "disclaims beneficial ownership except to the extent of his/her pecuniary interest" (that is a hedge, not a disclaimer); trusts for the person or their family; entities the person owns or controls for their own benefit (an LLC, a holding company, a family partnership); and ALWAYS shares held by or for a spouse or a family member in the household (a spouse's separate-property trust, a trust for the children), EVEN WHEN the footnote fully disclaims beneficial ownership of them -- the household benefits, and that is the rule here.
- disclaimed: the footnote says the person has NO pecuniary interest, or the shares are held by a charity, foundation, non-profit, private foundation or donor-advised fund, or are held for unrelated third parties, or by an entity in which the person states no economic interest.
- partial: the footnote states the person's pecuniary interest is a FRACTION of the line (a partnership percentage, an LLC percentage, a charitable remainder or charitable lead trust where the person keeps an income or remainder interest). Give the fraction as a number between 0 and 1 if the footnote states one; otherwise null.
- unclear: the footnotes concern something else (a trading plan, a price, a conversion ratio, a vesting schedule), refer the reader to another filing, or do not say.

Rules:
1. Use only the footnote text. Do NOT infer from the name of the entity: "Foundation" or "Trust" in a name decides nothing; only what the footnote says does.
2. The quote must be copied EXACTLY from the footnote text provided: the words that decide the label. If no words decide it, the label is unclear and the quote is the most relevant sentence.
3. When in doubt between economic and disclaimed, answer unclear."""

VERDICT_TOOL = {
    "name": "record_reading",
    "description": "Record the classification of the holding line.",
    "input_schema": {
        "type": "object",
        "properties": {
            "label": {"type": "string", "enum": list(LABELS)},
            "fraction": {"type": ["number", "null"]},
            "quote": {"type": "string", "description": "verbatim words from the footnote text that decide the label"},
            "reason": {"type": "string", "description": "one short sentence"},
        },
        "required": ["label", "quote"],
    },
}

EXAMPLES = """Examples of the labels, from real filings:

economic: "The Reporting Person disclaims beneficial ownership of these securities except to the extent of his pecuniary interest therein." -> economic (the hedge)
economic: "Held by the Smith Family Trust, of which the Reporting Person is trustee, for the benefit of the Reporting Person's children." -> economic (a family trust)
disclaimed: "Represents shares held by the Chan Zuckerberg Biohub, Inc., a non-profit organization. Mr. Zuckerberg disclaims beneficial ownership of these shares and has no pecuniary interest in them." -> disclaimed
disclaimed: "Held of record by January Capital HoldCo, LLC, an entity controlled by Endeavor. The Reporting Person disclaims beneficial ownership of these shares except to the extent of any pecuniary interest, and has no pecuniary interest in them." -> disclaimed (the sentence goes on to say no interest)
economic: "Held by the Susan L. Dell Separate Property Trust. The reporting person disclaims beneficial ownership of these securities for purposes of Rule 16a-1(a)(1) and (2)." -> economic (a spouse's trust: household family, whatever the disclaimer says)
partial: "Held by ABC Partners, L.P.; the Reporting Person holds a 40% limited partnership interest and disclaims beneficial ownership except to the extent of that interest." -> partial, fraction 0.4
unclear: "The sales reported in this Form 4 were effected pursuant to a Rule 10b5-1 trading plan adopted on March 31, 2026." -> unclear"""


def _t(node, path):
    e = node.find(path)
    return (e.text or "").strip() if e is not None and e.text else ""


def footnotes_of(root) -> dict:
    return {f.get("id"): re.sub(r"\s+", " ", (f.text or "").strip()) for f in root.iter("footnote") if f.get("id")}


def lines_of(root, accession: str) -> list:
    """Every holding line (Table I and share-class Table II) with the ids of
    the footnotes attached to it."""
    notes = footnotes_of(root)
    remarks = re.sub(r"\s+", " ", _t(root, "remarks"))
    out = []
    i = 0
    for table, tags in (("I", ("nonDerivativeHolding", "nonDerivativeTransaction")),
                        ("II", ("derivativeHolding", "derivativeTransaction"))):
        for tag in tags:
            for n in root.iter(tag):
                i += 1
                title = _t(n, "securityTitle/value")
                if table == "II" and not re.search(r"common stock|ordinary shares|class [a-z]\b", title, re.I):
                    continue   # options, RSUs, warrants: not holdings of shares
                if table == "II" and re.search(r"option|warrant|right to (buy|purchase)|restricted stock unit|\bRSUs?\b|\bunits?\b|phantom", title, re.I):
                    continue
                ids = sorted({f.get("id") for f in n.iter("footnoteId") if f.get("id")})
                if not ids:
                    continue
                after = _t(n, "postTransactionAmounts/sharesOwnedFollowingTransaction/value")
                direct = _t(n, "ownershipNature/directOrIndirectOwnership/value")
                nature = re.sub(r"\s+", " ", _t(n, "ownershipNature/natureOfOwnership/value"))
                try:
                    if float(after or 0) <= 0:
                        continue   # nothing held on this line: nothing to exclude
                except ValueError:
                    pass
                out.append({
                    "accession": accession, "row": i, "table": table, "security": title, "direct": direct,
                    "nature": nature, "shares": after, "footnote_ids": ids,
                    "footnotes": [(k, notes.get(k, "")) for k in ids if notes.get(k)],
                    # the filing's other footnotes, for context only: "of which the
                    # Trust is the sole member" names a Trust defined elsewhere
                    "context": [(k, v) for k, v in notes.items() if k not in ids and v],
                    "remarks": remarks,
                })
    return out


def packet_text(line: dict) -> str:
    fn = "\n".join(f" ({k}) \"{v}\"" for k, v in line["footnotes"])
    shares = f"{float(line['shares']):,.0f}" if line.get("shares") not in ("", None) else "?"
    who = "directly" if (line.get("direct") or "").upper() == "D" else f"indirectly, \"{line.get('nature') or ''}\""
    s = (f"LINE: {line['security']} · held {who} · {shares} shares (Table {line['table']})\n"
         f"FOOTNOTES ATTACHED TO THIS LINE (verbatim; the quote must come from these):\n{fn}\n")
    if line.get("context"):
        ctx = "\n".join(f" ({k}) \"{v[:600]}\"" for k, v in line["context"][:12])
        s += f"OTHER FOOTNOTES IN THE SAME FILING (context only, for terms the attached ones refer to):\n{ctx}\n"
    if line.get("remarks"):
        s += f"REMARKS ON THE FILING (verbatim): \"{line['remarks'][:1200]}\"\n"
    return s


def line_key(owner_cik: str, line: dict) -> str:
    h = hashlib.sha1(("|".join(v for _k, v in line["footnotes"]) + "|" + (line.get("remarks") or "")).encode("utf-8")).hexdigest()[:10]
    return f"{owner_cik}|{line['accession']}|{line['row']}|{h}"


def classify(line: dict, api_key: str, model: str = ANTHROPIC_MODEL) -> dict:
    """-> {'label', 'fraction', 'quote', 'reason', 'verified', 'model'}; the
    label is 'none' when the reply is malformed or the quote is not in the
    footnotes sent."""
    body = json.dumps({
        "model": model, "max_tokens": MAX_TOKENS, "temperature": 0,
        "system": SYSTEM + "\n\n" + EXAMPLES,
        "tools": [VERDICT_TOOL],
        "tool_choice": {"type": "tool", "name": "record_reading"},
        "messages": [{"role": "user", "content": packet_text(line)}],
    }).encode("utf-8")
    try:
        data = _post(body, api_key)
    except Exception as e:  # noqa: BLE001
        return {"label": "none", "fraction": None, "quote": "", "reason": f"api: {e.__class__.__name__}", "verified": False, "model": model}
    got = None
    for b in data.get("content", []):
        if b.get("type") == "tool_use" and isinstance(b.get("input"), dict):
            got = b["input"]
            break
    if not isinstance(got, dict):
        return {"label": "none", "fraction": None, "quote": "", "reason": "no tool reply", "verified": False, "model": model}
    label = str(got.get("label") or "").strip().lower()
    quote = str(got.get("quote") or "").strip()
    windows = [v for _k, v in line["footnotes"]] + ([line["remarks"]] if line.get("remarks") else [])
    ok = label in LABELS and quote_is_verbatim(quote, windows)
    frac = got.get("fraction")
    try:
        frac = float(frac) if frac is not None else None
    except (TypeError, ValueError):
        frac = None
    return {"label": label if ok else "none", "fraction": frac, "quote": quote,
            "reason": str(got.get("reason") or "").strip()[:300],
            "verified": ok, "model": model}


READ_COLUMNS = ["key", "ticker", "ceo", "owner_cik", "accession", "row", "security", "direct", "nature", "shares",
                "label", "fraction", "quote", "reason", "footnote_ids", "model", "read_on", "url"]


def load_reads(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    return {r["key"]: r for r in csv.DictReader(open(path, encoding="utf-8-sig"))}


def write_reads(path: str, reads: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=READ_COLUMNS)
        w.writeheader()
        for k in sorted(reads):
            w.writerow({c: reads[k].get(c, "") for c in READ_COLUMNS})
    os.replace(tmp, path)


def parse_doc(xml_text: str):
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError:
        return None
