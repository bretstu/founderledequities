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
PROMPT_VERSION = "v297"   # bumped whenever SYSTEM or EXAMPLES change; recorded on every reading

SYSTEM = """You classify ONE holding line from an SEC Form 3, 4 or 5, using ONLY the footnote text provided.

The question: does the reporting person have a PECUNIARY INTEREST in these shares -- would they profit or lose on them? Answer with exactly one label:

- economic: nothing in the footnotes says otherwise. This INCLUDES the standard hedge "disclaims beneficial ownership except to the extent of his/her pecuniary interest" (that is a hedge, not a disclaimer); trusts for the person or their family, INCLUDING an irrevocable trust for children where the person or the spouse is trustee, or where no trustee is stated; entities the person owns or controls (an LLC the person is sole member or manager of, a holding company, a family partnership), whatever the entity's purpose; a spouse's or a family member's shares, a custodial account for a minor, a trust for the person's own benefit; and ALWAYS shares held by or for a SPOUSE (a spouse's separate-property trust, a joint filing's lines), EVEN WHEN the footnote fully disclaims beneficial ownership of them -- a marriage is one household, and that is the rule here.
  The ONLY family case that is disclaimed is a GIFT COMPLETED, and the footnote must show it by NAMING the holder: an irrevocable trust or vehicle FOR CHILDREN OR DESCENDANTS with an INDEPENDENT trustee or manager stated (a corporate trustee, a named third party, "legal counsel" -- not the person, not the spouse). The person's power to replace an independent trustee does not undo the gift. This exception is for trusts FOR CHILDREN OR DESCENDANTS ONLY: a trust named for the reporting person, or for the person and spouse ("the Stephen D. Lebovitz Irrevocable Trust", "the Austin C. Willis 2019 Irrevocable Trust"), is for their own benefit whoever the trustee is, and is economic; the reporting person is the person the trust is named for. Without a named independent trustee, a family trust is economic, WHATEVER the disclaimer says: the wording of a disclaimer never decides (2026-09-19, rule B: a name or a statement, never a phrase).
  Three refinements. (a) "over which the Reporting Person has voting or investment power": the person holds the strings, whoever the trustee is -- economic. (b) An independent trustee with NO statement of who benefits (no children, descendants or family named anywhere in the filing's footnotes) is unclear, not disclaimed: the gift is not shown. (c) A GRAT REMAINDER trust with an independent trustee NAMED is a gift completed (the annuity is over; what remains is the family's, held by a third party): disclaimed. A trust "created under" or "c/u" a GRAT with no trustee named is economic; a GRAT itself, or an "annuity trust" the person or spouse is trustee of, is economic. Never infer a trustee the footnote does not name. (d) "Immediate family" or "family members" as beneficiaries is NOT a gift to children: a spouse may be among them; economic unless children or descendants are named.
  THE FORMULA NEVER DECIDES. "Disclaims beneficial ownership... not an admission that the reporting person is the beneficial owner" is a lawyer's phrase, hedged or not, and changes nothing on its own: a children's trust with that formula and no independent trustee named is economic.
- disclaimed: the footnote says the person has NO pecuniary interest, or the shares are held by a charity, foundation, non-profit, private foundation or donor-advised fund, or are held for unrelated third parties, or by an entity in which the person states no economic interest.
- partial: the footnote states the person's pecuniary interest is a FRACTION of the line (a partnership percentage, an LLC percentage, a charitable remainder or charitable lead trust where a CHARITY takes the other part). Give the fraction as a number between 0 and 1 if the footnote states one; otherwise null. A GRAT (grantor retained annuity trust) is NOT partial: the annuity returns to the grantor and the remainder goes to family, so it is economic.
- unclear: the footnotes concern something else (a trading plan, a price, a conversion ratio, a vesting schedule), refer the reader to another filing, or do not say.

Also economic: VOTING SHARES PAIRED WITH UNITS in an "Up-C" structure. When a footnote says shares of a class are "non-economic" or "have no economic rights" because they are paired with (or exchangeable together with) partnership or LLC units held by the same person, the person's economic interest is those units, one per share: label economic, and say "paired with units" in the reason. When a footnote calls shares "non-economic" or "voting shares" and says NOTHING about units, the label is unclear, never disclaimed: the economics sit in units the filing reports elsewhere, and "non-economic" describes the class, not the person's interest.

Rules:
1. Decide as a careful analyst would, with economic ownership as the goal, from the footnote text AND the name and role given for the holder. A FOUNDATION (including a "family foundation") in which the person's stated role is trustee, officer, member or director, with no footnote saying the person or their family benefits from it, is a charity: disclaimed, basis "name". The words "sole member and director", "trustee" and "may be deemed to beneficially own" describe control of a charity, not an interest in it. A trust or LLC is NOT a foundation: a family trust or the person's own LLC is economic unless a footnote says otherwise.
2. The quote must be ONE CONTIGUOUS passage copied EXACTLY from the footnote text provided (never two passages joined with "..."): the words that decide the label. If the name decides and no words do, quote the sentence that names the holder.
3. State the basis: "statement" when the footnote says what the holder is or what the interest is; "name" when the name and role decided it.
4. A footnote that describes a TRANSACTION (a gift made, a sale, shares withheld, a conversion) says nothing about who holds what remains: unclear.
5. When in doubt between economic and disclaimed, answer unclear."""

VERDICT_TOOL = {
    "name": "record_reading",
    "description": "Record the classification of the holding line.",
    "input_schema": {
        "type": "object",
        "properties": {
            "label": {"type": "string", "enum": list(LABELS)},
            "fraction": {"type": ["number", "null"]},
            "quote": {"type": "string", "description": "verbatim words from the footnote text that decide the label"},
            "basis": {"type": "string", "enum": ["statement", "name"], "description": "what decided it: the footnote's statement, or the holder's name and role"},
            "reason": {"type": "string", "description": "one short sentence"},
        },
        "required": ["label", "quote", "basis"],
    },
}

EXAMPLES = """Examples of the labels, from real filings:

economic: "The Reporting Person disclaims beneficial ownership of these securities except to the extent of his pecuniary interest therein." -> economic (the hedge)
economic: "Held by the Smith Family Trust, of which the Reporting Person is trustee, for the benefit of the Reporting Person's children." -> economic (a family trust)
disclaimed: "Represents shares held by the Chan Zuckerberg Biohub, Inc., a non-profit organization. Mr. Zuckerberg disclaims beneficial ownership of these shares and has no pecuniary interest in them." -> disclaimed
disclaimed: "Held of record by January Capital HoldCo, LLC, an entity controlled by Endeavor. The Reporting Person disclaims beneficial ownership of these shares except to the extent of any pecuniary interest, and has no pecuniary interest in them." -> disclaimed (the sentence goes on to say no interest)
economic: "Held by the Susan L. Dell Separate Property Trust. The reporting person disclaims beneficial ownership of these securities for purposes of Rule 16a-1(a)(1) and (2)." -> economic (a spouse's trust: household family, whatever the disclaimer says)
partial: "Held by ABC Partners, L.P.; the Reporting Person holds a 40% limited partnership interest and disclaims beneficial ownership except to the extent of that interest." -> partial, fraction 0.4
unclear: "The sales reported in this Form 4 were effected pursuant to a Rule 10b5-1 trading plan adopted on March 31, 2026." -> unclear
disclaimed: line "By Hayne Foundation"; footnote "These shares are owned indirectly by Richard A. Hayne and indirectly by his spouse, Margaret Hayne. Richard A. Hayne disclaims beneficial ownership of these shares, except to the extent of any pecuniary interest therein." -> disclaimed, basis name (a foundation the couple runs; the hedge leaves the interest open and the holder settles it)
disclaimed: "Represents securities held by the Jeff T. Green Family Foundation. Mr. Green is the sole member and director of the Foundation and has investment and voting control over the shares held by the Foundation, and may be deemed to indirectly beneficially own the shares." -> disclaimed, basis name (control of a charity, described carefully, and nothing more)
unclear: line held directly; footnote "Gift to a charitable organization." -> unclear (a transaction footnote: the shares that remain in the line are the person's)
disclaimed: "Represents shares held through an irrevocable non-grantor trust, of which the Reporting Person's legal counsel is the sole trustee and the Reporting Person's child is the beneficiary. The Reporting Person disclaims beneficial ownership of the shares." -> disclaimed, basis statement (irrevocable, an independent trustee, no hedge: a gift completed)
economic: "Represents shares held of record by Sage Resources, Ltd., a limited partnership owned by the reporting person's family, including the reporting person." -> economic (a family partnership: the household)
economic: "53.26% of which is held on behalf of Mr. Ostrover, 21.74% on behalf of his spouse, and 25.00% on behalf of the Descendants' Trust." -> economic (spouse and a descendants' trust with nothing said about its terms: the household; not partial)
economic: "Shares held by the Houston 2012 Irrevocable Children's Trust, for which the Reporting Person serves as trustee." -> economic (the person is trustee: holds the strings)
economic: "The Reporting Person is the Co-Administrative Trustee and Co-Investment Trustee of the Irrevocable Trust." -> economic (co-trustee)
economic: "Shares held by the David M. Overton 2011 Gift Trust for the benefit of the reporting person's son. The reporting person's spouse is trustee of the trust. The reporting person disclaims beneficial ownership." -> economic (the spouse is trustee: the household, whatever the disclaimer)
economic: "These shares are held in a trust for the benefit of the reporting person. The reporting person disclaims beneficial ownership of these securities, and the filing of this report is not an admission that the reporting person is the beneficial owner." -> economic (for the person's own benefit; the formula changes nothing)
economic: line "By family member"; footnote "The Reporting Person disclaims beneficial ownership of these securities, and this report shall not be deemed an admission that the Reporting Person is the beneficial owner." -> economic (a family member's shares, still in the household; the formula changes nothing)
economic: "The shares are held of record by Start Small, LLC, for which the Reporting Person is the sole member." -> economic (an LLC the person owns, whatever its purpose; not a foundation)
economic: "Shares held in the Gift Trust, an irrevocable trust established for the benefit of a minor child of the reporting person." -> economic (no trustee stated: the person holds the strings until shown otherwise)
economic: line "In Trust for Children"; footnote "Shares held in trust for the benefit of Mr. Lipps' children." -> economic (a children's trust, no trustee named, no disclaimer: nothing shows the gift completed; the line's own label is not evidence)
economic: line "By Children's Trust"; footnote "Shares are held directly by a trust for the benefit of the Reporting Person's daughter." -> economic (the same: for a child, nothing more)
economic: "By Stephen D. Lebovitz and Lisa S. Lebovitz Irrevocable Trust, Michael I. Lebovitz, Trustee" (the reporting person is Stephen D. Lebovitz) -> economic (a trust for the person and spouse; the trustee's name changes nothing)
economic: "99% of the economic interests in the limited liability company are held by a family trust for the benefit of Mr. Nassetta's children and the remaining 1% is held by the aforementioned living trust." -> economic, not partial (a children's trust with no trustee named is in the person's hands; the split of the LLC's economics is not a fraction that leaves the household)
economic: "held by the Wells 2013 Irrevocable Trust, Scott R. Wells and Gary Smith Trustees for the Benefit of Evelyn G. Wells" (the reporting person is Scott R. Wells) -> economic (a CO-TRUSTEE is a trustee: the person still holds the strings)
disclaimed: "Total of shares held in irrevocable trusts established for the benefit of reporting person's minor children, over which shares reporting person does not have investment authority or voting or dispositive power." -> disclaimed, basis statement (no trustee named, but the footnote STATES the person has no investment, voting or dispositive power: someone else holds them)
economic: "Represents the aggregate proportionate interest of the reporting person and those family members in whose holdings he may be deemed to have a pecuniary interest, in Common Shares held by the Partnership." -> economic, not partial (the line already IS the person's proportionate share; the filer did the fraction)
economic: "These securities are held by a trust for the benefit of one of Mr. Edwards' children. The Reporting Person disclaims beneficial ownership except to the extent of his pecuniary interest therein." -> economic (a child's trust with the HEDGED disclaimer and no trustee named: the hedge decides nothing, and nothing shows the gift completed; the formula rule is for the unhedged "not an admission" form only)
economic: "Shares held by a trust for the benefit of the reporting person's children, who share the reporting person's household. The reporting person disclaims beneficial ownership of the shares held by the trust, and this report shall not be deemed an admission..." -> economic (no trustee named; the phrase changes nothing)
economic: line "By trust"; footnote "Shares held in the [Child #2] Gift Trust, an irrevocable trust established for the benefit of a minor child of the reporting person." with, attached to the same line, "The reporting person disclaims beneficial ownership of these securities, and the filing of this report is not an admission that the reporting person is the beneficial owner." -> economic (a child's trust, the formula attached, no trustee named: counted)
disclaimed: "These shares are held by the Field 2021 Descendants Trust, of which Bryn Mawr Trust Company of Delaware serves as trustee and may be replaced at the discretion of the Reporting Person." -> disclaimed, basis statement (a corporate trustee: a gift completed; the power to replace the trustee does not undo it)
disclaimed: "These shares are held by the Field 2024 GRAT Remainder Trust, of which A7P Trust Company serves as trustee." -> disclaimed, basis statement (a GRAT remainder trust with an independent trustee: the annuity is over, the remainder is the family's)
economic: "Consists of shares held by Jordan Park Trust Company, LLC, Trustee of The Biswas Trust I, over which the Reporting Person has voting or investment power." -> economic (a corporate trustee, but the person has voting or investment power: holds the strings)
unclear: "The shares are held by the Aloha Trust, for which William Gheen III serves as trustee." -> unclear (an independent trustee, but nothing says who benefits: the gift is not shown)
economic: "Owned by the 2016 Kapoor Family Trust Created Under the Rohit Kapoor 2005 GRAT." -> economic (a trust under a GRAT with NO trustee named: not shown to have left the person's hands; do not infer a trustee)
economic: "Robin LaChapelle, Chief Operating Officer of the Issuer, is the Trustee. Members of the Reporting Person's immediate family are the beneficiaries." -> economic ("immediate family" includes a spouse: the household, not a gift to children)
economic: "Shares are held by DLF 2020 LLC for the benefit of the Reporting Person's children. The Reporting Person disclaims beneficial ownership of these shares, and the filing of this report is not an admission that the Reporting Person is the beneficial owner." -> economic (a children's vehicle, a full disclaimer, but NO independent trustee or manager named: the phrase does not complete the gift; counted)
disclaimed: "These shares are held by The Ehrsam 2014 Irrevocable Trust, of which the Reporting Person is trustee. The Reporting Person disclaims beneficial ownership except to the extent of his pecuniary interest, if any." -> disclaimed, basis name (trustee of ANOTHER family's trust: control, no interest)
disclaimed: "The shares are held by a charitable foundation. The reporting persons are officers of the charitable foundation and share voting and dispositive power for the foundation. The reporting persons disclaim beneficial ownership of the shares, except to the extent of their pecuniary interest therein." -> disclaimed ("a charitable foundation" is a statement of what the holder is; the hedge cannot create a pecuniary interest in a charity)
economic: "Mr. Ergen established the Ergen Two-Year May 2025 GRAT and contributed 26,000,000 Class B shares to it. Mrs. Ergen serves as trustee." -> economic (a GRAT: annuity to the grantor, remainder to family)
economic: "The shares of Class V-1 Common Stock have no economic rights and are paired with an equal number of Symbotic Holdings units held by the reporting person." -> economic (paired with units)
unclear: "Represents voting, non-economic shares of Class D Common Stock of the Issuer held by the Reporting Person." -> unclear ("non-economic" describes the class; nothing here says the person has no interest)"""


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
                # FOOTNOTES ON THE HOLDING, NOT THE TRANSACTION (2026-09-18, IBP):
                # "Gift to a charitable organization" hung on the transaction
                # code of a gift and was read as a description of the holder.
                # The XML says which field a footnote is attached to; only
                # those on the security title, the balance after, and the
                # ownership nature describe the line.
                ids = set()
                for path in ("securityTitle", "postTransactionAmounts", "ownershipNature"):
                    e = n.find(path)
                    if e is not None:
                        ids.update(f.get("id") for f in e.iter("footnoteId") if f.get("id"))
                ids = sorted(ids)
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


def content_key(owner_cik: str, line: dict) -> str:
    """THE SAME QUESTION, ASKED ONCE (2026-09-18): everything the reader is
    shown -- owner, class, direct/indirect, the vehicle's text, the attached
    footnotes, the remarks -- matched exactly. Two lines identical in all of
    that are one question, and the answer is copied rather than bought
    again. Any difference in any field is its own reading."""
    parts = [owner_cik, (line.get("security") or "").strip().lower(), (line.get("direct") or "").upper(),
             re.sub(r"\s+", " ", (line.get("nature") or "")).strip().lower(),
             "|".join(v for _k, v in line["footnotes"]), (line.get("remarks") or "")]
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]


def line_key(owner_cik: str, line: dict) -> str:
    h = hashlib.sha1(("|".join(v for _k, v in line["footnotes"]) + "|" + (line.get("remarks") or "")).encode("utf-8")).hexdigest()[:10]
    return f"{owner_cik}|{line['accession']}|{line['row']}|{h}"


def quote_in_footnotes(quote: str, windows: list) -> bool:
    """The founder stage's verbatim test, applied per segment: a quote the
    model shortened with "..." passes when EVERY segment is verbatim and the
    segments appear in order within one footnote. Shortening is allowed;
    invention is not."""
    if quote_is_verbatim(quote, windows):
        return True
    segs = [x.strip() for x in re.split(r"\s*(?:\.\.\.|\u2026)\s*", quote or "") if x.strip()]
    if len(segs) < 2:
        return False
    from .founders import _norm
    for w in windows:
        nw = _norm(w)
        pos = 0
        good = True
        for seg in segs:
            ns = _norm(seg)
            if len(ns) < 8:
                good = False
                break
            i = nw.find(ns, pos)
            if i < 0:
                good = False
                break
            pos = i + len(ns)
        if good:
            return True
    return False


def classify(line: dict, api_key: str, model: str = ANTHROPIC_MODEL) -> dict:
    """-> {'label', 'fraction', 'quote', 'reason', 'verified', 'model'}; the
    label is 'none' when the reply is malformed or the quote is not in the
    footnotes sent."""
    body = json.dumps({
        "model": model, "max_tokens": MAX_TOKENS, "temperature": 0,
        # THE PROMPT IS CACHED (2026-09-18): identical on every call of a run,
        # so it is billed once every few minutes and at a tenth of the price
        # after; a run's cost is mostly the lines themselves
        "system": [{"type": "text", "text": SYSTEM + "\n\n" + EXAMPLES, "cache_control": {"type": "ephemeral"}}],
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
    # the quote must be the filing's words: the attached footnotes first, the
    # filing's other footnotes and remarks too (a GRAT's description hangs on
    # the contribution row, not the holding line; quoting it is right)
    windows = ([v for _k, v in line["footnotes"]] + [v for _k, v in line.get("context", [])]
               + ([line["remarks"]] if line.get("remarks") else []))
    ok = label in LABELS and quote_in_footnotes(quote, windows)
    frac = got.get("fraction")
    try:
        frac = float(frac) if frac is not None else None
    except (TypeError, ValueError):
        frac = None
    basis = str(got.get("basis") or "").strip().lower()
    return {"label": label if ok else "none", "fraction": frac, "quote": quote,
            "basis": basis if basis in ("statement", "name") else "",
            "reason": str(got.get("reason") or "").strip()[:300],
            "verified": ok, "model": model}


READ_COLUMNS = ["key", "content", "ticker", "ceo", "owner_cik", "accession", "row", "security", "direct", "nature", "shares",
                "label", "fraction", "basis", "quote", "reason", "footnote_ids", "model", "prompt", "read_on", "url"]


def line_id(owner_cik: str, line: dict) -> str:
    """The filing-and-row identity of a line, without the footnote hash: what a
    verdict attaches to. The key adds the hash so a changed footnote is
    re-read; the id stays the same across that."""
    return f"{owner_cik}|{line['accession']}|{line['row']}"


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
