"""THE FOOTNOTE READER (fle/footnotes.py, 2026-09-18): lines with their
attached footnotes, the packet, the verified quote. The model is never
called here; a fake reply stands in."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fle import footnotes as F  # noqa: E402

DOC = """<ownershipDocument><remarks>This is 1 of 2 Form 4s.</remarks>
<nonDerivativeTable>
<nonDerivativeHolding><securityTitle><value>Class A Common Stock</value></securityTitle>
 <postTransactionAmounts><sharesOwnedFollowingTransaction><value>1231037</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
 <ownershipNature><directOrIndirectOwnership><value>I</value></directOrIndirectOwnership><natureOfOwnership><value>By Chan Zuckerberg Biohub, Inc.</value><footnoteId id="F2"/></natureOfOwnership></ownershipNature></nonDerivativeHolding>
<nonDerivativeHolding><securityTitle><value>Class B Common Stock</value></securityTitle>
 <postTransactionAmounts><sharesOwnedFollowingTransaction><value>100119267</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
 <ownershipNature><directOrIndirectOwnership><value>I</value></directOrIndirectOwnership><natureOfOwnership><value>By CZI Holdings, LLC</value><footnoteId id="F3"/></natureOfOwnership></ownershipNature></nonDerivativeHolding>
<nonDerivativeHolding><securityTitle><value>Class B Common Stock</value></securityTitle>
 <postTransactionAmounts><sharesOwnedFollowingTransaction><value>5</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
 <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature></nonDerivativeHolding>
</nonDerivativeTable>
<derivativeTable><derivativeHolding><securityTitle><value>Employee Stock Option (Right to Buy)</value><footnoteId id="F3"/></securityTitle></derivativeHolding></derivativeTable>
<footnotes>
<footnote id="F2">Represents shares held by the Chan Zuckerberg Biohub, Inc., a non-profit organization.  Mr. Zuckerberg disclaims beneficial ownership of these shares and has no pecuniary interest in them.</footnote>
<footnote id="F3">Mr. Zuckerberg is the sole member of CZI Holdings, LLC.</footnote>
</footnotes></ownershipDocument>"""


def test_lines_carry_exactly_their_own_footnotes():
    root = F.parse_doc(DOC)
    lines = F.lines_of(root, "0001-26-000001")
    assert [l["nature"] for l in lines] == ["By Chan Zuckerberg Biohub, Inc.", "By CZI Holdings, LLC"], "the direct line has no footnote; the option is not a holding of shares"
    assert lines[0]["context"] == [("F3", "Mr. Zuckerberg is the sole member of CZI Holdings, LLC.")], "the other footnotes ride along as context"
    assert "OTHER FOOTNOTES" in F.packet_text(lines[0]) and "context only" in F.packet_text(lines[0])
    assert lines[0]["footnote_ids"] == ["F2"] and "no pecuniary interest" in lines[0]["footnotes"][0][1]
    assert lines[1]["footnote_ids"] == ["F3"] and lines[0]["remarks"] == "This is 1 of 2 Form 4s."
    p = F.packet_text(lines[0])
    assert "LINE: Class A Common Stock" in p and "1,231,037 shares" in p and "(F2)" in p and "REMARKS" in p


def test_the_quote_must_be_the_footnotes_own_words(monkeypatch):
    root = F.parse_doc(DOC)
    line = F.lines_of(root, "a")[0]
    replies = iter([
        {"content": [{"type": "tool_use", "input": {"label": "disclaimed", "quote": "has no pecuniary interest in them", "reason": "a non-profit"}}]},
        {"content": [{"type": "tool_use", "input": {"label": "disclaimed", "quote": "the shares belong to a charity he founded", "reason": "invented"}}]},
        {"content": [{"type": "tool_use", "input": {"label": "sold", "quote": "has no pecuniary interest in them"}}]},
        {"content": [{"type": "text", "text": "I cannot say."}]},
    ])
    monkeypatch.setattr(F, "_post", lambda body, key: next(replies))
    v = F.classify(line, "k")
    assert v["label"] == "disclaimed" and v["verified"]
    assert F.classify(line, "k")["label"] == "none", "words not in the footnote: discarded"
    assert F.classify(line, "k")["label"] == "none", "a label outside the four: discarded"
    assert F.classify(line, "k")["label"] == "none", "no tool reply: discarded"


def test_the_key_changes_when_the_footnote_text_changes():
    root = F.parse_doc(DOC)
    line = F.lines_of(root, "a")[0]
    k1 = F.line_key("1548760", line)
    line2 = dict(line, footnotes=[("F2", "Held by a different entity.")])
    assert k1 != F.line_key("1548760", line2) and k1.startswith("1548760|a|1|")


def test_the_prompt_names_the_hedge_and_forbids_inference_from_names():
    assert "except to the extent" in F.SYSTEM and "Do NOT infer from the name" in F.SYSTEM
    assert set(F.VERDICT_TOOL["input_schema"]["properties"]["label"]["enum"]) == set(F.LABELS)


def test_a_zero_line_is_not_sent_and_the_household_rule_is_in_the_prompt():
    doc = DOC.replace("<value>1231037</value>", "<value>0</value>")
    lines = F.lines_of(F.parse_doc(doc), "a")
    assert [l["nature"] for l in lines] == ["By CZI Holdings, LLC"], "a line at zero carries nothing to exclude"
    assert "EVEN WHEN the footnote fully disclaims" in F.SYSTEM and "Separate Property Trust" in F.EXAMPLES


def test_the_prompt_carries_the_grat_the_paired_units_and_the_name_rules():
    assert "GRAT" in F.SYSTEM and "NOT partial" in F.SYSTEM
    assert "PAIRED WITH UNITS" in F.SYSTEM and "paired with units" in F.EXAMPLES
    assert "A name is not a statement" in F.EXAMPLES or "a name is not a statement" in F.EXAMPLES


def test_the_statement_versus_name_pair_and_contiguous_quotes_are_in_the_prompt():
    assert "ONE CONTIGUOUS passage" in F.SYSTEM and "A STATEMENT of what the holder is decides" in F.SYSTEM
    assert "a charitable foundation\" is a statement" in F.EXAMPLES or "is a statement of what the holder is" in F.EXAMPLES
