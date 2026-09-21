

def test_a_holding_larger_than_the_cover_count_states_shares_but_no_percentage():
    """BOXABL (2026-09-21): a Form 3's Class B, 59.6M shares, against a cover
    that counts 10.3M of one class. The shares are real; 579% is not. The
    figure is withheld and the problem says why."""
    from fle import ownership as O
    src = __import__("inspect").getsource(O)
    assert "no percentage can be stated" in src and "rec.pct = None" in src
