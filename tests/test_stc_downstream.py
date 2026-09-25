"""THE TAX COVER STAYS OUT OF THE MEGAPHONES (2026-09-25). The alerts, the
letter and the X cards all classify through ops/kinds.py; these tests pin
that a "sold to cover tax" row is compensation everywhere, so no future
refactor can quietly grow a second taxonomy and put a mandated tax slice
back on the SOLD channel."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "ops"))

import kinds  # noqa: E402

STC = {"code": "S", "label": "sold to cover tax", "plan": "discretionary", "pre_ipo": ""}


def test_the_shared_taxonomy_calls_it_compensation():
    assert kinds.kind_of(STC) == "comp"
    assert kinds.group_of(STC) == "comp"
    assert "sold to cover tax" in kinds.COMP_LABELS
    assert kinds.KIND_DETAIL["sold to cover tax"] == "sold to cover tax"


def test_the_alerts_and_the_letter_read_from_that_one_copy():
    import importlib
    live = importlib.import_module("live")
    letter = importlib.import_module("letter")
    assert live.COMPENSATION is kinds.COMP_LABELS, \
        "ops/live.py classifies by the shared set, not a copy"
    assert letter.COMPENSATION is kinds.COMP_LABELS
    assert letter.kind_of(STC) == "comp", "the letter's wrapper is kinds.kind_of"


def test_an_ordinary_discretionary_sale_still_sells():
    disc = {"code": "S", "label": "discretionary sale", "plan": "discretionary", "pre_ipo": ""}
    assert kinds.kind_of(disc) == "disc" and kinds.group_of(disc) == "sold"
