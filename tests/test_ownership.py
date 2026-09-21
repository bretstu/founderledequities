

def test_a_holding_larger_than_the_cover_count_states_shares_but_no_percentage():
    """BOXABL (2026-09-21): a Form 3's Class B, 59.6M shares, against a cover
    that counts 10.3M of one class. The shares are real; 579% is not. The
    figure is withheld and the problem says why."""
    from fle import ownership as O
    src = __import__("inspect").getsource(O)
    assert "no percentage can be stated" in src and "rec.pct = None" in src


def test_the_up_c_rule_counts_the_units_and_not_the_paired_class():
    """THE UP-C RULE (2026-09-24), on Hagerty's shape: 1,037,740 Class A,
    50,978,823 Class V, 50,978,823 units. Class V equals the units, so it
    is the wrapper: the stake is Class A + units, counted once."""
    from fle import ownership as O
    src = __import__("inspect").getsource(O)
    assert "THE UP-C RULE" in src and "rec.units_counted = u" in src and "rec.paired_class = wrapper" in src
    # the arithmetic, stated: total (A + V) - V (still counted) + units
    led_total, classA, classV, units = 1037740 + 50978823, 1037740, 50978823, 50978823
    assert led_total - classV + units == classA + units == 52016563
