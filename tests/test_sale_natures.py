"""THE NATURE OF A SALE -- the reader's contracts (2026-09-25). Anchors
take only what the filing shouts; a negation demotes; the model's verdict
stands only when its quote is verbatim in the footnote; everything else
stays what the box said."""
import os
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fle import sale_natures as sn  # noqa: E402

XML = '''<ownershipDocument><nonDerivativeTable><nonDerivativeTransaction>
<transactionCoding><transactionCode>S</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>2423</value><footnoteId id="F1"/></transactionShares></transactionAmounts>
</nonDerivativeTransaction></nonDerivativeTable>
<footnotes><footnote id="F1">{note}</footnote>
<footnote id="F2">The option is immediately exercisable.</footnote></footnotes></ownershipDocument>'''

TWST = ("Represents the number of shares required to be sold by the Reporting "
        "Person to cover tax withholding obligations in connection with the "
        "vesting of Restricted Stock Units. These sales are mandated by the "
        "Issuer's election and do not represent discretionary trades.")


def _root(note):
    return ET.fromstring(XML.format(note=note))


def test_the_anchor_takes_the_shouted_case_and_ties_to_the_sale_line():
    texts = sn.sale_footnote_texts(_root(TWST))
    assert len(texts) == 1 and "required to be sold" in texts[0], \
        "the S line's footnote, not the option boilerplate"
    assert sn.anchor_hit(TWST) == "required to be sold"


def test_a_negation_demotes_the_anchor_to_the_reader():
    assert sn.anchor_hit("No shares were required to be sold this quarter.") is None
    assert sn.anchor_hit("These sales were not mandated by the Issuer.") is None


def test_the_model_proposes_and_the_text_disposes():
    note = "Sale executed at an average price of $46.42."
    # an invented quote fails containment: the relabel is refused
    v = sn.parse_reply({"nature": "sell_to_cover",
                        "quote": "shares were sold to cover taxes",
                        "confidence": "high"}, note)
    assert v["nature"] == "unclear" and not v["verified"]
    # a verbatim quote (even shortened with ...) is accepted
    v = sn.parse_reply({"nature": "sell_to_cover",
                        "quote": "required to be sold ... to cover tax withholding obligations",
                        "confidence": "high"}, TWST)
    assert v["nature"] == "sell_to_cover" and v["verified"]


def test_decide_registers_the_anchor_and_queues_the_suggestive(tmp_path, monkeypatch):
    monkeypatch.setattr(sn, "REGISTER", str(tmp_path / "reg.csv"))
    monkeypatch.setattr(sn, "PENDING", str(tmp_path / "pend.csv"))
    monkeypatch.setattr(sn, "_REG", None)
    assert sn.decide(_root(TWST), "ACC-1", "TWST", "1") == "sold to cover tax"
    # suggestive but unanchored: queued, and today's answer is None
    soft = "Shares sold in connection with the vesting of restricted stock units."
    assert sn.decide(_root(soft), "ACC-2", "TWST", "1") is None
    assert os.path.exists(sn.PENDING), "the reader's queue"
    # plain footnote: nothing happens
    assert sn.decide(_root("A sale."), "ACC-3", "TWST", "1") is None
    # the register answers without re-reading
    monkeypatch.setattr(sn, "_REG", None)
    assert sn.decide(_root("unrelated"), "ACC-1", "TWST", "1") == "sold to cover tax"


def test_a_queued_footnote_does_not_queue_again_next_walk(tmp_path, monkeypatch):
    monkeypatch.setattr(sn, "REGISTER", str(tmp_path / "reg.csv"))
    monkeypatch.setattr(sn, "PENDING", str(tmp_path / "pend.csv"))
    monkeypatch.setattr(sn, "_REG", None)
    soft = "Shares sold in connection with the vesting of restricted stock units."
    assert sn.decide(_root(soft), "ACC-9", "TWST", "1") is None
    monkeypatch.setattr(sn, "_REG", None)  # a fresh process: the next night's walk
    assert sn.decide(_root(soft), "ACC-9", "TWST", "1") is None
    with open(sn.PENDING) as fh:
        assert sum(1 for line in fh if line.startswith("ACC-9")) == 1, \
            "append-once per accession, across runs"
