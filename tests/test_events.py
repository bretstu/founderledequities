"""One row per trade -- the feed the dashboard's tape is built from."""
import xml.etree.ElementTree as ET

from fle.events import Event, _position, flag_prices, plan_state


def _e(**kw):
    base = dict(ticker="TST", ceo="A Founder", code="S", buy=False,
                shares=10_000, value=1_000_000.0, avg_price=100.0)
    base.update(kw)
    return Event(**base)


# ---------------------------------------------------------------- position

HIST = [("2026-01-05", 100_000, 100_000, 0.0),
        ("2026-02-10", 90_000, 90_000, 0.0),
        ("2026-03-20", 95_000, 95_000, 2_500.0)]


def test_a_snapshot_day_reports_its_own_residue():
    after, net, resid = _position(HIST, "2026-03-20")
    assert after == 95_000
    assert net == 5_000
    assert resid == 2_500


def test_a_day_between_snapshots_forward_fills_and_owns_no_residue():
    """366 events once inherited a neighbour's reconciliation. A day history
    has no snapshot for knows the carried holding and nothing else -- not the
    nearest row's residue, and not zero, which would claim the day was clean."""
    after, net, resid = _position(HIST, "2026-03-01")
    assert after == 90_000
    assert net == -10_000
    assert resid is None


def test_before_the_first_snapshot_nothing_is_known():
    assert _position(HIST, "2025-12-31") == (None, None, None)
    assert _position([], "2026-01-01") == (None, None, None)


def test_the_first_snapshot_has_no_previous_day_to_net_against():
    after, net, resid = _position(HIST, "2026-01-05")
    assert after == 100_000
    assert net is None
    assert resid == 0.0


# ---------------------------------------------------------- percent of stake

def test_percent_is_of_the_position_before_the_trade():
    # sold 10,000 and closed at 90,000 -- that is 10% of the 100,000 held
    e = _e(holding_after=90_000, net_change=-10_000, residue=0.0)
    assert abs(e.pct_of_holding - 10.0) < 1e-9


def test_an_exercise_and_sell_prints_no_percentage():
    """28.43% of a stake that did not move is arithmetically right and
    communicatively false. John May exercised and sold the same shares."""
    e = _e(holding_after=44_082, net_change=0.0, residue=0.0, other_codes="M")
    assert e.stake_unchanged
    assert e.pct_of_holding is None
    assert e.label == "exercise and sell"


def test_an_unchanged_stake_is_only_an_exercise_when_the_filing_shows_one():
    """Schwarzman holds no common: his sales are partnership units exchanged
    and sold the same day, and the common position is zero before and
    after. That is not options being cashed, and the label must not say so
    on the position alone -- the filing's other codes decide."""
    units = _e(holding_after=0.0, net_change=0.0, residue=0.0, other_codes="C")
    assert units.stake_unchanged and units.pct_of_holding is None
    assert units.label == "convert and sell"
    assert units.unchanged_kind == "convert"
    bare = _e(holding_after=44_082, net_change=0.0, residue=0.0, other_codes="")
    assert bare.label == "sale, position unchanged"
    assert bare.unchanged_kind == ""
    both = _e(holding_after=44_082, net_change=0.0, residue=0.0, other_codes="CM")
    assert both.label == "exercise and sell", "an exercise in the filing outranks a conversion"
    moved = _e(holding_after=44_082, net_change=-500.0, residue=0.0, other_codes="M")
    assert moved.unchanged_kind is None and moved.label != "exercise and sell"


def test_a_day_with_residue_asserts_neither_net_nor_percentage():
    e = _e(holding_after=44_082, net_change=0.0, residue=50_000.0)
    assert e.pct_of_holding is None
    assert e.label == "sale"          # not "exercise and sell"


def test_a_first_purchase_divides_by_no_prior_stake():
    e = _e(code="P", buy=True, holding_after=10_000, net_change=10_000,
           residue=0.0)
    assert e.pct_of_holding is None


def test_selling_out_entirely_is_all_of_the_stake():
    e = _e(holding_after=0, net_change=-10_000, residue=0.0)
    assert abs(e.pct_of_holding - 100.0) < 1e-9


# ------------------------------------------------------------------- labels

def test_the_checkbox_words_the_label():
    assert _e(code="P", buy=True, plan="plan").label == "scheduled purchase"
    assert _e(code="P", buy=True, plan="unknown").label == "open-market purchase"
    assert _e(plan="plan", net_change=-10_000, holding_after=0,
              residue=0.0).label == "scheduled sale"
    assert _e(plan="discretionary", net_change=-10_000, holding_after=0,
              residue=0.0).label == "discretionary sale"
    # before April 2023 the checkbox did not exist; absence is not a "no"
    assert _e(plan="unknown", net_change=-10_000, holding_after=0,
              residue=0.0).label == "sale"


def test_the_checkbox_appears_in_four_spellings():
    for raw, want in (("1", "plan"), ("true", "plan"),
                      ("0", "discretionary"), ("false", "discretionary")):
        root = ET.fromstring(
            f"<doc><aff10b5One>{raw}</aff10b5One></doc>")
        assert plan_state(root) == want
    assert plan_state(ET.fromstring("<doc/>")) == "unknown"


# ------------------------------------------------------------------- prices

def test_a_mid_year_split_is_not_an_error():
    """Amazon's 20-for-1 landed in June 2022. Under the calendar-year bucket
    the year's median stayed pre-split and every legitimate post-split trade
    read as a filer error. The rolling window compares each trade with its
    neighbours in time, which within weeks of the split are post-split too."""
    evs = ([_e(traded=d, avg_price=p) for d, p in
            (("2022-01-10", 2_900.0), ("2022-02-10", 3_000.0),
             ("2022-03-10", 2_950.0))] +
           [_e(traded=d, avg_price=p) for d, p in
            (("2022-08-10", 140.0), ("2022-09-10", 142.0),
             ("2022-10-10", 145.0))])
    flag_prices(evs)
    assert not any(e.price_flag for e in evs)


def test_a_decimal_shift_is_flagged_but_never_corrected():
    """Nadella's 1 September 2020 filing reports $2,261,327 on a $226 stock.
    The filed number still shows -- a figure a reader cannot trace back to
    the document is worth less than a wrong one they can -- and the flag
    says so."""
    evs = [_e(traded=d, avg_price=p) for d, p in
           (("2020-07-01", 210.0), ("2020-08-01", 220.0),
            ("2020-09-01", 2_261_327.0), ("2020-10-01", 226.0))]
    flag_prices(evs)
    flagged = [e for e in evs if e.price_flag]
    assert len(flagged) == 1
    assert flagged[0].avg_price == 2_261_327.0     # set, never applied


def test_fewer_than_three_neighbours_is_no_verdict():
    evs = [_e(traded="2026-01-05", avg_price=100.0),
           _e(traded="2026-01-06", avg_price=100_000.0)]
    flag_prices(evs)
    assert not any(e.price_flag for e in evs)


def test_a_purchase_the_position_did_not_register_says_so():
    """Both of Schwarzman's August 2026 Blackstone purchases carry
    net_change 0 and holding_after 0 from history: the walk counts his
    common at zero before and after. The label must not call that a stake
    going up."""
    e = _e(code="P", buy=True, holding_after=0.0, net_change=0.0, residue=0.0,
           plan="discretionary")
    assert e.label == "purchase, position unchanged"
    assert e.pct_of_holding is None
    real = _e(code="P", buy=True, holding_after=10_000, net_change=10_000, residue=0.0)
    assert real.label == "open-market purchase"


def test_a_residue_too_small_to_change_the_answer_states_it_with_a_caution():
    """Tan: 105,263 bought, 561 unexplained, 1,331,640 after. Half a percent
    of the trade, four hundredths of a percent of the position."""
    tan = _e(code="P", buy=True, shares=105_263, holding_after=1_331_640,
             net_change=105_824, residue=561.0)
    assert tan.pct_of_holding is None, "the strict figure is still declined"
    assert abs(tan.pct_approx - 100 * 105_263 / (1_331_640 - 105_263)) < 1e-9
    # the median residue day: 38% of the trade -- stays unstated
    big = _e(shares=10_000, holding_after=100_000, net_change=-13_800, residue=3_800.0)
    assert big.pct_approx is None
    # small against the trade but large against a tiny position -- unstated
    tiny = _e(shares=1_000_000, holding_after=1_000, net_change=-1_000_000, residue=5_000.0)
    assert tiny.pct_approx is None
    # no residue at all: the strict figure exists and the approximation is not offered
    clean = _e(shares=10_000, holding_after=90_000, net_change=-10_000, residue=0.0)
    assert clean.pct_of_holding is not None and clean.pct_approx is None
    # an unchanged stake is never given a percentage, however small the residue
    ex = _e(shares=10_000, holding_after=90_000, net_change=0.0, residue=1.0, other_codes="M")
    assert ex.pct_approx is None


def test_a_trade_before_registration_is_a_catch_up_not_an_insider_trade():
    """Musk's 11,390 SpaceX shares: traded 2026-04-02, on a Form 4 filed
    2026-06-17; the issuer's first Section 16 filing was the Form 3 at
    registration in May. Pre-registration. A trade after it is not."""
    pre = _e(traded="2026-04-02", filed="2026-06-17", registered="2026-05-20")
    assert pre.pre_registration
    post = _e(traded="2026-06-15", filed="2026-06-17", registered="2026-05-20")
    assert not post.pre_registration
    unknown = _e(traded="2026-04-02", filed="2026-06-17", registered="")
    assert not unknown.pre_registration, "no registration date asserts nothing"
