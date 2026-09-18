"""THE POST (ops/post_card.py, 2026-09-18): three lines in the site's words,
no pronoun; the 1200x560 card from the same facts."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ops"))
import post_card  # noqa: E402


def test_the_post_is_three_lines_in_the_sites_words():
    t = post_card.post_text("SOUN", "Keyvan Mohajer", True, "disc", 868853, -0.76, 4.01, 9)
    assert t == "DISCRETIONARY SALE\nFounder Keyvan Mohajer sold $869K of $SOUN.\n\n0.76% of the stake. Now owns 4.01%.\nFiled 9 minutes ago."
    t = post_card.post_text("UPST", "Paul Gu", True, "bought", 1300000, 3.9, 1.3847, None)
    assert t.startswith("OPEN-MARKET BUY\nFounder Paul Gu bought $1.3M of $UPST.") and "3.9% of the stake. Now owns 1.38%." in t and t.endswith("Filed today.")
    t = post_card.post_text("RCAT", "Jeffrey Thompson", True, "plan", 1200000, -7.1359, 7.67, 14)
    assert t.startswith("PLANNED SALE\n") and "7.1% of the stake" in t
    assert " his " not in t and " her " not in t and " their " not in t, "no pronoun anywhere"
    t = post_card.post_text("X", "A Hired CEO", False, "bought", 50000, 0.4, 0.05, 3)
    assert t.startswith("OPEN-MARKET BUY\nCEO A Hired CEO bought $50K of $X.")


def test_the_card_draws_at_1200_by_560(tmp_path):
    from PIL import Image
    series = [(f"2026-{m:02d}-01", 10 + m) for m in range(1, 13)]
    out = tmp_path / "card.png"
    post_card.draw(str(out), "SOUN", "SoundHound AI, Inc.", "Dr. Keyvan Mohajer", True, "disc", 868853, "2026-09-15", 4.09, 4.01, series)
    im = Image.open(out)
    assert im.size == (1200, 560)
    out2 = tmp_path / "nochart.png"
    post_card.draw(str(out2), "X", "X Corp", "Someone", False, "bought", None, "2026-09-15", None, 1.2, [])
    assert Image.open(out2).size == (1200, 560), "no price series, no amount: still a card"


def test_the_kind_is_the_tapes():
    assert post_card.post_kind({"code": "P", "plan": ""}) == "bought"
    assert post_card.post_kind({"code": "S", "plan": "plan"}) == "plan"
    assert post_card.post_kind({"code": "S", "plan": "discretionary"}) == "disc" and post_card.post_kind({"code": "S", "plan": "unknown"}) == "sold"
    assert post_card.short_name("SoundHound AI, Inc.", "SOUN") == "SoundHound AI" and post_card.short_name("Red Cat Holdings, Inc.", "RCAT") == "Red Cat"
