"""How a stake was acquired: bought, or paid."""
from fle.flows import Flows


def _f(txns):
    f = Flows()
    for code, acquired, shares, date in txns:
        f.add(code, acquired, shares, date, "Common Stock", "D")
    return f


def test_a_founder_who_bought_and_an_executive_who_was_paid():
    """The same holding, two different stories -- and the code is the only
    thing that tells them apart. For a product about founder ownership, that
    distinction is arguably the whole point."""
    founder = _f([("P", True, 4_000_000, "2019-05-01"),
                  ("A", True, 50_000, "2020-03-01"),
                  ("S", False, 200_000, "2024-06-01")])
    hired = _f([("A", True, 120_000, "2021-03-01"),
                ("M", True, 300_000, "2022-03-01"),
                ("F", False, 140_000, "2022-03-01")])

    assert founder.bought == 4_000_000
    assert founder.bought_share > 98
    assert hired.bought == 0
    assert hired.bought_share == 0
    assert hired.from_derivative == 300_000


def test_withholding_is_not_a_sale():
    """Code F is shares kept back to pay tax or an exercise price. Musk's
    17,531,857 was the bill for his exercise, not a decision to sell, and
    counting it as one would misread the most-watched row in the index."""
    f = _f([("M", True, 303_960_630, "2026-06-16"),
            ("F", False, 17_531_857, "2026-06-16")])
    assert f.sold == 0
    assert f.surrendered == 17_531_857
    assert f.from_derivative == 303_960_630


def test_an_amendment_does_not_count_twice():
    """A 4/A restates the original's rows. Reading both would double a
    transaction, so identical rows collapse on what identifies one: its date,
    code, security and size."""
    f = Flows()
    for _ in range(2):
        f.add("P", True, 5_000, "2026-01-05", "Common Stock", "D")
    assert f.bought == 5_000
    assert f.by_code["P"][0] == 1

    # two genuinely different sizes on one day are both kept
    f.add("P", True, 7_000, "2026-01-05", "Common Stock", "D")
    assert f.bought == 12_000


def test_no_acquisitions_yet_is_not_zero_percent_bought():
    """A chief executive appointed last quarter has no answer yet, and
    reporting 0% would say they chose not to buy."""
    assert Flows().bought_share is None
    assert _f([("A", True, 100, "2026-01-01")]).bought_share == 0


def test_these_are_flows_not_a_position():
    """Someone can buy a million shares and sell a million. "How they
    acquired" and "what they still own" are different questions."""
    f = _f([("P", True, 1_000_000, "2020-01-01"),
            ("S", False, 1_000_000, "2024-01-01")])
    assert f.bought == 1_000_000       # they did buy it
    assert f.sold == 1_000_000         # and they no longer hold it
    assert f.bought_share == 100       # of what they acquired, all was bought


def test_the_code_tally_shows_everything_the_buckets_hide():
    f = _f([("P", True, 5_000, "2026-01-05"), ("A", True, 100, "2026-02-01"),
            ("G", False, 42, "2026-03-01"), ("J", True, 7, "2026-04-01")])
    tally = f.tally()
    assert "P=1:5,000" in tally and "G=1:42" in tally and "J=1:7" in tally
    assert f.gifted_out == 42 and f.other_in == 7


def test_a_founding_stake_is_neither_bought_nor_granted():
    """It appears in no transaction: it is simply there on the Form 3, the
    initial statement filed on becoming an insider. Musk held about 449.6
    million Tesla shares at his -- a third of everything he has ever had.

    Counting only transactions reported him as buying 0.6% of his stake,
    which describes a founder as though he were a hired executive.
    """
    f = Flows()
    f.opening = 449_598_698
    for code, acquired, n in [("A", True, 522_203_918), ("M", True, 333_714_902),
                              ("C", True, 24_389_250), ("X", True, 113_908),
                              ("P", True, 5_533_585), ("J", True, 53_499)]:
        f.add(code, acquired, n, "2020-01-01", "Common Stock", "D")

    assert abs(f.founded_share - 33.7) < 0.1
    assert abs(f.bought_share - 0.41) < 0.05      # measured against everything
    assert f.acquired < f.sourced                 # the opening is not acquired


def test_no_form_3_is_not_a_zero_founding_stake():
    """A chief executive whose Form 3 predates electronic filing has an
    unknown opening position, not an empty one."""
    f = Flows()
    assert f.founded_share is None
    f.add("A", True, 100, "2026-01-01", "Common Stock", "D")
    assert f.founded_share == 0.0     # a Form 3 WAS read and held nothing


def test_the_flows_should_reconcile_to_the_holding():
    """opening + acquired - disposed == what they hold now. Zero residual
    means every share is accounted for, and the columns can be summed."""
    f = Flows()
    f.opening = 100_000
    for code, acquired, n in [("P", True, 50_000), ("A", True, 20_000),
                              ("S", False, 30_000)]:
        f.add(code, acquired, n, "2020-01-01", "Common Stock", "D")
    residual, pct = f.reconcile(140_000)
    assert residual == 0 and pct == 0


def test_a_split_breaks_the_reconciliation_and_is_reported():
    """A split is not a transaction. No Form 4 reports one; the balance
    simply multiplies, so a 2010 figure and a 2026 figure are in different
    units and adding them is meaningless.

    Musk's Form 3 records about 28 million Tesla shares against a holding of
    1.12 billion -- 16.1x, against the 15x of a 5-for-1 and a 3-for-1.
    """
    f = Flows()
    f.opening = 28_000_000
    for code, acquired, n in [("A", True, 522_203_918), ("M", True, 333_714_902),
                              ("C", True, 24_389_250), ("X", True, 113_908),
                              ("P", True, 5_533_585), ("J", True, 53_499),
                              ("S", False, 78_918_728), ("F", False, 17_553_585),
                              ("D", False, 96_000_000), ("G", False, 19_810_661)]:
        f.add(code, acquired, n, "2020-01-01", "Common Stock", "D")
    residual, pct = f.reconcile(1_123_324_786)
    assert residual > 400_000_000 and pct > 30

    import inspect
    from fle import ownership
    src = inspect.getsource(ownership.build)
    assert "not rec.flows_reconcile" in src
    assert "do not add these" in " ".join(src.split())


def test_the_current_holding_is_unaffected_by_any_of_this():
    """It comes from the NEWEST filing, entirely in today's units. Only the
    lifetime flows cross split boundaries."""
    import inspect
    from fle import ledger
    src = inspect.getsource(ledger.build_ledger)
    # the position is settled newest-first, independently of the flow tally
    assert "led.flows.add(" in src
    assert "if key not in led.groups:" in src


# --- split adjustment ----------------------------------------------------

def test_a_forward_split_restates_old_amounts_in_todays_shares():
    """Tesla split 5-for-1 in 2020 and 3-for-1 in 2022. Musk's 2010 Form 3
    and a 2013 purchase are both in pre-split shares; a 2026 grant is not.

    Left alone this does not blur the columns, it BIASES them: a founder who
    bought early has their purchases shrunk fifteenfold while an executive
    granted stock last year is counted at face value.
    """
    from fle.splits import Splits, Split
    tsla = Splits("TSLA", [Split("2020-08-31", 5.0), Split("2022-08-25", 3.0)])
    assert tsla.factor_since("2010-07-02") == 15
    assert tsla.factor_since("2013-05-01") == 15
    assert tsla.factor_since("2021-01-01") == 3      # only the later split
    assert tsla.factor_since("2026-06-16") == 1
    assert tsla.adjust(28_000_000, "2010-07-02") == 420_000_000


def test_a_split_on_the_execution_date_is_already_adjusted():
    """A transaction ON the execution date is reported in post-split shares,
    so only splits strictly after it apply."""
    from fle.splits import Splits, Split
    s = Splits("X", [Split("2020-08-31", 5.0)])
    assert s.factor_since("2020-08-31") == 1
    assert s.factor_since("2020-08-30") == 5


def test_a_reverse_split_uses_the_same_arithmetic():
    """GE's 1-for-8 in 2021: eight old shares became one."""
    from fle.splits import Splits, Split
    ge = Splits("GE", [Split("2021-08-02", 1 / 8)])
    assert ge.adjust(8_000, "2015-01-01") == 1_000


def test_amendments_dedupe_on_the_reported_figure():
    """An amendment restates the original's numbers, not the adjusted ones,
    so the key has to be built before adjustment."""
    from fle.splits import Splits, Split
    from fle.flows import Flows
    s = Splits("X", [Split("2020-01-01", 2.0)])
    f = Flows()
    for _ in range(2):
        f.add("P", True, 1_000, "2019-01-01", "Common Stock", "D", s)
    assert f.bought == 2_000          # adjusted once, not counted twice


def test_no_api_key_says_so_rather_than_silently_not_adjusting():
    from fle.splits import fetch_splits
    out = fetch_splits(None, "TSLA", None)
    assert not out.ok and "unadjusted" in out.note
    assert out.factor_since("2010-01-01") == 1.0


def test_the_flows_read_the_same_tables_the_position_does():
    """Reading Table I only meant the flows and the position disagreed about
    what counts. Zuckerberg's Class B is convertible, so every share of it
    lives in Table II -- and a code-J transfer of 414,123,745 into Chan
    Zuckerberg Initiative, LLC went unread while his J total came back as
    3,466,735 of Class A.

    If a security is counted in the numerator, its transactions belong in the
    flows. Options and units are excluded by the same rule that excludes them
    from the holding.
    """
    import inspect
    from fle import ledger
    src = inspect.getsource(ledger.build_ledger)
    assert 'if r.table == "II" and not is_share_class(r.security):' in src
    assert 'if row.table == "I" and row.code:' not in src

    # a convertible class counts; an option does not
    assert ledger.is_share_class("Class B Common Stock")
    assert not ledger.is_share_class("Non-Qualified Stock Option (right to buy)")


def test_the_form_3_is_read_for_the_flows_only():
    """The position no longer needs it -- a filing states each group whole,
    so nothing is carried and there is nothing to seed.

    But a founding stake appears in no transaction: it is simply there on the
    initial statement. Without it "3.2% bought" measures Musk against his
    grants alone and calls a founder a hired executive.
    """
    import inspect
    from fle import ledger
    src = inspect.getsource(ledger.build_ledger)
    assert "THE FORM 3, FOR THE FLOWS ONLY" in src
    assert "led.flows.opening = opening" in src
    # it must not touch the holding
    assert "led.groups[" not in src.split("THE FORM 3, FOR THE FLOWS ONLY")[1]
    # and it is split-adjusted, because a Form 3 predates every split
    assert "splits.adjust(r.shares, when) if splits else r.shares" in src


def test_the_form_3_must_be_about_this_issuer():
    """Schwarzman has 162 Form 3s across Blackstone's funds; the oldest is
    one of theirs."""
    import inspect
    from fle import ledger
    src = inspect.getsource(ledger.build_ledger)
    block = src.split("THE FORM 3, FOR THE FLOWS ONLY")[1]
    assert "if got and got != str(int(issuer_cik)):" in block


# --------------------------------------------------------------- events feed

def _own_doc(rows, aff=None, cik="1494730"):
    """rows: (date, code, A/D, shares, price, balance, D/I, security, nature)"""
    body = "".join(f"""<nonDerivativeTransaction>
      <securityTitle><value>{sec}</value></securityTitle>
      <transactionDate><value>{d}</value></transactionDate>
      <transactionCoding><transactionCode>{c}</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>{sh}</value></transactionShares>
        {'<transactionPricePerShare><value>%s</value></transactionPricePerShare>' % px if px else ''}
        <transactionAcquiredDisposedCode><value>{ad}</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <postTransactionAmounts><sharesOwnedFollowingTransaction><value>{bal}</value></sharesOwnedFollowingTransaction></postTransactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>{di}</value></directOrIndirectOwnership>
        {'<natureOfOwnership><value>%s</value></natureOfOwnership>' % nat if nat else ''}</ownershipNature>
    </nonDerivativeTransaction>""" for d, c, ad, sh, px, bal, di, sec, nat in rows)
    a = f"<aff10b5One>{aff}</aff10b5One>" if aff is not None else ""
    return f"""<ownershipDocument>{a}
      <issuer><issuerCik>0000320193</issuerCik></issuer>
      <reportingOwner><reportingOwnerId><rptOwnerCik>{cik}</rptOwnerCik>
        <rptOwnerName>Test Person</rptOwnerName></reportingOwnerId>
        <reportingOwnerRelationship><isOfficer>1</isOfficer>
        <officerTitle>CEO</officerTitle></reportingOwnerRelationship></reportingOwner>
      <nonDerivativeTable>{body}</nonDerivativeTable></ownershipDocument>"""


def _client_for(doc, acc="0001-21-A", report="2021-11-10", prior=None):
    """One filing, or a baseline filing followed by the one under test.

    `prior` matters more than it looks. The first filing in a walk has no
    established position behind it, so holding_before is 0 and net_change is
    the whole stake -- correct, but it makes every single-filing fixture look
    like a defect. Real chief executives have filed before.
    """
    F = [{"form": "4", "accessionNumber": acc, "reportDate": report,
          "filingDate": report, "primaryDocument": "d.xml"}]
    docs = {"d.xml": doc}
    if prior is not None:
        F.insert(0, {"form": "4", "accessionNumber": acc + "-P",
                     "reportDate": "2000-01-01", "filingDate": "2000-01-01",
                     "primaryDocument": "p.xml"})
        docs["p.xml"] = prior

    class C:
        def submissions(self, cik):
            return {"_filings": F}
        def get(self, url, use_cache=True):
            return docs["p.xml" if "p.xml" in url else "d.xml"]
    return C()


def test_datadog_net_change_comes_from_history_not_a_second_walk():
    """Pomel sold 206,223 across two vehicles; history knows what it did to him.

    Events once computed the position with a walk of its own and rediscovered,
    badly, what history's walk already handles -- chained balances, benched
    vehicles, replace-on-transaction. Now the trade detail comes from the
    filing and the position comes from history, one state machine, not two.
    """
    from fle.events import build_events

    rows = [("2021-11-10", "S", "D", 2900, 185.46, 386615, "D", "Class A Common Stock", ""),
            ("2021-11-10", "S", "D", 142572, 190.00, 244043, "D", "Class A Common Stock", ""),
            ("2021-11-10", "S", "D", 60751, 191.00, 865, "I", "Class A Common Stock", "By GRAT")]
    hist = {320193: [("2021-11-09", 451131.0, 451131.0, 0.0),
                     ("2021-11-10", 244908.0, 244908.0, 0.0)]}
    c = _client_for(_own_doc(rows))
    e = build_events(c, 320193, "1494730", "DDOG", "Olivier Pomel", history=hist)[0]

    assert e.shares == 2900 + 142572 + 60751
    assert e.holding_after == 244908.0, "the day's total, from history"
    assert e.net_change == 244908.0 - 451131.0
    assert e.pct_of_holding is not None and -100 < e.pct_of_holding < 0, "signed: the stake fell"
    assert abs(e.pct_of_holding - 100 * (244908.0 - 451131.0) / 451131.0) < 1e-9


def test_deere_exercise_and_sell_leaves_the_position_alone():
    """John May sold $2.69m and owned exactly what he owned before.

    History's snapshots for the day show no net movement and no residue, so
    the event may say so: exercise and sell, position unchanged, and no
    percent printed for a stake that did not move.
    """
    from fle.events import build_events

    rows = [("2019-06-21", "M", "A", 16468, 100.55, 60550, "D", "$1 Par Common Stock", ""),
            ("2019-06-21", "S", "D", 16468, 163.21, 44082, "D", "$1 Par Common Stock", "")]
    hist = {320193: [("2019-06-20", 44082.0, 44082.0, 0.0),
                     ("2019-06-21", 44082.0, 44082.0, 0.0)]}
    c = _client_for(_own_doc(rows), acc="0001-19-A", report="2019-06-21")
    e = build_events(c, 320193, "1494730", "DE", "John C. May", history=hist)[0]

    assert e.code == "S" and round(e.value) == round(16468 * 163.21)
    assert e.net_change == 0.0 and e.stake_unchanged
    assert e.label == "exercise and sell"
    assert e.pct_of_holding is None, "28% of a stake that did not move"
    assert "M" in e.other_codes


def test_applovin_a_day_history_cannot_explain_is_flagged_not_asserted():
    """Foroughi's June 2026 filings defeat clean attribution -- for history too.

    Several same-day Form 4s; a trust reported in one, omitted in the next,
    restated at a different balance in the third, having sold in between.
    History's totals wobble and its `unexplained` column says by how much:
    -2,311,038 / -2,962,184 / +2,311,038 across the three days. An event on
    such a day inherits the residue and makes no claim: no net shown as
    trustworthy, no percent, no "position unchanged" label. Flag, never fix.
    """
    from fle.events import build_events

    rows = [("2026-06-11", "S", "D", 8624, 476.00, 2391604, "D", "Class A Common Stock", "")]
    hist = {320193: [("2026-06-10", 5575655.0, 5575655.0, -2311038.0),
                     ("2026-06-11", 2561306.0, 2561306.0, -2962184.0)]}
    c = _client_for(_own_doc(rows, aff="false"), acc="0001-26-A", report="2026-06-11")
    e = build_events(c, 320193, "1494730", "APP", "Adam Foroughi", history=hist)[0]

    assert e.residue == -2962184.0
    assert e.pct_of_holding is None, "no percent against a day that will not reconcile"
    assert e.label == "discretionary sale", "and no unchanged claim either"
    assert e.value == 8624 * 476.00, "the trade itself is still exactly as filed"


def test_without_history_the_feed_still_reports_the_trades():
    """Position columns are a join, not a requirement.

    Run before history has built -- or for a company outside it -- and the
    feed still carries everything the filing states: shares, price, value,
    plan. The position columns are simply absent rather than guessed at.
    """
    from fle.events import build_events

    rows = [("2019-06-21", "S", "D", 100, 50.00, 900, "D", "Common Stock", "")]
    c = _client_for(_own_doc(rows), acc="0001-19-A", report="2019-06-21")
    e = build_events(c, 320193, "1494730", "X", "Someone")[0]

    assert e.value == 5000.0
    assert e.holding_after is None and e.net_change is None
    assert e.pct_of_holding is None


def test_costar_one_filing_three_days_is_one_event_with_a_span():
    """One filing, three days: 26, 27 and 30 April 2018. One instruction,
    filed once, one event: the shares and dollars of all three days, the
    average price, dated by the last day with the first kept beside it.
    Kept apart by day, the 26th and 27th had no position of their own and
    borrowed the previous filing's verdict."""
    from fle.events import build_events

    rows = [("2018-04-26", "S", "D", 7782, 372.34, 136870, "D", "Common Stock", ""),
            ("2018-04-27", "S", "D", 11200, 371.15, 125670, "D", "Common Stock", ""),
            ("2018-04-30", "S", "D", 5839, 369.05, 119831, "D", "Common Stock", "")]
    hist = {320193: [("2018-03-01", 144652.0, 144652.0, 0.0),
                     ("2018-04-30", 119831.0, 119831.0, 0.0)]}
    c = _client_for(_own_doc(rows), acc="0001-18-A", report="2018-04-30")   # filed on the last day
    ev = build_events(c, 320193, "1494730", "CSGP", "Andrew C. Florance", history=hist)

    assert len(ev) == 1
    e = ev[0]
    assert (e.traded_from, e.traded) == ("2018-04-26", "2018-04-30")
    assert e.shares == 7782 + 11200 + 5839 and e.rows == 3
    assert round(e.value, 2) == round(7782 * 372.34 + 11200 * 371.15 + 5839 * 369.05, 2)
    assert e.holding_after == 119831.0 and e.net_change == 119831.0 - 144652.0
    assert abs(e.pct_of_holding - 100 * (119831.0 - 144652.0) / 144652.0) < 1e-9
    assert e.label == "sale"


def test_commvault_every_day_of_a_filing_carries_the_filings_verdict():
    """Mirchandani sold on 17, 18 and 19 August 2026 in one filing; the
    stake fell 64,868 across it (with residue: a partial vehicle). By day,
    the 17th and 18th read "position unchanged" because the previous
    filing had netted to zero. One event, and the filing's own residue
    says the change is not stated."""
    from fle.events import build_events

    rows = [("2026-08-17", "S", "D", 12437, 60.0, 366107, "D", "Common Stock", ""),
            ("2026-08-18", "S", "D", 4840, 60.0, 361267, "D", "Common Stock", ""),
            ("2026-08-19", "S", "D", 6857, 60.0, 354410, "D", "Common Stock", "")]
    hist = {320193: [("2026-05-20", 378544.0, 378544.0, 0.0),      # nets to zero
                     ("2026-08-19", 313676.0, 313676.0, -40734.0)]}
    c = _client_for(_own_doc(rows), acc="0001-26-C", report="2026-08-19")
    ev = build_events(c, 320193, "1494730", "CVLT", "Sanjay Mirchandani", history=hist)
    assert len(ev) == 1 and ev[0].shares == 24134
    # the filing's own net (its rows), the day's net beside it, the residue flagged
    assert ev[0].net_change == -24134.0 and ev[0].day_net == -64868.0 and ev[0].residue == -40734.0
    assert ev[0].label == "sale" and ev[0].pct_of_holding is None, "residue: not stated, not unchanged"


def test_adpt_an_exercise_and_sell_over_two_days_is_unchanged_on_both():
    """Robins exercised and sold 600,000 shares over 17 and 18 August 2026.
    By day, the 17th read "discretionary sale, 12.8% of stake" from the
    previous filing's net. One event: exercise and sell, unchanged."""
    from fle.events import build_events

    rows = [("2026-08-17", "M", "A", 321324, 5.0, 2501842, "D", "Common Stock", ""),
            ("2026-08-17", "S", "D", 321324, 40.0, 2180518, "D", "Common Stock", ""),
            ("2026-08-18", "M", "A", 278676, 5.0, 2459194, "D", "Common Stock", ""),
            ("2026-08-18", "S", "D", 278676, 40.0, 2180518, "D", "Common Stock", "")]
    hist = {320193: [("2026-05-01", 2180518.0, 2180518.0, 0.0),
                     ("2026-08-18", 2180518.0, 2180518.0, 0.0)]}
    c = _client_for(_own_doc(rows, aff="false"), acc="0001-26-D", report="2026-08-18")
    ev = build_events(c, 320193, "1494730", "ADPT", "Chad Robins", history=hist)
    assert len(ev) == 1
    assert ev[0].shares == 600000 and ev[0].label == "exercise and sell"
    assert ev[0].pct_of_holding is None and ev[0].stake_unchanged


def test_deere_2017_an_exercise_that_kept_some_shares_reads_as_a_rise():
    """May exercised 25,130, sold 19,907 and kept 5,223. The old percent,
    gross sold over the position before, printed -40.4% beside a filing
    that left him richer. The net says +12%, beside a SOLD badge, with an
    M in the codes: the truth of that filing."""
    from fle.events import build_events

    rows = [("2017-06-06", "M", "A", 25130, 80.0, 69241, "D", "Common Stock", ""),
            ("2017-06-06", "S", "D", 19907, 125.57, 49334, "D", "Common Stock", "")]
    hist = {320193: [("2017-01-01", 44111.0, 44111.0, 0.0),
                     ("2017-06-06", 49334.0, 49334.0, 0.0)]}
    c = _client_for(_own_doc(rows), acc="0001-17-A", report="2017-06-06")
    e = build_events(c, 320193, "1494730", "DE", "John C. May", history=hist)[0]
    assert e.code == "S" and e.net_change == 5223.0
    assert abs(e.pct_of_holding - 100 * 5223 / 44111) < 1e-9
    assert e.pct_of_holding > 0 and "M" in e.other_codes


def test_two_filings_on_one_day_each_state_their_own_net():
    """Musk, 21 December 2021: one filing exercises 934,091 options and
    sells 583,611 (net +350,480); the other sells 350,480 outright. One
    history point for the day, net zero. Handed a share of the day's net
    by gross shares, the outright sale read "stake +0.74%". Each filing's
    net is its own rows; the day's opening position is what both are
    measured against; the two add up to the day."""
    from fle.events import build_events
    ex = [("2021-12-21", "M", "A", 934_091, 0.0, 0, "D", "Common Stock", ""),
          ("2021-12-21", "S", "D", 583_611, 1_000.0, 0, "D", "Common Stock", "")]
    sale = [("2021-12-21", "S", "D", 350_480, 1_000.0, 0, "D", "Common Stock", "")]
    hist = {320193: [("2021-12-20", 170_000_000.0, 170_000_000.0, 0.0),
                     ("2021-12-21", 170_000_000.0, 170_000_000.0, 0.0)]}
    docs = {"0001-21-X": _own_doc(ex), "0001-21-Y": _own_doc(sale)}
    F = [{"form": "4", "accessionNumber": k, "reportDate": "2021-12-21", "filingDate": "2021-12-22", "primaryDocument": "d.xml"} for k in docs]

    class C:
        def submissions(self, cik):
            return {"_filings": F}
        def get(self, url, use_cache=True):
            for k, d in docs.items():
                if k.replace("-", "") in url:
                    return d
            raise KeyError(url)
    ev = sorted(build_events(C(), 320193, "1494730", "TSLA", "Elon Musk", history=hist), key=lambda e: e.accession)
    by = {e.accession: e for e in ev}
    exs, out = by["0001-21-X"], by["0001-21-Y"]
    assert exs.net_change == 350_480 and exs.label == "exercise and sell" and exs.pct_of_holding > 0
    assert out.net_change == -350_480 and out.label != "exercise and sell" and out.pct_of_holding < 0, "the outright sale is a sale, and the stake fell by it"
    assert exs.day_net == 0 and out.day_net == 0 and exs._before == 170_000_000 == out._before


def test_blackstone_a_filing_about_another_company_is_not_a_trade_here():
    """Schwarzman signs Form 4s about the companies Blackstone controls as
    its controlling person, so they sit in both feeds. 587 of 605 are about
    other issuers; the walks skip them by the filing's own <issuer>, and
    the feed must too."""
    from fle.events import build_events

    rows = [("2026-08-25", "S", "D", 1_000_000, 100.0, 0, "I", "Class A Common Stock", "By Blackstone")]
    theirs = _own_doc(rows).replace("<issuerCik>0000320193</issuerCik>", "<issuerCik>0001602065</issuerCik>")
    c = _client_for(theirs, acc="0001-26-V", report="2026-08-25")
    assert build_events(c, 320193, "1494730", "BX", "Stephen A. Schwarzman") == []
    # the same rows about this issuer are a trade
    c = _client_for(_own_doc(rows), acc="0001-26-V", report="2026-08-25")
    assert len(build_events(c, 320193, "1494730", "BX", "Stephen A. Schwarzman")) == 1


def test_a_filing_whose_day_history_never_saw_states_no_change():
    """No snapshot on the filing's day: the holding is carried, the net is
    not borrowed from a neighbour, and no percent or verdict is claimed."""
    from fle.events import build_events

    rows = [("2026-08-17", "S", "D", 1000, 60.0, 9000, "D", "Common Stock", "")]
    hist = {320193: [("2026-05-20", 10000.0, 10000.0, -2000.0),
                     ("2026-09-01", 9000.0, 9000.0, 0.0)]}
    c = _client_for(_own_doc(rows), acc="0001-26-E", report="2026-08-17")
    e = build_events(c, 320193, "1494730", "X", "Someone", history=hist)[0]
    assert e.holding_after == 10000.0 and e.net_change is None and e.residue is None
    assert e.pct_of_holding is None and not e.stake_unchanged and e.label == "sale"


def test_the_10b5_1_box_has_four_spellings_and_a_missing_fifth():
    """1, 0, true, false -- and nothing at all before April 2023.

    A count matching only [01] dropped 621 filings and concluded no chief
    executive had ever bought under a plan. Absence is its own answer: the
    checkbox did not exist, and Garmin 2007 says in a footnote that the sale
    was under a plan while carrying no box to tick.
    """
    from fle.events import plan_state
    import xml.etree.ElementTree as ET

    for raw, want in (("1", "plan"), ("true", "plan"), ("TRUE", "plan"),
                      ("0", "discretionary"), ("false", "discretionary")):
        assert plan_state(ET.fromstring(_own_doc([], aff=raw))) == want
    assert plan_state(ET.fromstring(_own_doc([]))) == "unknown"


def test_a_filer_typo_is_flagged_and_still_shown():
    """$682,827 for a $63 stock is the filing's error, not ours.

    Two such rows in 68,889. The figure stays as filed and carries a flag,
    because a reader who can open the document and see it for themselves is
    better served than by a number we quietly changed.
    """
    from fle.events import Event, flag_prices

    ev = [Event(ticker="CRM", traded="2008-06-01", avg_price=63.71),
          Event(ticker="CRM", traded="2008-07-01", avg_price=64.10),
          Event(ticker="CRM", traded="2008-08-01", avg_price=62.90),
          Event(ticker="CRM", traded="2008-04-28", avg_price=682827.0)]
    flag_prices(ev)
    assert ev[-1].price_flag and "682,827" in ev[-1].price_flag
    assert ev[-1].avg_price == 682827.0, "flagged, never rewritten"
    assert not any(e.price_flag for e in ev[:3])


def test_tko_the_feed_honours_the_panel_s_exclusions():
    """Emanuel does not trade shares the panel says are not his.

    TKO's proxy reports Ari Emanuel at zero Class B; the shares are held of
    record by Endeavor entities and his own Form 4 footnote disclaims them.
    The panel drops them from the curated exclusions list. A feed that
    reported him selling them would contradict the table beside it.
    """
    from fle.events import build_events
    from fle.exclusions import Exclusion

    rows = [("2024-05-01", "S", "D", 1_000, 100.0, 9_000, "I",
             "Class B Common Stock", ""),
            ("2024-05-01", "S", "D", 500, 100.0, 4_500, "D",
             "Class A Common Stock", "")]
    c = _client_for(_own_doc(rows), acc="0001-24-T", report="2024-05-01")
    ex = [Exclusion(cik="320193", ticker="TKO", security="Class B Common Stock",
                    direct="I", reason="proxy reports him at zero", source="")]
    ev = build_events(c, 320193, "1494730", "TKO", "Ari Emanuel", exclude=ex)

    assert len(ev) == 1, "one event, from the class that is actually his"
    assert ev[0].shares == 500
    assert "Class A" in ev[0].securities and "Class B" not in ev[0].securities


def test_a_chief_executive_who_sells_out_has_no_percentage_left():
    """Selling the whole position closes at zero, and zero has no percentage.

    `pct_of_holding` rebuilds the pre-filing position from the close and the net.
    For a sale that empties the account the close is zero and the rebuild is
    the sale itself; for a first purchase the position before was zero. Both
    are legitimate, both divided by zero, and neither appeared in the eight
    companies the feed was verified against -- 500 found them immediately.
    """
    from fle.events import Event

    sold_out = Event(shares=1_000, holding_after=0.0, net_change=-1_000.0,
                     buy=False)
    assert sold_out.pct_of_holding is not None      # sold 100% of 1,000
    assert round(sold_out.pct_of_holding) == -100

    first_buy = Event(shares=500, holding_after=500.0, net_change=500.0,
                      buy=True)
    assert first_buy.pct_of_holding is None, "no stake to be a fraction of"

    nothing = Event(shares=0, holding_after=0.0, net_change=0.0, buy=False)
    assert nothing.pct_of_holding is None


def test_a_day_history_never_saw_carries_no_ones_residue():
    """The nearest snapshot's reconciliation is not this day's evidence.

    History emits a row per day a filing REPORTS ON, so a trade dated between
    two filings has no snapshot of its own. Reading the neighbour's
    `unexplained` gave 366 events a problem that belonged to another day --
    and, because a percentage is suppressed wherever residue is set, silently
    removed the feed's most useful column from all of them.
    """
    from fle.events import _position

    rows = [("2026-01-05", 1_000.0, 1_000.0, 0.0),
            ("2026-02-10", 900.0, 900.0, -55_000.0),   # a messy day
            ("2026-03-01", 880.0, 880.0, 0.0)]
    # An event ON the messy day inherits its residue, as it should.
    after, net, resid = _position(rows, "2026-02-10")
    assert after == 900.0 and resid == -55_000.0
    # An event BETWEEN snapshots gets the forward-filled holding and nothing
    # about a reconciliation it was not part of.
    after, net, resid = _position(rows, "2026-02-20")
    assert after == 900.0, "forward-filled, as a denominator would be"
    assert resid is None, "no claim either way about an unobserved day"
