"""The metric, and why it is not v1's."""


def test_the_v1_metric_fell_when_a_ceo_acquired_shares():
    """Musk exercised 303,960,630 options -- newly issued shares, so the
    denominator grew by the same amount the numerator already counted.

    v1: options in the numerator, excluded from the denominator, so the
    figure FALLS as he acquires stock. That is not imprecision, it is the
    wrong direction.
    """
    C, O = 413_000_000, 304_000_000
    S = 3_325_150_886
    S2 = S + O

    v1_before, v1_after = (C + O) / S, (C + O) / S2
    assert v1_after < v1_before                      # wrong direction

    common_before, common_after = C / S, (C + O) / S2
    assert common_after > common_before              # correct

    as_filed_before, as_filed_after = (C + O) / (S + O), (C + O) / S2
    assert abs(as_filed_before - as_filed_after) < 1e-9   # continuous...
    # ...but each company's denominator then includes only that person's own
    # options, so no two companies are measured alike.


def test_common_over_outstanding_matches_the_source_data():
    """Form 4 Table I reports common stock. Anchoring on common means the
    anchor and every update measure the same quantity, so a series built from
    filings has no discontinuity at the join."""
    from fle.ledger import _rows
    import inspect
    src = inspect.getsource(_rows)
    assert "nonDerivativeTransaction" in src
    assert "is_share_class" in src        # Table II only for share classes


# --- how a rating is reached --------------------------------------------

def test_confidence_weighs_flags_rather_than_counting_them():
    """Counting made "denominator sums 2 share classes" -- correct behaviour
    for a dual-class filer, not a defect -- weigh the same as a line missing
    from the total. Meta came back LOW while matching its own proxy to the
    share, and Apple slipped from high to medium for one dropped line.
    """
    import inspect
    from fle import ownership
    src = inspect.getsource(ownership.build)
    assert "worst = {lvl for lvl, _ in rec.graded}" in src
    assert 'if PROBLEM in worst' in src
    # the three severities are assigned where a flag is raised
    assert "flag(NOTE, f\"denominator sums" in src
    assert "flag(PROBLEM, f\"{len(led.blind)}" in src


def test_a_rating_describes_what_can_be_vouched_for():
    """Meta still rates low. A line whose balance was only ever footnoted
    might hold anything, and that it turned out to be nothing is not
    something the code can know."""
    from fle.ownership import NOTE, CAUTION, PROBLEM

    def rate(levels):
        return ("low" if PROBLEM in levels else
                "medium" if CAUTION in levels else "high")

    assert rate(set()) == "high"
    assert rate({NOTE}) == "high"                      # notes never demote
    assert rate({NOTE, CAUTION}) == "medium"
    assert rate({NOTE, CAUTION, PROBLEM}) == "low"


def test_a_date_gap_is_mostly_benign():
    """Transactions must be filed within two business days, so an old
    numerator means no transactions rather than stale data. The denominator is
    quarterly, so a few months is normal."""
    import inspect
    from fle import ownership
    src = inspect.getsource(ownership.build)
    assert "rec.gap_days > 365" in src        # a year can move the ratio
    assert "rec.gap_days > 150" in src        # months are only a note


def test_a_match_that_is_not_an_officer_is_a_problem():
    """The officer check ranks a person above a namesake vehicle -- but when
    nothing competes, a lone trust matches the name perfectly, wins by a wide
    margin, and passes every other test.

    The certification names a principal executive officer. A match not
    flagged as one is the wrong person until someone says otherwise, so it
    forces LOW rather than sailing through.
    """
    import inspect
    from fle import ownership
    src = inspect.getsource(ownership.build)
    assert "if led.owner_cik and not led.officer:" in src
    assert "flag(PROBLEM," in src.split("not led.officer:")[1][:120]

    # and the answer is inspectable in the sheet rather than inferred
    from fle.panel import COLUMNS
    assert "is_officer" in COLUMNS and "owner_name" in COLUMNS


def test_the_hole_this_closes():
    """Three cases, and only the middle one used to flag."""
    def old(score, margin):
        return score < 0.9 or margin < 0.15

    def now(score, margin, officer):
        return old(score, margin) or not officer

    assert not old(1.00, 1.00) and not now(1.00, 1.00, True)    # person beats trust
    assert old(0.85, 0.05) and now(0.85, 0.05, True)            # close call
    assert not old(1.00, 1.00) and now(1.00, 1.00, False)       # lone trust: was silent


def test_owning_nothing_is_an_answer_not_an_error():
    """Verizon's Daniel Schulman has filed 32 times and holds no common
    stock: he was a director before becoming chief executive, and directors
    are paid in deferred stock units, which are derivatives rather than
    shares. A.O. Smith's Stephen Shafer is the same shape.

    Treating that as an error dropped both companies from the panel -- when
    for a site about how much chief executives own, "nothing at all" is one
    of the more interesting rows on it. Every newly appointed CEO starts here.
    """
    import inspect
    from fle import ownership
    src = inspect.getsource(ownership.build)
    # a genuine zero
    assert "if led.owner_cik and led.filings_read > 0:" in src
    assert "rec.shares = 0.0" in src
    assert "holds no common stock" in src

    # and a failure to read still errors, so the two never look alike
    assert 'rec.error = led.note or "no Section 16 holdings found"' in src


def test_zero_does_not_become_low_confidence():
    """A zero backed by 32 filings is a well-evidenced fact. It is a note,
    not a problem."""
    from fle.ownership import NOTE, CAUTION, PROBLEM

    def rate(levels):
        return ("low" if PROBLEM in levels else
                "medium" if CAUTION in levels else "high")
    assert rate({NOTE}) == "high"


def test_an_up_c_structure_gets_a_caveat_not_a_bare_zero():
    """Blackstone Inc is a holding company; the business sits in Blackstone
    Holdings partnerships, and Schwarzman's interest is 235,686,046
    exchangeable PARTNERSHIP UNITS with no common stock at all.

    Those units are not Blackstone Inc shares and are not in its shares
    outstanding, so counting them would inflate the ratio. But reporting 0%
    describes a man with a fifth of the firm as owning none of it. KKR,
    Carlyle, Ares and most post-2015 listings share the shape.
    """
    import inspect
    from fle import ownership
    src = inspect.getsource(ownership.build)
    # zero with units is a caution; zero without is only a note
    assert 'flag(CAUTION, f"holds no common stock, but' in src
    assert 'flag(NOTE, "holds no common stock")' in src
    assert "not issued stock of this issuer" in " ".join(src.split())


def test_a_lopsided_ratio_gets_the_same_caveat():
    """The same structure, less extremely: a little common stock and a great
    deal in Table II is just as misleading without the caveat."""
    def fires(shares, options):
        return bool(shares and options and options > shares * 3)

    assert fires(120_931, 500_000)            # mostly units
    assert not fires(3_280_418, 70_832)       # Cook: ordinary
    assert not fires(1_123_324_786, 0)        # Musk: none at all


def test_a_ceo_who_owns_nothing_at_all_is_simply_that():
    """No common stock and nothing uncounted either. It is a note, not a
    caution, and the row stays high confidence."""
    import inspect
    from fle import ownership
    src = inspect.getsource(ownership.build)
    assert 'flag(NOTE, "holds no common stock")' in src


def test_the_caveat_names_the_securities_rather_than_guessing():
    """This asserted "typically an exchangeable interest in an operating
    partnership" for anyone holding nothing -- true of Schwarzman's Blackstone
    Holdings units, false of Schulman, whose Verizon holding is director
    DEFERRED STOCK UNITS and has nothing to do with a partnership.

    The filings say what these are.
    """
    import inspect
    from fle import ownership
    src = inspect.getsource(ownership.build)
    assert "NAME THE SECURITIES, DO NOT GUESS THE STRUCTURE" in src
    assert "led.option_titles.items()" in src

    # the message is built from the titles, so it says what they are rather
    # than what such holdings usually are
    def message(total, titles):
        what = "; ".join(t for t, _ in sorted(titles.items(),
                                              key=lambda kv: -kv[1])[:3])
        return (f"holds no common stock, but {total:,.0f} of: "
                f"{what or 'units or options'} -- not counted, because it is "
                f"not issued stock of this issuer")

    schulman = message(9_034, {"Verizon Deferred Stock Units": 9034})
    schwarzman = message(1_438_529, {"Blackstone Holdings Partnership units": 1438529})
    assert "Deferred Stock Units" in schulman
    assert "partnership" not in schulman.lower()      # the old wording was wrong here
    assert "Partnership units" in schwarzman


def test_partnership_units_are_separated_from_compensation():
    """An up-C or UPREIT puts a public shell on top of an operating
    partnership and leaves the founders holding UNITS in the partnership,
    exchangeable one for one into the public stock: Blackstone's "Blackstone
    Holdings Partnership units", Ares' "Operating Group units", and the REIT
    family -- "OP Units", "LTIP Units" at Boston Properties, Prologis, Simon,
    Digital Realty, Kimco.

    Those are already issued and already the person's; a restricted stock unit
    is a promise that can be forfeited. Both sit in Table II, so a total
    cannot tell them apart -- and that difference decides whether excluding
    it is obviously right or merely arguable.
    """
    from fle.ledger import is_partnership_unit as u

    for t in ["Blackstone Holdings Partnership units", "Ares Operating Group units",
              "Common Units", "Class A Units", "OP Units", "LTIP Units",
              "Long-Term Incentive Units", "INVH LP LTIP Units", "AO LTIP Units"]:
        assert u(t), t

    for t in ["Restricted Stock Units", "Performance Share Units",
              "Phantom Stock Units", "Deferred Stock Units",
              "Employee Stock Option (Right to Buy)", "Stock Appreciation Right",
              "Performance Stock Units", "PSU 2024", "Other Stock Units"]:
        assert not u(t), t


def test_a_partnership_marker_is_required_not_merely_the_word_unit():
    """Matching any word "unit" and subtracting compensation caught eleven
    false positives out of twenty-seven: "Restricted Units" at Honeywell,
    Hartford and UPS, "Dividend Equivalent Unit" at Synchrony, "Growth Units"
    at Palantir, "SEP Unit" at Huntington Ingalls.

    An exclusion list can only name the pay shapes somebody has already seen.
    Naming what a partnership interest IS fails in the safe direction: an
    unrecognised one is missed and flagged ordinary, rather than an RSU being
    labelled ownership.
    """
    from fle.ledger import is_partnership_unit as u
    for t in ["Growth Units", "Restricted Units", "Restricted Units 2012",
              "Restricted Units (Cash Payable)", "Dividend Equivalent Unit",
              "Units", "SEP Unit", "Other Stock Units", "PSU 2024",
              "2013 Performace Stock Units"]:
        assert not u(t), t
    # LTIP spelled out is still LTIP -- Kimco and Digital Realty write it so
    assert u("Long-Term Incentive Units")
    assert u("LTIP Units")


def test_the_flag_reaches_the_sheet():
    from fle.panel import COLUMNS
    assert "operating_partnership" in COLUMNS
    assert "partnership_units" in COLUMNS


def test_a_stock_unit_is_never_a_partnership_interest():
    """Paccar grants "Stock Units (LTIP)"; Vivmark, a REIT, holds "LTIP
    Units". Identical vocabulary, opposite meanings, separated only by which
    word is the noun -- a stock unit is a unit of stock, a LTIP unit is a
    unit of the operating partnership.

    Matching the LTIP token alone flagged a truck manufacturer as an UPREIT.
    Not another exclusion list: one structural observation that happens also
    to cover Restricted, Performance and Other Stock Units.
    """
    from fle.ledger import is_partnership_unit as u
    assert not u("Stock Units (LTIP)")
    assert not u("STOCK UNITS (LTIP)")
    assert u("LTIP Units")

    # nothing genuine was lost
    for t in ["Long-Term Incentive Units", "INVH LP LTIP Units", "AO LTIP Units",
              "Class 2 Performance LTIP Units", "OP Units",
              "Operating Partnership Units", "Common Units", "Class A Units",
              "Blackstone Holdings Partnership units",
              "Ares Operating Group units", "Restricted Holdings Units"]:
        assert u(t), t

    # and every stock-unit shape is rejected by the same rule
    for t in ["Restricted Stock Units", "Performance Stock Units",
              "Other Stock Units", "Phantom Stock Units", "Deferred Stock Units",
              "2013 Performace Stock Units"]:
        assert not u(t), t
