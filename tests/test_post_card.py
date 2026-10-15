"""THE POST (ops/post_card.py, 2026-09-18): three lines in the site's words,
no pronoun; the 1200x560 card from the same facts."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ops"))
import post_card  # noqa: E402


def test_the_post_is_two_lines_the_trade_and_the_stake():
    """TWO LINES (2026-10-15): the kind's own line and "Filed today" left.
    The manner is three words in the sentence, the day is the trade's, the
    second line is the stake before and after; no his or her anywhere."""
    t = post_card.post_text("AII", "Robert Ritchie", True, "plan", 720000, -1.5, 8.85, None, pct_before=8.98, when="Oct 9\u201313")
    assert t == "Founder Robert Ritchie sold $720K of $AII on a plan, Oct 9\u201313.\nStake 8.98% \u2192 8.85%.", t
    t = post_card.post_text("INBX", "Mark Lappe", True, "bought", 848977, 1.0, 6.59, None, pct_before=6.53, when="Oct 14")
    assert t == "Founder Mark Lappe bought $849K of $INBX on the open market, Oct 14.\nStake 6.53% \u2192 6.59%."
    t = post_card.post_text("SOUN", "Keyvan Mohajer", True, "disc", 868853, -0.76, 4.01, 9, pct_before=4.0407, when="Sep 15")
    assert t == "Founder Keyvan Mohajer sold $869K of $SOUN at their own discretion, Sep 15.\nStake 4.04% \u2192 4.01%."
    assert " his " not in t and " her " not in t, "the filing does not say"
    assert "PLANNED" not in t and "Filed" not in t and "minutes ago" not in t
    t = post_card.post_text("X", "A Hired CEO", False, "bought", 50000, 0.4, 0.05, 3, pct_before=0.0498, when="Oct 1")
    assert t.startswith("CEO A Hired CEO bought $50K of $X on the open market, Oct 1.") and "Stake 0.050%" in t
    # the arrow would show no change: the move as a share of the holding instead, or unchanged
    t = post_card.post_text("DBX", "Andrew Houston", True, "plan", 1000000, -0.04, 36.82, None, pct_before=36.8245, when="Oct 12")
    assert t.endswith("Stake 36.82%, down 0.04% of the holding."), t
    t = post_card.post_text("UTHR", "Martine Rothblatt", True, "disc", 5200000, 0, 1.56, None, pct_before=1.56, when="Oct 13")
    assert t.endswith("Stake 1.56%, unchanged."), t
    # a pre-2023 sale states no plan box: no manner
    t = post_card.post_text("OLD", "Old Hand", True, "sold", 2000000, -3, 4.0, None, pct_before=4.12, when="Mar 3")
    assert t.startswith("Founder Old Hand sold $2M of $OLD, Mar 3.")
    # the day as a post says it
    assert post_card.trade_days("", "2026-10-14") == "Oct 14" and post_card.trade_days("2026-10-14", "2026-10-14") == "Oct 14"
    assert post_card.trade_days("2026-10-09", "2026-10-13") == "Oct 9\u201313" and post_card.trade_days("2026-09-29", "2026-10-02") == "Sep 29\u2013Oct 2"
    assert post_card.trade_days("", "") == ""


def test_the_card_draws_at_the_link_card_ratio(tmp_path):
    from PIL import Image
    series = [(f"2026-{m:02d}-01", 10 + m) for m in range(1, 13)]
    out = tmp_path / "card.png"
    post_card.draw(str(out), "SOUN", "SoundHound AI, Inc.", "Dr. Keyvan Mohajer", True, "disc", 868853, "2026-09-15", 4.09, 4.01, series)
    im = Image.open(out)
    assert im.size == (1200, 630), "the link-card ratio"
    out2 = tmp_path / "nochart.png"
    post_card.draw(str(out2), "X", "X Corp", "Someone", False, "bought", None, "2026-09-15", None, 1.2, [])
    assert Image.open(out2).size == (1200, 630), "no price series, no amount: still a card"


def test_the_kind_is_the_tapes():
    assert post_card.post_kind({"code": "P", "plan": ""}) == "bought"
    assert post_card.post_kind({"code": "S", "plan": "plan"}) == "plan"
    assert post_card.post_kind({"code": "S", "plan": "discretionary"}) == "disc" and post_card.post_kind({"code": "S", "plan": "unknown"}) == "sold"
    assert post_card.short_name("SoundHound AI, Inc.", "SOUN") == "SoundHound AI" and post_card.short_name("Red Cat Holdings, Inc.", "RCAT") == "Red Cat"


def test_the_link_card_is_the_post_card(tmp_path):
    """THE LINK CARD (2026-09-18): the page's OG image is the compact card
    with the newest trade and the stake, the same for every company."""
    from PIL import Image
    out = tmp_path / "card.png"
    post_card.draw(str(out), "SEZL", "Sezzle Inc.", "Charles Youakim", True, "plan", 3_000_000, "2026-09-14", 5.2, 4.99, [], height=630)
    im = Image.open(out)
    assert im.size == (1200, 630)
    import company_cards
    assert "post_card.draw(" in open(os.path.join(ROOT, "ops", "company_cards.py"), encoding="utf-8").read(), "the deploy's company card is drawn by the post card"
    assert post_card.money(999_600_000) == "$1B" and post_card.money(999_800) == "$1M"


def test_a_day_the_record_cannot_add_up_still_states_the_stake_before_and_after():
    t = post_card.post_text("AMBA", "Feng-Ming Wang", True, "disc", 394555, "", 1.74, None, pct_before=1.7563)
    assert t.endswith("Stake 1.76% \u2192 1.74%.") and "of the holding" not in t
