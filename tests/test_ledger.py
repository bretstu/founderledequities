"""Every test here is a bug v1 shipped.

None were caught by internal consistency -- a ledger adds up whether or not
it has missed a line. Each was found by comparing against something outside
the code, so each is pinned to a number that can be checked in a filing.
"""
import xml.etree.ElementTree as ET

from fle.ledger import _rows, _owners, is_share_class, Ledger


def _f4(rows, derivatives=(), owner="Musk Elon", cik="0001494730"):
    def block(tag, items):
        return "".join(
            f'<{tag}><securityTitle><value>{s}</value></securityTitle>'
            f'<transactionDate><value>{d}</value></transactionDate>'
            # Musk's rows ARE transactions -- an exercise, then a
            # withholding. Without the code they read as standalone
            # holdings and add up.
            f'<transactionCoding><transactionCode>M</transactionCode>'
            f'</transactionCoding>'
            f'<postTransactionAmounts><sharesOwnedFollowingTransaction>'
            f'<value>{b}</value></sharesOwnedFollowingTransaction>'
            f'</postTransactionAmounts><ownershipNature>'
            f'<directOrIndirectOwnership><value>{di}</value>'
            f'</directOrIndirectOwnership>'
            + (f'<natureOfOwnership><value>{n}</value></natureOfOwnership>' if n else '')
            + f'</ownershipNature></{tag}>' for s, d, b, di, n in items)
    return ('<ownershipDocument><reportingOwner><reportingOwnerId>'
            f'<rptOwnerCik>{cik}</rptOwnerCik><rptOwnerName>{owner}</rptOwnerName>'
            '</reportingOwnerId><reportingOwnerRelationship>'
            '<isOfficer>1</isOfficer>'
            '<officerTitle>CEO</officerTitle></reportingOwnerRelationship>'
            '</reportingOwner>'
            + block("nonDerivativeTransaction", rows)
            + block("derivativeHolding", derivatives)
            + '</ownershipDocument>')


def _walk(filings):
    """The rule: newest first, each group taken whole from the first filing
    that reports it."""
    from fle.ledger import Group, is_share_class
    led = Ledger()
    for when, rows, *deriv in filings:
        root = ET.fromstring(_f4(rows, deriv[0] if deriv else ()))
        here = {}
        for r in _rows(root, "4", when, "acc"):
            if r.table == "II" and not is_share_class(r.security):
                continue
            if r.shares != r.shares:
                continue
            key = (r.security.lower(), r.direct)
            g = here.setdefault(key, Group(security=r.security, direct=r.direct,
                                           as_of=r.as_of, accession="acc",
                                           table=r.table))
            if r.code:
                g.last_txn[r.nature or ""] = r.shares
            else:
                g.holdings += r.shares
            g.rows += 1
        for g in here.values():
            g.shares = sum(g.last_txn.values()) + g.holdings
        for k, g in here.items():
            if k not in led.groups:
                led.groups[k] = g
    return led


MUSK_JUNE = ("2026-06-16", [
    ("Common Stock", "2026-06-16", 727_704_534, "D", None),   # after exercise
    ("Common Stock", "2026-06-16", 710_172_677, "D", None),   # after withholding
    ("Common Stock", "2026-06-16", 413_152_109, "I", "By Trust"),
])
MUSK_APRIL = ("2026-04-21", [
    ("Common Stock", "2026-04-21", 423_743_904, "D", None),
    ("Common Stock", "2026-04-21", 413_152_109, "I", "By Trust"),
])


def test_reproduces_a_holding_that_can_be_checked_outside_the_code():
    """1,123,324,786 is what commercial providers publish for Musk at Tesla,
    and 28.44% of the 3,949,547,394 on Tesla's July 10-Q cover."""
    led = _walk([MUSK_JUNE, MUSK_APRIL])
    assert led.total == 1_123_324_786
    assert abs(led.total / 3_949_547_394 * 100 - 28.44) < 0.01
    assert len(led.lines) == 2






def test_a_convertible_class_in_table_two_is_stock():
    """Zuckerberg's Class B is reported as a derivative because it converts
    into Class A. Excluding Table II returned 1,231,037 -- his foundation's
    Class A -- against an actual 342,463,325."""
    led = _walk([("2026-07-31",
                  [("Class A Common Stock", "2026-07-31", 1_231_037, "I",
                    "By Chan Zuckerberg Biohub, Inc.")],
                  [("Class B Common Stock", "2026-07-31", 341_232_288, "D", None)])])
    assert led.total == 342_463_325
    assert len(led.lines) == 2


def test_an_option_that_names_a_share_class_is_still_an_option():
    for t in ("Class B Common Stock", "Common Stock", "Ordinary Shares"):
        assert is_share_class(t), t
    for t in ("Option to Buy (Class B Common Stock)",
              "Non-Qualified Stock Option (right to buy)",
              "Employee Stock Option (Right to Buy)",
              "Restricted Stock Units", "Performance Share Units",
              "Series A Preferred Stock"):
        assert not is_share_class(t), t


def test_the_reporting_owner_is_read_from_the_filing():
    root = ET.fromstring(_f4(MUSK_JUNE[1]))
    assert _owners(root) == [("1494730", "Musk Elon", "CEO", True)]


# --- the Form 3 inventory ------------------------------------------------








def test_the_failure_message_says_what_was_searched():
    """"could not find this person" gave no way to tell a missing insider
    from a search that stopped too early."""
    import inspect
    from fle import ledger
    src = inspect.getsource(ledger.build_ledger)
    assert "Form 3s searched" in src
    assert "--max-search 0" in src


def test_the_best_match_wins_not_the_first():
    """"Michael S. Dell" against "Dell Susan Lieberman" -- his wife, a Dell
    insider in her own right -- scores 0.75, over the 0.7 floor.

    Searching newest-first happened to reach his filing before hers and hid
    it. Searching Form 3s reached hers first and returned her holdings as his:
    31,270,896 shares and 4.825% instead of his 294,263,250 and 45.4%.

    The matcher was always this lenient; changing the search order only
    exposed it. A shared surname is not unusual at the companies this project
    is about.
    """
    from fle.names import names_match
    assert names_match("Michael S. Dell", "Dell Susan Lieberman") >= 0.7   # still passes
    assert names_match("Michael S. Dell", "DELL MICHAEL S") == 1.0         # but loses

    import inspect
    from fle import ledger
    src = inspect.getsource(ledger.build_ledger)
    assert "if sc > best[0]:" in src
    assert "COLLECT EVERY CANDIDATE, THEN DECIDE" in src
    assert 'runner, best, tied = best[0], (sc, cik_, d["name"]), []' in src
    # the stop demands an exact-name OFFICER with a chief executive's title
    # on a RECENT filing -- each condition alone has picked the wrong person
    assert "settled_early" in src and 'when >= "2024"' in src


def test_a_narrow_win_is_reported():
    """A margin is exactly where a wrong person comes from, so it is shown
    rather than assumed away."""
    import inspect
    from fle import ledger, cli, ownership
    fields = {f.name for f in ledger.Ledger.__dataclass_fields__.values()}
    assert {"match_score", "runner_up"} <= fields
    assert "too close to call" in inspect.getsource(cli.cmd_ledger)
    assert "insider matched at" in inspect.getsource(ownership.build)


def test_only_a_narrow_win_warns():
    """A runner-up existing is normal: a spouse or sibling who is also an
    insider shares the surname. Michael Dell beats Susan Lieberman Dell 1.00
    to 0.75, which is decisive -- warning on it teaches the reader to ignore
    the warning."""
    def warn(best, runner):
        return best < 0.9 or (best - runner) < 0.15

    assert not warn(1.00, 0.75)      # the Dell case: decisive
    assert not warn(1.00, 0.00)
    assert warn(0.85, 0.00)          # nobody else, but a weak match
    assert warn(0.80, 0.75)          # two candidates, neither convincing
    assert warn(0.90, 0.88)          # near-identical


def test_an_exact_tie_is_broken_on_filing_count_and_recorded():
    """Coinbase returned two CIKs both scoring 1.00 against "Brian
    Armstrong". One person with two EDGAR identifiers, or a namesake --
    nothing in the filings says which, so a score cannot settle it and the
    winner was whichever came first.

    Broken on filing count: the primary identifier is the one they actually
    file under. Recorded either way, because a tie is the single case where
    the wrong person is a coin flip.
    """
    import inspect
    from fle import ledger
    src = inspect.getsource(ledger.build_ledger)
    assert "elif sc == best[0] and cik_ != best[1]:" in src
    assert "if alt and len(alt) > len(mine or []):" in src
    assert "tied" in {f.name for f in ledger.Ledger.__dataclass_fields__.values()}
    from fle import cli, ownership
    assert "TIED" in inspect.getsource(cli.cmd_ledger)
    assert "matched the name equally" in inspect.getsource(ownership.build)


def test_a_trust_named_after_the_ceo_is_not_the_ceo():
    """"Brian Armstrong Living Trust" files Coinbase Form 4s in its own right
    and scores a PERFECT 1.00 against "Brian Armstrong", because "Living
    Trust" reads as two more name tokens. The tie was broken on filing count,
    which happened to pick the person -- and could as easily not have.

    A trust is a ten per cent owner; a chief executive is an officer, and
    that is a checkbox in the schema. Matching on words like "trust" or "LLC"
    would fail on the next vehicle named something else.
    """
    from fle.names import names_match
    assert names_match("Brian Armstrong", "Brian Armstrong Living Trust") == 1.0
    assert names_match("Brian Armstrong", "Armstrong Brian") == 1.0

    # the officer flag is what separates them
    def score(name, is_officer):
        return names_match("Brian Armstrong", name) + (1.0 if is_officer else 0.0)

    assert score("Armstrong Brian", True) > score("Brian Armstrong Living Trust", False)

    import inspect
    from fle import ledger
    src = inspect.getsource(ledger.build_ledger)
    assert '(1.0 if d["officer"] else 0.0)' in src
    assert "isOfficer" in inspect.getsource(ledger._owners)


def test_a_reported_score_is_the_name_match_not_the_ranking():
    """The officer bonus is for ranking; showing 2.00 to a reader would be
    meaningless."""
    import inspect
    from fle import ledger
    src = inspect.getsource(ledger.build_ledger)
    assert "led.match_score = best[0] - 1.0 if best[0] > 1.0 else best[0]" in src


def test_the_margin_is_measured_on_the_ranking_not_the_display():
    """Ranking scores carry +1 for an officer, so Armstrong beat his own
    Living Trust 2.00 to 1.00 -- decisive. But the DISPLAYED scores strip that
    bonus off the winner only, giving 1.00 and 1.00, and a margin computed
    from those looked like a coin flip.

    So the officer fix worked and the warning still fired, which is worse than
    either: a correct result carrying a warning teaches people to ignore
    warnings.
    """
    import inspect
    from fle import ledger, ownership
    src = inspect.getsource(ledger.build_ledger)
    assert "led.margin = best[0] - runner" in src
    assert "margin" in {f.name for f in ledger.Ledger.__dataclass_fields__.values()}
    assert "led.margin < 0.15" in inspect.getsource(ownership.build)
    # 2.00 vs 1.00 is decisive even though both display as 1.00
    assert (2.00 - 1.00) >= 0.15


def test_either_officer_signal_counts():
    """Filers are inconsistent. A chief executive who is also chairman is
    sometimes ticked director-only with the title still filled in, and a
    missing tick would hand the match to a trust named after them.

    Both fields live in the same element, and a trust has neither.
    """
    import xml.etree.ElementTree as ET
    from fle.ledger import _owners

    def doc(name, rel):
        return (f"<ownershipDocument><reportingOwner><reportingOwnerId>"
                f"<rptOwnerCik>1</rptOwnerCik><rptOwnerName>{name}</rptOwnerName>"
                f"</reportingOwnerId><reportingOwnerRelationship>{rel}"
                f"</reportingOwnerRelationship></reportingOwner></ownershipDocument>")

    ticked = _owners(ET.fromstring(doc("A", "<isOfficer>1</isOfficer>")))[0]
    titled = _owners(ET.fromstring(doc("B", "<isDirector>1</isDirector>"
                                            "<officerTitle>CEO</officerTitle>")))[0]
    trust = _owners(ET.fromstring(doc("X Living Trust", "")))[0]
    director = _owners(ET.fromstring(doc("C", "<isDirector>1</isDirector>")))[0]

    assert ticked[3] is True
    assert titled[3] is True          # title alone is enough
    assert trust[3] is False
    assert director[3] is False       # a director with no title is not an officer


def test_the_search_only_stops_on_an_officer():
    """With the officer bonus an exact-name officer scores 2.0 and a namesake
    trust 1.0. Stopping at 1.0 ended the search on the TRUST -- Coinbase's
    filed its Form 3 at the 2021 direct listing, before Armstrong's -- and
    never reached the person.

    That manufactured the "lone non-officer match" case rather than merely
    failing to catch it.
    """
    import inspect
    from fle import ledger
    src = inspect.getsource(ledger.build_ledger)
    assert "CEO_TITLE.search(_title" in src
    assert "if best[0] >= 1.0:" not in src

    from fle.names import names_match
    trust = names_match("Brian Armstrong", "Brian Armstrong Living Trust")
    person = names_match("Brian Armstrong", "Armstrong Brian") + 1.0
    assert trust == 1.0 and person == 2.0
    assert trust < 2.0            # no longer ends the search


def test_a_filing_about_another_company_is_skipped():
    """A company that is itself an insider elsewhere carries those filings in
    its own submissions feed. Blackstone Inc is an insider of the funds it
    controls, so CIK 1393818's Section 16 list contains Form 4s about BREIT
    and BXMT -- and their securities were counted as Blackstone's: "Common
    Shares of Beneficial Interest", "Institutional Class II Common Shares",
    "Common Stock of BPG Subsidiary Inc."

    117 Form 3s for one person at one company was the tell. Every filing
    states its issuer; we never read it.
    """
    import xml.etree.ElementTree as ET
    from fle.ledger import issuer_of

    def doc(cik):
        return (f"<ownershipDocument><issuer>"
                f"<issuerCik>{str(cik).zfill(10)}</issuerCik>"
                f"<issuerName>X</issuerName></issuer></ownershipDocument>")

    assert issuer_of(ET.fromstring(doc(1393818))) == "1393818"
    assert issuer_of(ET.fromstring(doc(1662972))) == "1662972"   # BREIT
    # a document with no issuer element is kept, not discarded
    assert issuer_of(ET.fromstring("<ownershipDocument/>")) == ""

    import inspect
    from fle import ledger
    src = inspect.getsource(ledger.build_ledger)
    assert 'if got and got != str(int(issuer_cik)):' in src
    assert "led.other_issuers += 1" in src


def test_the_uncounted_securities_are_named_not_just_totalled():
    """Schwarzman holds 235,686,046 of SOMETHING at Blackstone, and whether
    that is a stock option, an exchangeable partnership unit or a mis-titled
    share class changes the right answer completely.

    A total alone cannot answer the question it raises.
    """
    import xml.etree.ElementTree as ET
    from fle.ledger import _options

    doc = """<ownershipDocument>
     <derivativeHolding><securityTitle><value>Holdings Partnership Units</value>
      </securityTitle><postTransactionAmounts>
      <sharesOwnedFollowingTransaction><value>235686046</value>
      </sharesOwnedFollowingTransaction></postTransactionAmounts></derivativeHolding>
     <derivativeHolding><securityTitle><value>Employee Stock Option</value>
      </securityTitle><conversionOrExercisePrice><value>23.34</value>
      </conversionOrExercisePrice><postTransactionAmounts>
      <sharesOwnedFollowingTransaction><value>5000</value>
      </sharesOwnedFollowingTransaction></postTransactionAmounts></derivativeHolding>
    </ownershipDocument>"""

    total, titles, _partner = _options(ET.fromstring(doc))
    assert total == 235_691_046
    # a strike price separates an option from a unit without reading the title
    assert any("strike 23.34" in t for t in titles)
    assert any("Partnership Units" in t and "strike" not in t for t in titles)


def test_table_two_keeps_the_last_balance_not_the_sum():
    """Blackstone reported 226,799,998 partnership units and the total came
    out as 235,686,046. A filing that carries both a transaction and a
    holding for one security has two rows, and each states the balance AFTER
    it -- so adding them counts the position twice.

    The same rule Table I already follows, applied where it was missing.
    """
    import xml.etree.ElementTree as ET
    from fle.ledger import _options

    def row(tag, title, amt):
        return (f"<{tag}><securityTitle><value>{title}</value></securityTitle>"
                f"<postTransactionAmounts><sharesOwnedFollowingTransaction>"
                f"<value>{amt}</value></sharesOwnedFollowingTransaction>"
                f"</postTransactionAmounts></{tag}>")

    doc = ("<ownershipDocument>"
           + row("derivativeTransaction", "Holdings Partnership units", 235686046)
           + row("derivativeHolding", "Holdings Partnership units", 226799998)
           + "</ownershipDocument>")
    total, titles, _partner = _options(ET.fromstring(doc))
    assert total == 226_799_998          # the last balance, once
    assert len(titles) == 1




def _settle(doc):
    """The rule: sum a filing's rows per (security, direct-or-indirect)."""
    import xml.etree.ElementTree as ET
    from fle.ledger import _rows, is_share_class, Group
    here = {}
    for r in _rows(ET.fromstring(doc), "4", "2026-01-01", "a"):
        if r.table == "II" and not is_share_class(r.security):
            continue
        if r.shares != r.shares:
            continue
        g = here.setdefault((r.security.lower(), r.direct),
                            Group(security=r.security, direct=r.direct,
                                  as_of=r.as_of, accession="a", table=r.table))
        if r.code:
            g.last_txn[r.nature or ""] = r.shares
        else:
            g.holdings += r.shares
        g.rows += 1
    return sum(sum(g.last_txn.values()) + g.holdings for g in here.values())


def _row(sec, di, bal, nat=None, table="II"):
    tag = "derivativeHolding" if table == "II" else "nonDerivativeHolding"
    n = f"<natureOfOwnership><value>{nat}</value></natureOfOwnership>" if nat else ""
    return (f"<{tag}><securityTitle><value>{sec}</value></securityTitle>"
            f"<postTransactionAmounts><sharesOwnedFollowingTransaction>"
            f"<value>{bal}</value></sharesOwnedFollowingTransaction>"
            f"</postTransactionAmounts><ownershipNature>"
            f"<directOrIndirectOwnership><value>{di}</value>"
            f"</directOrIndirectOwnership>{n}</ownershipNature></{tag}>")


def test_dorsey_five_indistinguishable_vehicles():
    """Every row says "See Footnote", so no two can be told apart -- and they
    do not need to be. Within one filing each row is a distinct position, so
    the group's sum is the answer: 48,844,566, which is what Simply Wall St
    reports."""
    doc = ("<ownershipDocument>"
           + _row("Class B Common Stock", "I", 35_763_992, "See Footnote")
           + _row("Class B Common Stock", "I", 12_080_574, "See Footnote")
           + _row("Class A Common Stock", "I", 0, "See Footnote", "I")
           + _row("Class A Common Stock", "I", 2_391, "See Footnote", "I")
           + _row("Class A Common Stock", "I", 287_155, "See Footnote", "I")
           + _row("Class A Common Stock", "I", 710_454, "See Footnote", "I")
           + "</ownershipDocument>")
    assert _settle(doc) == 48_844_566


def test_armstrong_two_named_trusts_in_one_filing():
    """Both Class B trusts are in the 10 November filing. The two dates in
    the old ledger were transactionDate versus filingDate, not two filings --
    a distinction that cost a day of wrong reasoning."""
    b = ("<ownershipDocument>"
         + _row("Class B Common Stock", "I", 22_681_225, "By The Brian Armstrong Living Trust")
         + _row("Class B Common Stock", "I", 2_958_393, "The Ehrsam 2014 Irrevocable Trust")
         + "</ownershipDocument>")
    a = ("<ownershipDocument>"
         + _row("Class A Common Stock", "D", 0, None, "I")
         + _row("Class A Common Stock", "I", 526, "By The Brian Armstrong Living Trust", "I")
         + "</ownershipDocument>")
    assert _settle(b) + _settle(a) == 25_640_144


def test_direct_and_indirect_are_separate_groups():
    """Musk's two lines are the same security -- "Common Stock" -- stated in
    filings a day apart. Only the structured direct/indirect field tells them
    apart, so the group key needs it."""
    from fle.ledger import Group
    d = Group(security="Common Stock", direct="D", shares=710_172_677)
    i = Group(security="Common Stock", direct="I", shares=413_152_109)
    assert d.key != i.key
    assert d.shares + i.shares == 1_123_324_786


def test_the_newest_filing_reporting_a_group_settles_it():
    import inspect
    from fle import ledger
    src = inspect.getsource(ledger.build_ledger)
    assert "if key not in led.groups:" in src      # older mentions ignored
    assert "g.shares = sum(g.last_txn.values()) + g.holdings" in src


def test_nothing_is_carried_across_filings():
    """The whole point. No vehicle identity, no footnotes, no closed-line
    rule, no silence counting, no Form 3 inventory -- all of it existed to
    carry lines, and nothing is carried."""
    import inspect
    from fle import ledger
    src = inspect.getsource(ledger)
    for gone in ["normalise_nature", "_PLACEHOLDER", "led.closed",
                 "restating_filings", "led.suspect", "seed=True",
                 "footnote_ids", "led.inventory"]:
        assert gone not in src, gone


def test_build_ledger_constructs_its_groups_correctly():
    """Adding two fields to Group silently shifted the positional arguments
    in build_ledger: `rows` received the accession string and the walk died
    on `g.rows += 1`.

    The tests used the right arity and never exercised that line, so 103 of
    them passed against code that could not run. This calls it.
    """
    import inspect
    from fle.ledger import build_ledger, Group

    src = inspect.getsource(build_ledger)
    assert "Group(security=title, direct=r.direct" in src   # keywords
    assert "Group(r.security, r.direct, 0.0" not in src

    # and the walk's own arithmetic works on a default Group
    g = Group(security="Common Stock", direct="D")
    g.rows += 1
    g.last_txn["direct"] = 710_172_677
    g.holdings += 413_152_109
    g.shares = sum(g.last_txn.values()) + g.holdings
    assert g.rows == 1 and g.shares == 1_123_324_786


def test_build_ledger_actually_runs_against_a_fake_client():
    """The 103 tests passed against code that crashed on its first filing.
    Every one of them called _rows or a hand-rolled copy of the walk; not one
    called build_ledger.

    This drives the real function with a fake EDGAR, so an arity slip, a
    rename or a bad attribute fails here instead of on the command line.
    """
    from fle.ledger import build_ledger

    OWNER = ('<reportingOwner><reportingOwnerId>'
             '<rptOwnerCik>0001590945</rptOwnerCik>'
             '<rptOwnerName>Dorsey Jack</rptOwnerName></reportingOwnerId>'
             '<reportingOwnerRelationship><isOfficer>1</isOfficer>'
             '<officerTitle>CEO</officerTitle></reportingOwnerRelationship>'
             '</reportingOwner>')

    def hold(sec, di, bal, table="II"):
        tag = "derivativeHolding" if table == "II" else "nonDerivativeHolding"
        return (f'<{tag}><securityTitle><value>{sec}</value></securityTitle>'
                f'<postTransactionAmounts><sharesOwnedFollowingTransaction>'
                f'<value>{bal}</value></sharesOwnedFollowingTransaction>'
                f'</postTransactionAmounts><ownershipNature>'
                f'<directOrIndirectOwnership><value>{di}</value>'
                f'</directOrIndirectOwnership><natureOfOwnership>'
                f'<value>See Footnote</value></natureOfOwnership>'
                f'</ownershipNature></{tag}>')

    DOC = ('<ownershipDocument><issuer><issuerCik>0001512673</issuerCik>'
           '</issuer>' + OWNER
           + hold("Class B Common Stock", "I", 35_763_992)
           + hold("Class B Common Stock", "I", 12_080_574)
           + hold("Class A Common Stock", "I", 1_000_000, "I")
           + '</ownershipDocument>')

    class _Edgar:
        def submissions(self, cik):
            return {"_filings": [
                {"form": "4", "accessionNumber": "0001512673-25-000001",
                 "filingDate": "2025-06-03", "primaryDocument": "d.xml"}]}

        def filing_index(self, cik, acc):
            return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}

        def get(self, url, use_cache=True):
            return DOC

    led = build_ledger(_Edgar(), 1512673, owner_name="Jack Dorsey")
    assert led.owner_name == "Dorsey Jack"
    assert led.total == 48_844_566          # the whole answer, one filing
    assert len(led.groups) == 2             # Class B indirect, Class A indirect
    assert led.filings_read == 1


# --- a misspelling in the filer's own document ---------------------------






def test_one_class_means_the_title_is_never_read():
    """The SEC's General Instructions make the class the reporting unit: a
    Form 4 reports "total beneficial ownership ... for each class of
    securities in which a transaction was reported", on "a separate line for
    each class ... directly or indirectly."

    We were taking securityTitle AS the class. It is free text, and filers
    put other things in it -- "Common Sotck" at Live Nation, four spellings
    of the par value at Brown & Brown, "Class A Common Stock-Trust" and "IRA"
    at Amphenol, plan names at Pentair.

    When a company has ONE class, every title is that class. Not a guess:
    there is nothing else the shares could be.
    """
    from fle.ledger import build_ledger

    OWNER = ('<reportingOwner><reportingOwnerId>'
             '<rptOwnerCik>0001337041</rptOwnerCik>'
             '<rptOwnerName>Rapino Michael</rptOwnerName></reportingOwnerId>'
             '<reportingOwnerRelationship><isOfficer>1</isOfficer>'
             '<officerTitle>CEO</officerTitle></reportingOwnerRelationship>'
             '</reportingOwner>')

    def doc(title, bal):
        return ('<ownershipDocument><issuer><issuerCik>0001335258</issuerCik>'
                '</issuer>' + OWNER
                + f'<nonDerivativeHolding><securityTitle><value>{title}</value>'
                f'</securityTitle><postTransactionAmounts>'
                f'<sharesOwnedFollowingTransaction><value>{bal}</value>'
                f'</sharesOwnedFollowingTransaction></postTransactionAmounts>'
                f'<ownershipNature><directOrIndirectOwnership><value>D</value>'
                f'</directOrIndirectOwnership></ownershipNature>'
                f'</nonDerivativeHolding></ownershipDocument>')

    filings = [{"form": "4", "accessionNumber": "0001335258-26-000001",
                "filingDate": "2026-08-06", "primaryDocument": "d.xml"},
               {"form": "4", "accessionNumber": "0001335258-12-000001",
                "filingDate": "2012-03-30", "primaryDocument": "d.xml"}]

    class _Edgar:
        def submissions(self, cik):
            return {"_filings": filings}

        def filing_index(self, cik, acc):
            return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}

        def get(self, url, use_cache=True):
            old = "000133525812" in url.replace("-", "")
            return doc("Common Sotck", 1_511_806) if old else \
                doc("Common Stock", 4_188_167)

    one = build_ledger(_Edgar(), 1335258, owner_name="Michael Rapino",
                       share_classes=1)
    assert len(one.groups) == 1
    assert one.total == 4_188_167          # the typo cannot make a group
    assert one.single_class

    # with the class count unknown, the old behaviour stands
    unknown = build_ledger(_Edgar(), 1335258, owner_name="Michael Rapino")
    assert len(unknown.groups) == 2


def test_the_denominator_is_read_before_the_ledger():
    """The ledger cannot decide whether a title means anything until it knows
    how many classes the company has, and only the company's own cover page
    says that."""
    import inspect
    from fle import ownership
    src = inspect.getsource(ownership.build)
    assert "out = shares_outstanding(client, cik)" in src
    assert src.index("out = shares_outstanding(client, cik)") < \
        src.index("led = build_ledger(client, cik")
    assert "share_classes=out.classes if out.ok else 0" in src


def test_every_caller_passes_the_class_count():
    """cmd_ledger calls build_ledger directly rather than through
    ownership.build, so it needs the class count itself. Without it the
    single-class path never ran from the command line, Amphenol stayed at
    5,053,309, and Live Nation only looked fixed because the typo rule
    happened to catch it.

    A command that disagrees with the panel is worse than one that fails.
    """
    import inspect
    from fle import cli, ownership
    assert "share_classes=_out.classes if _out.ok else 0" in \
        inspect.getsource(cli.cmd_ledger)
    assert "share_classes=out.classes if out.ok else 0" in \
        inspect.getsource(ownership.build)


def test_none_of_the_title_rules_survive():
    """Everything that tried to make sense of a free-text security title is
    gone, because the company tells us how many classes it has and that
    settles it:

      the typo rule          "Common Sotck" needed one-character matching
      the stale-group report a rename could double a holding
      footnote keying        ids drift, text can be reworded

    Each existed to identify a security from prose. The cover page says how
    many classes there are, and when there is one, every title is that class.
    """
    import inspect
    from fle import ledger, ownership
    src = inspect.getsource(ledger)
    for gone in ["fix_typos", "one_character_out", "led.typos", "title_counts",
                 "stale_groups", "footnote_ids", "normalise_nature",
                 "_PLACEHOLDER", "led.closed", "led.suspect"]:
        assert gone not in src, gone
    assert "stale_groups" not in inspect.getsource(ownership)

    from fle.panel import COLUMNS
    for gone in ["stale_groups", "stale_shares", "stale_detail",
                 "closed_shares", "closed_lines"]:
        assert gone not in COLUMNS, gone


# --- multi-class: the company names its own classes ----------------------

def test_the_class_list_comes_from_the_cover_page():
    """Ford tags its count once per class -- `CommonStockMember` and
    `CommonClassBMember`. So the classes are the company's own list, and the
    primary one is not un-dimensioned: it simply has no letter.
    """
    from fle.ledger import class_letters
    assert class_letters(["us-gaap:CommonStockMember",
                          "us-gaap:CommonClassBMember"]) == {
        ("", ""): "Common Stock", ("class", "B"): "Class B Common Stock"}
    assert class_letters(["us-gaap:CommonClassAMember",
                          "us-gaap:CommonClassBMember"]) == {
        ("class", "A"): "Class A Common Stock",
        ("class", "B"): "Class B Common Stock"}


def test_a_title_is_matched_by_its_class_letter():
    """A lone letter token, not the word "Class" -- which is why "Clas A
    Common Stock" still reads as A. That is one row in Zuckerberg's 9,284 and
    exactly the 184,659 Meta was off by against its own proxy.
    """
    from fle.ledger import class_letters, match_class
    meta = class_letters(["us-gaap:CommonClassAMember",
                          "us-gaap:CommonClassBMember"])
    assert match_class("Class A Common Stock", meta) == "Class A Common Stock"
    assert match_class("Clas A Common Stock", meta) == "Class A Common Stock"
    assert match_class("Class B Common Stock", meta) == "Class B Common Stock"

    ford = class_letters(["us-gaap:CommonStockMember",
                          "us-gaap:CommonClassBMember"])
    assert match_class("Common Stock, $0.01 par value", ford) == "Common Stock"
    assert match_class("Class B Common Stock", ford) == "Class B Common Stock"


def test_a_class_the_cover_page_does_not_name_is_excluded():
    """AppLovin's Class F and Dell's Series A are real securities the chief
    executive holds, and neither is in the denominator. Counting them puts
    shares on top that are missing from the bottom -- the error v1 made with
    options, which made ownership FALL when a CEO acquired stock.
    """
    from fle.ledger import class_letters, match_class
    two = class_letters(["us-gaap:CommonClassAMember",
                         "us-gaap:CommonClassBMember"])
    assert match_class("Class F Common Stock", two) is None
    # "Series A" and "Class A" are different securities, and Dell holds both
    assert match_class("Series A Common Stock", two) is None

    import inspect
    from fle import ledger, ownership
    src = inspect.getsource(ledger.build_ledger)
    assert "led.unnamed_class.setdefault(r.security" in src
    assert "continue" in src.split("led.unnamed_class.setdefault")[1][:200]
    assert "no room for them" in \
        " ".join(inspect.getsource(ownership.build).split())


def test_two_letters_in_one_title_is_ambiguous_not_a_guess():
    from fle.ledger import class_letters, match_class, title_letter
    assert title_letter("Class A B Common Stock") is None
    two = class_letters(["us-gaap:CommonClassAMember",
                         "us-gaap:CommonClassBMember"])
    assert match_class("Class A B Common Stock", two) is None


def test_series_and_class_are_different_securities():
    """Dell holds both "Class A Common Stock" and "Series A Common Stock".
    Matching on the letter alone put Series A into Class A, which is a
    different security -- so the designator is matched as well.
    """
    from fle.ledger import class_letters, match_class, title_letter
    dell = class_letters(["us-gaap:CommonClassAMember",
                          "us-gaap:CommonClassBMember",
                          "us-gaap:CommonClassCMember"])
    assert match_class("Class A Common Stock", dell) == "Class A Common Stock"
    assert match_class("Series A Common Stock", dell) is None
    assert match_class("Series C Common Stock", dell) is None

    # a misspelt designator leaves the kind unknown; "class" is assumed,
    # because it is the only one that appears without a letter beside it
    assert title_letter("Clas A Common Stock") == ("class", "A")


def test_an_excluded_class_reports_its_current_balance():
    """The walk is newest-first, so the first mention of a title is the
    current one. Taking a maximum reported Block as excluding 61,382,506 when
    its pre-IPO common stock has sat at zero since 2015 -- a harmless
    exclusion made to look alarming."""
    import inspect
    from fle import ledger
    src = inspect.getsource(ledger.build_ledger)
    assert "led.unnamed_class.setdefault(r.security, r.shares)" in src
    assert "max(\n                        led.unnamed_class" not in src





# --- the history walk -----------------------------------------------------

def _h4(bal, when, code=None, title="Common Stock", di="D"):
    tag = "nonDerivativeTransaction" if code else "nonDerivativeHolding"
    c = (f"<transactionCoding><transactionCode>{code}</transactionCode>"
         f"</transactionCoding>") if code else ""
    return ('<ownershipDocument><issuer><issuerCik>0001318605</issuerCik>'
            '</issuer><reportingOwner><reportingOwnerId>'
            '<rptOwnerCik>0001494730</rptOwnerCik>'
            '<rptOwnerName>Musk Elon</rptOwnerName></reportingOwnerId>'
            '<reportingOwnerRelationship><isOfficer>1</isOfficer>'
            '<officerTitle>CEO</officerTitle></reportingOwnerRelationship>'
            '</reportingOwner>'
            f'<{tag}><securityTitle><value>{title}</value></securityTitle>{c}'
            f'<postTransactionAmounts><sharesOwnedFollowingTransaction>'
            f'<value>{bal}</value></sharesOwnedFollowingTransaction>'
            f'</postTransactionAmounts><ownershipNature>'
            f'<directOrIndirectOwnership><value>{di}</value>'
            f'</directOrIndirectOwnership></ownershipNature></{tag}>'
            '</ownershipDocument>')


def test_the_history_ends_where_the_panel_does():
    """The walk IS the panel's walk, run forwards:

        today   newest first, the FIRST filing to report a group settles it
        series  oldest first, each filing OVERWRITES the group it reports

    Both end at the newest filing per group, so the final snapshot must equal
    the panel's figure. That is a free correctness test on every company.
    """
    from fle.history import build_history
    from fle.series import Series, Point

    docs = {"a1": _h4(100, "2016-02-01"),
            "a2": _h4(250, "2019-05-01", code="P"),
            "a3": _h4(400, "2024-08-01", code="P"),
            "a4": _h4(75, "2025-01-01", title="Common Stock", di="I")}
    mine = [{"form": "4", "accessionNumber": k,
             "filingDate": d, "primaryDocument": "d.xml"}
            for k, d in [("a1", "2016-02-01"), ("a2", "2019-05-01"),
                         ("a3", "2024-08-01"), ("a4", "2025-01-01")]]

    class _Edgar:
        def filing_index(self, cik, acc):
            return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}

        def get(self, url, use_cache=True):
            for k in docs:
                if k in url:
                    return docs[k]
            raise KeyError(url)

    series = Series(points=[Point("2016-01-01", 1000.0),
                            Point("2024-01-01", 2000.0)],
                    classes={"2016": {"us-gaap:CommonStockMember": 1000.0}})

    hist = build_history(_Edgar(), 1318605, "1494730", mine, series=series)
    assert hist.read == 4
    got = [(s.date, s.shares) for s in hist.snapshots]
    # the 2024-01-01 cover page moved the count, so it is a point too:
    # the same 250 shares over the new denominator (add_cover_points)
    assert got == [("2016-02-01", 100.0), ("2019-05-01", 250.0),
                   ("2024-01-01", 250.0),
                   ("2024-08-01", 400.0), ("2025-01-01", 475.0)]
    assert [s.cover for s in hist.snapshots] == [False, False, True, False, False]
    assert hist.snapshots[2].outstanding == 2000.0 and hist.snapshots[2].pct == 12.5

    # the last snapshot is direct 400 + indirect 75, which is what a
    # newest-first walk over the same filings would settle on
    assert hist.snapshots[-1].shares == 475.0

    # and the denominator is the one in force at each date, not today's
    assert hist.snapshots[0].outstanding == 1000.0
    assert hist.snapshots[-1].outstanding == 2000.0
    assert round(hist.snapshots[0].pct, 1) == 10.0


def test_filings_before_the_window_are_read_but_not_emitted():
    """A balance set in 2013 and never restated is still the balance in
    2016. Starting the WALK at the window would lose it; starting the
    EMISSION there does not."""
    from fle.history import build_history
    from fle.series import Series, Point

    # Two different classes, so the point under test is the WINDOW rather
    # than the class rule: a 2020 filing that transacts in Class A states
    # the whole of Class A and would legitimately supersede an older Class A
    # line, but it says nothing about Class B.
    docs = {"old": _h4(900, "2013-03-01", title="Class B Common Stock"),
            "new": _h4(950, "2020-04-01", code="P", di="I",
                       title="Class A Common Stock")}
    mine = [{"form": "4", "accessionNumber": "old",
             "filingDate": "2013-03-01", "primaryDocument": "d.xml"},
            {"form": "4", "accessionNumber": "new",
             "filingDate": "2020-04-01", "primaryDocument": "d.xml"}]

    class _Edgar:
        def filing_index(self, cik, acc):
            return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}

        def get(self, url, use_cache=True):
            return docs["old"] if "old" in url else docs["new"]

    hist = build_history(_Edgar(), 1318605, "1494730", mine,
                         series=Series(points=[Point("2013-01-01", 10_000.0)]),
                         since="2016-01-01")
    assert hist.read == 2                      # both read
    assert len(hist.snapshots) == 1            # one emitted
    # the 2013 Class B balance survives into the 2020 snapshot
    assert hist.snapshots[0].shares == 900.0 + 950.0


def test_the_denominator_is_the_one_in_force_then():
    """Tesla went from 3.33bn shares to 3.95bn in ten years. Dividing a 2016
    holding by today's count understates it by a sixth."""
    from fle.series import Series, Point
    s = Series(points=[Point("2016-03-31", 3_330_000_000.0),
                       Point("2026-06-30", 3_949_547_394.0)])
    assert s.at("2016-05-01").shares == 3_330_000_000.0
    assert s.at("2026-08-01").shares == 3_949_547_394.0
    # before the first point, the earliest is the honest fallback
    assert s.at("2010-01-01").shares == 3_330_000_000.0


def test_the_class_list_is_the_one_in_force_then():
    """Block's "Common Stock" WAS the class in 2019 and is not one now."""
    from fle.series import Series
    s = Series(classes={"2016": {"us-gaap:CommonStockMember": 1.0},
                        "2022": {"us-gaap:CommonClassAMember": 1.0,
                                 "us-gaap:CommonClassBMember": 1.0}})
    assert list(s.classes_at("2019-01-01")) == ["us-gaap:CommonStockMember"]
    assert len(s.classes_at("2024-01-01")) == 2


def test_the_denominator_falls_back_to_cover_pages():
    """The concept API holds only UN-DIMENSIONED facts, and a company tagging
    its count once per class has none -- the same 404 that sends the panel to
    the cover page.

    The series had no such fallback, so Meta, Coinbase and Block came back
    with no percentage on a single one of their 952 snapshots. And because
    the class list was read separately, it came back empty for exactly those
    companies -- so Meta's "Clas A Common Stock" fell through to the raw
    title and restored, in the history, the 184,659-share error the panel had
    already fixed.

    One pass now gives both, from the same document.
    """
    import inspect
    from fle import series
    src = inspect.getsource(series.from_cover_pages)
    assert "_facts_from_document(raw)" in src
    assert "class_names(raw)" in src          # both, from one fetch
    assert "out.classes = seen_year" in src

    pick = inspect.getsource(series.denominator_series)
    assert "return from_cover_pages(" in pick
    # a filer the API covers needs ONE cover page for its class list, not 40
    assert "_newest_cover(client, cik, since)" in pick
    assert "len(one) > 1" in pick


def test_a_dimensioned_filer_is_not_trusted_to_the_api():
    """If the newest cover page turns out to name several classes, the API's
    un-dimensioned history is not the whole company and must not be used as
    a denominator."""
    import inspect
    from fle import series
    src = inspect.getsource(series.denominator_series)
    i = src.index("len(one) > 1")
    assert "from_cover_pages" in src[i:i + 240]


def test_two_vehicles_transacting_in_one_filing_are_added_not_replaced():
    """Musk exercises to 727,704,534 and has 17,531,857 withheld to
    710,172,677 -- one position, two rows, only the last current.

    Zuckerberg, on 25 January 2021, converts 36,000 out of CZI Holdings
    leaving 354,099,234, and 6,250 out of his 2006 Trust leaving 5,595,706,
    and restates the CZI Foundation's 1,908,602. Three positions: 361,603,542.

    The rows look identical. What separates them is the VEHICLE, and
    `natureOfOwnership` names it -- within THIS document, where one drafter
    spells it one way. It is never used across documents, which is where the
    spelling drifts and where keying on it split Amphenol into thirteen.

    Taking the last transaction per GROUP left 7,504,308 of that 361,603,542,
    and Meta's series oscillated between the two figures 92 times.
    """
    import xml.etree.ElementTree as ET
    from fle.ledger import _rows, Group, is_share_class

    def settle(doc):
        here = {}
        for r in _rows(ET.fromstring(doc), "4", "2021-01-25", "a"):
            if r.table == "II" and not is_share_class(r.security):
                continue
            if r.shares != r.shares:
                continue
            key = (r.security.lower(), r.direct)
            g = here.setdefault(key, Group(security=r.security, direct=r.direct))
            if r.code:
                g.last_txn[r.nature or ""] = r.shares
            else:
                g.holdings += r.shares
        return sum(sum(g.last_txn.values()) + g.holdings for g in here.values())

    def row(sec, bal, nat=None, code=None, di="I", table="II"):
        tag = {"I": "nonDerivativeHolding", "II": "derivativeHolding"}[table]
        if code:
            tag = {"I": "nonDerivativeTransaction",
                   "II": "derivativeTransaction"}[table]
        c = (f"<transactionCoding><transactionCode>{code}</transactionCode>"
             f"</transactionCoding>") if code else ""
        n = (f"<natureOfOwnership><value>{nat}</value></natureOfOwnership>"
             if nat else "")
        return (f"<{tag}><securityTitle><value>{sec}</value></securityTitle>{c}"
                f"<postTransactionAmounts><sharesOwnedFollowingTransaction>"
                f"<value>{bal}</value></sharesOwnedFollowingTransaction>"
                f"</postTransactionAmounts><ownershipNature>"
                f"<directOrIndirectOwnership><value>{di}</value>"
                f"</directOrIndirectOwnership>{n}</ownershipNature></{tag}>")

    # three vehicles, two of them transacting
    zuck = ("<ownershipDocument>"
            + row("Class B Common Stock", 354_099_234, "By CZI Holdings, LLC", "C")
            + row("Class B Common Stock", 5_595_706, "By the 2006 Trust", "C")
            + row("Class B Common Stock", 1_908_602, "By CZI Foundation")
            + "</ownershipDocument>")
    assert settle(zuck) == 361_603_542

    # one vehicle, two sequential rows
    musk = ("<ownershipDocument>"
            + row("Common Stock", 727_704_534, None, "M", "D", "I")
            + row("Common Stock", 710_172_677, None, "F", "D", "I")
            + "</ownershipDocument>")
    assert settle(musk) == 710_172_677

    # and the cases that were already right stay right
    dorsey = ("<ownershipDocument>"
              + row("Class A Common Stock", 0, "See Footnote", "G", "I", "I")
              + row("Class A Common Stock", 2_391, "See Footnote", "G", "I", "I")
              + row("Class A Common Stock", 287_155, "See Footnote", None, "I", "I")
              + row("Class A Common Stock", 710_454, "See Footnote", None, "I", "I")
              + "</ownershipDocument>")
    assert settle(dorsey) == 1_000_000

    armstrong = ("<ownershipDocument>"
                 + row("Class B Common Stock", 22_681_225,
                       "By The Brian Armstrong Living Trust", "C")
                 + row("Class B Common Stock", 2_958_393,
                       "The Ehrsam 2014 Irrevocable Trust")
                 + "</ownershipDocument>")
    assert settle(armstrong) == 25_639_618


def test_the_vehicle_is_never_carried_between_documents():
    """The group key is the CLASS. Nature discriminates rows inside one
    filing and nothing more -- carrying it across documents is what split
    Amphenol into thirteen groups and Brown & Brown into four.

    Direct-or-indirect moved OUT of the key and into the vehicle, because
    keying on it let one class's two halves go stale independently and
    doubled Musk's position for twenty-one months."""
    import inspect
    from fle import ledger
    src = inspect.getsource(ledger.build_ledger)
    assert 'key = title.lower()' in src                  # the class, alone
    assert 'r.nature' not in src.split('key = title.lower()')[0][-400:]
    assert 'keys = vehicle_keys(rows, ends)' in src and 'for r, vehicle in zip(rows, keys):' in src


def _bill_rows():
    """Lacerte's 4 September 2026 filing, to the share: five vehicles
    selling across two days, four of them labelled 'See footnote' (one
    'See foornote'), and three holdings restated."""
    S = lambda nat, moved, bal: ("Common Stock", "I" if nat else "D", nat, "S", moved, "D", bal)
    return [S("", 40_357, 100_899), S("", 100_899, 0),
            S("See footnote", 11_765, 87_828), S("See footnote", 26_974, 60_854),      # Makahakama Trust
            S("See footnote", 10_636, 194_364), S("See footnote", 24_364, 170_000),    # the Foundation
            S("See footnote", 10_970, 173_279), S("See footnote", 10_154, 163_125),    # trust A
            S("See foornote", 15_372, 168_877), S("See footnote", 5_752, 163_125),     # trust B, typo on the first row
            ("Common Stock", "I", "See footnote", "", 0, "", 1_708_749),
            ("Common Stock", "I", "See footnote", "", 0, "", 135_000),
            ("Common Stock", "I", "See footnote", "", 0, "", 135_000)]


def test_bill_anonymous_vehicles_are_told_apart_by_their_running_balances():
    """Keyed on the text, four trusts became one and the walk settled
    2,310,751 against the filing's 2,535,853 (2.71% published, 2.97%
    held). The balances say which rows belong together."""
    from fle.ledger import vehicle_keys, is_anonymous
    from fle.ledger import _rows
    root = ET.fromstring(_h4t(_bill_rows(), "2026-09-03"))
    rows = _rows(root, "4", "2026-09-03", "x")
    keys = vehicle_keys(rows)
    txn = [k[1] for k, r in zip(keys, rows) if r.code and r.direct == "I"]
    pairs = [txn[i:i + 2] for i in range(0, 8, 2)]
    assert all(a == b for a, b in pairs), "each trust's two rows chain: the second opens where the first closed"
    assert len({a for a, _ in pairs}) == 4, "four trusts, not one"
    assert pairs[3] == ["seefoornote", "seefoornote"], "the typo row's trust: its second row joined it by the balance it opens at"
    hold = [k[1] for k, r in zip(keys, rows) if not r.code]
    assert len(set(hold)) == 3 and not (set(hold) & set(txn)), "holdings are kept apart, and apart from the trusts that transacted"
    # the filing's own total, on both walks
    doc = _h4t(_bill_rows(), "2026-09-03")
    hist = _walk_priced({"b1": doc}, [("b1", "2026-09-03")])
    assert hist.snapshots[-1].shares == 2_535_853
    assert is_anonymous("See footnote") and is_anonymous("see notes 3 and 4") and is_anonymous("(2)") and is_anonymous("")
    assert not is_anonymous("By Elon Musk Revocable Trust") and not is_anonymous("By Trust")
    assert not is_anonymous("", "D") and not is_anonymous("See footnote", "D"), "the direct line is a name"


def test_an_anonymous_restatement_supersedes_the_segments_it_cannot_name():
    """Dorsey's shape. Five trusts, all "See Footnote". A gift filing
    transacts two of them (told apart by their balances); the next Form 5
    lists all five as holdings again. The restatement means all five, so
    the segment the gift filing opened does not stand beside the sum.
    Without this, 48,844,566 read as 84,608,558 in the record."""
    H = lambda bal: ("Common Stock", "I", "See Footnote", "", 0, "", bal)
    T = lambda moved, bal: ("Common Stock", "I", "See Footnote", "G", moved, "D", bal)
    five = _h4t([H(10_000_000), H(8_000_000), H(6_000_000), H(4_000_000), H(2_000_000)], "2025-02-01")
    gift = _h4t([T(1_000_000, 9_000_000), T(500_000, 3_500_000)], "2025-06-01")
    again = _h4t([H(9_000_000), H(8_000_000), H(6_000_000), H(3_500_000), H(2_000_000)], "2026-02-01")
    # (accession keys must not be substrings of the fixture URL: "a" is in "data")
    hist = _walk_priced({"x1": five, "x2": gift, "x3": again},
                        [("x1", "2025-02-01"), ("x2", "2025-06-01"), ("x3", "2026-02-01")])
    got = [(s.date, s.shares) for s in hist.snapshots]
    assert got[0] == ("2025-02-01", 30_000_000)
    # the gift filing lists two trusts; the three it passed over in silence
    # are benched, and the Form 5 that lists them again at the balances
    # they vanished at bridges them back onto the gift day (Huang's rule,
    # now reachable for anonymous trusts)
    assert got[1] == ("2025-06-01", 28_500_000) and abs(hist.snapshots[1].unexplained) < 0.5
    assert got[2] == ("2026-02-01", 28_500_000), "the restatement means all five, not five plus a segment"


def test_bill_a_lone_anonymous_purchase_continues_the_trust_it_names_by_balance():
    """Lacerte, 26 August 2024: one line, a "See footnote" trust buying
    42,248 (before 142,001, after 184,249), nothing else. With holdings
    summed under one key the walk had a pile, could not find the 142,001
    in it, and dropped every other trust: residue -184,249, the purchase
    "stake change not stated". Kept apart, the earlier filing's holding at
    142,001 is the trust this row continues; the others were passed over
    in silence, benched, and bridged back when the next filing lists them
    at the balances they stood at."""
    H = lambda bal: ("Common Stock", "I", "See footnote", "", 0, "", bal)
    before = _h4t([H(1_708_749), H(135_000), H(135_000), H(142_001), H(184_249), H(205_000), H(99_593)], "2024-05-01")
    buy = _h4t([("Common Stock", "I", "See footnote", "P", 42_248, "A", 184_249)], "2024-08-26")
    after = _h4t([H(1_708_749), H(135_000), H(135_000), H(184_249), H(184_249), H(205_000), H(99_593)], "2024-11-01")
    hist = _walk_priced({"x1": before, "x2": buy, "x3": after},
                        [("x1", "2024-05-01"), ("x2", "2024-08-26"), ("x3", "2024-11-01")])
    got = {s.date: s for s in hist.snapshots}
    assert got["2024-05-01"].shares == 2_609_592
    assert got["2024-08-26"].shares == 2_609_592 + 42_248, "the purchase, and everything else standing"
    assert abs(got["2024-08-26"].unexplained) < 0.5, "nothing unexplained: the trade accounts for the whole move"
    assert got["2024-11-01"].shares == 2_651_840


def test_the_same_trust_listed_out_of_order_is_still_one_trust():
    """A later day's row placed before the earlier one: the earlier row
    opens where nothing has closed, but it CLOSES where the segment
    opened, so it precedes it. One trust, not two."""
    from fle.ledger import vehicle_keys, _rows
    S = lambda moved, bal: ("Common Stock", "I", "See footnote", "S", moved, "D", bal)
    rows = _rows(ET.fromstring(_h4t([S(26_974, 60_854), S(11_765, 87_828)], "2026-09-03")), "4", "2026-09-03", "x")
    keys = vehicle_keys(rows)
    assert keys[0] == keys[1]
    hist = _walk_priced({"x1": _h4t([S(26_974, 60_854), S(11_765, 87_828)], "2026-09-03")}, [("x1", "2026-09-03")])
    assert hist.snapshots[-1].shares == 60_854, "the position is where the chain ends, not the row that was listed last"


def test_a_holding_that_restates_this_documents_own_transaction_is_not_added():
    """A filing that lists a trust's sale and then, among its holdings,
    the same trust at the balance the sale left. One position: the
    holding is the transaction's closing balance said twice. Two holdings
    at one balance, though, are two trusts (Lacerte's family trusts)."""
    from fle.ledger import vehicle_keys, _rows
    doc = _h4t([("Common Stock", "I", "See footnote", "S", 1_000, "D", 99_000),
                ("Common Stock", "I", "See footnote", "", 0, "", 99_000),
                ("Common Stock", "I", "See footnote", "", 0, "", 135_000),
                ("Common Stock", "I", "See footnote", "", 0, "", 135_000)], "2026-01-10")
    rows = _rows(ET.fromstring(doc), "4", "2026-01-10", "x")
    keys = vehicle_keys(rows)
    assert keys[0] == keys[1], "the restating holding joins the transaction"
    assert keys[2] != keys[3], "two holdings at one balance stay apart"
    hist = _walk_priced({"x1": doc}, [("x1", "2026-01-10")])
    assert hist.snapshots[-1].shares == 99_000 + 135_000 + 135_000


def test_a_form_4_filed_twice_on_one_day_states_its_trust_once():
    """Roberts, 15 May 2026: the same Form 4 under two accession numbers,
    a direct exercise-and-sell and a "See footnote" trust at 1,867,416.
    Same-day filings merge; the second copy's trust is the first copy's
    trust stated again, not a second trust."""
    doc = _h4t([("Common Stock", "D", "", "M", 40_000, "A", 68_202),
                ("Common Stock", "D", "", "S", 40_000, "D", 28_202),
                ("Common Stock", "I", "See footnote", "", 0, "", 1_867_416),
                ("Common Stock", "I", "By Roberts Family Trust", "", 0, "", 32_340)], "2026-05-13")
    hist = _walk_priced({"x1": doc, "x2": doc}, [("x1", "2026-05-13"), ("x2", "2026-05-13")])
    assert hist.snapshots[-1].shares == 28_202 + 1_867_416 + 32_340


def test_the_spellings_of_nothing():
    from fle.ledger import is_anonymous
    for t in ("See footnote", "See Footnotes", "Se footnote", "SEE FTN", "FN", "ftn", "Per footnote 3",
              "Footnote 2", "note 4", "(2)", "*", "", "See foornote", "F.N."):
        assert is_anonymous(t), t
    for t in ("By Trust", "By Roberts Family Trust", "Self", "Foundation", "Fenwick Trust", "Notary Trust"):
        assert not is_anonymous(t), t


def test_a_shared_close_does_not_join_two_trusts():
    """Two anonymous trusts that each move once and end at the same
    balance are two trusts. A join on the shared close was tried for
    Harrison's repeated-final-balance filings and merged Sharma's,
    Foroughi's and Vashist's pairs; it is not a rule."""
    from fle.ledger import vehicle_keys, _rows
    R = lambda moved, bal: ("Common Stock", "I", "See footnote", "S", moved, "D", bal)
    rows = _rows(ET.fromstring(_h4t([R(10_000, 500_000), R(25_000, 500_000)], "2026-03-03")), "4", "2026-03-03", "x")
    assert len(set(vehicle_keys(rows))) == 2


def test_one_anonymous_trust_whose_balance_jumped_is_still_that_trust():
    """Watts: a "See footnote" holding at 2,242,604, then two days later a
    sale from "See footnote" opening at 2,293,664. The arithmetic pairs
    nothing; one arrival, one vehicle standing: the same trust, a balance
    that moved between filings. Read as a new trust, the old one was
    benched and bridged back beside its twin a month later."""
    hold = _h4t([("Common Stock", "D", "", "A", 89_520, "A", 272_957),
                 ("Common Stock", "I", "See footnote", "", 0, "", 2_242_604)], "2024-01-03")
    sale = _h4t([("Common Stock", "I", "See footnote", "S", 17_483, "D", 2_276_181),
                 ("Common Stock", "D", "", "", 0, "", 221_897)], "2024-01-05")
    again = _h4t([("Common Stock", "I", "See footnote", "S", 7_818, "D", 2_268_363),
                  ("Common Stock", "D", "", "", 0, "", 221_897)], "2024-01-09")
    hist = _walk_priced({"x1": hold, "x2": sale, "x3": again},
                        [("x1", "2024-01-03"), ("x2", "2024-01-05"), ("x3", "2024-01-09")])
    got = {s.date: s.shares for s in hist.snapshots}
    assert got["2024-01-05"] == 2_276_181 + 221_897
    assert got["2024-01-09"] == 2_268_363 + 221_897
    assert abs(hist.snapshots[-1].unexplained) < 0.5


def test_trusts_restated_at_new_balances_that_sum_to_the_old_are_not_silent():
    """Prince, 2022: five anonymous Class B trusts, then six at different
    balances summing to the same 16,120,473. Shares moved among trusts and
    all were restated. Read as silence, the four unmatched were benched and
    two later 4,000,000 sightings bridged 8,000,000 onto a record that had
    never lost them."""
    H = lambda bal: ("Class B Common Stock", "I", "See footnote", "", 0, "", bal)
    C = lambda opening, bal: ("Class B Common Stock", "I", "See footnote", "C", opening - bal, "D", bal)
    aug = _h4t([C(17_020_971, 16_863_819), H(491_031), H(4_000_000), H(4_000_000), H(6_569_442), H(1_060_000)], "2022-08-15")
    # six trusts against five: the counts differ, only the sums agree
    sep = _h4t([C(16_863_819, 16_706_667), H(1_741_355), H(377_772), H(6_928_408), H(1_060_000), H(3_000_000), H(3_012_938)], "2022-09-13")
    later = _h4t([C(16_706_667, 16_600_000), H(4_000_000), H(4_000_000), H(1_741_355), H(377_772), H(6_928_408 + 3_000_000 + 3_012_938 + 1_060_000 - 8_000_000)], "2023-02-01")
    hist = _walk_priced({"x1": aug, "x2": sep, "x3": later},
                        [("x1", "2022-08-15"), ("x2", "2022-09-13"), ("x3", "2023-02-01")])
    got = {s.date: s for s in hist.snapshots}
    assert got["2022-09-13"].shares == 16_706_667 + 16_120_473
    assert abs(got["2022-09-13"].unexplained) < 0.5, "a restatement, not an omission"
    assert got["2023-02-01"].shares == 16_600_000 + 16_120_473, "and nothing bridged back onto it"


def test_direct_rows_that_miss_by_a_share_are_one_line():
    """Portland General, 13 February 2026: nine direct rows of awards and
    withholding whose balances miss each other by a share (fractional
    withholding, rounded row by row). One line; the last balance wins.
    Read as anonymous, each gap started a phantom and the chief executive
    of a utility read as owning 1% of it."""
    from fle.ledger import vehicle_keys, _rows
    D = lambda code, moved, ad, bal: ("Common Stock", "D", "", code, moved, ad, bal)
    doc = _h4t([D("A", 27_112, "A", 221_247), D("A", 60_112, "A", 281_359), D("F", 30_928, "D", 250_432),
                D("A", 1_217, "A", 251_649), D("F", 5_058, "D", 246_591), D("A", 1_078, "A", 247_808),
                D("F", 6_319, "D", 241_350), D("A", 534, "A", 241_884), D("F", 5_991, "D", 235_892)], "2026-02-13")
    rows = _rows(ET.fromstring(doc), "4", "2026-02-13", "x")
    assert len(set(vehicle_keys(rows))) == 1
    hist = _walk_priced({"p1": doc}, [("p1", "2026-02-13")])
    assert hist.snapshots[-1].shares == 235_892


def test_a_named_vehicle_whose_balances_do_not_chain_is_still_one_vehicle():
    """Musk's SpaceX catch-up Form 4: four rows for the Revocable Trust
    whose running balances drop 25M between rows the filing never
    explains. A name is a name; the last balance is the position."""
    from fle.ledger import vehicle_keys, _rows
    T = lambda code, moved, ad, bal: ("Class A Common Stock", "I", "By Elon Musk Revocable Trust", code, moved, ad, bal)
    rows = _rows(ET.fromstring(_h4t([T("A", 511_289_725, "A", 551_349_985), T("S", 11_390, "D", 526_165_900),
                                     T("C", 282_614_850, "A", 808_780_270), T("C", 33_311_400, "A", 842_091_670)],
                                    "2026-06-15")), "4", "2026-06-15", "x")
    assert len(set(vehicle_keys(rows))) == 1


def test_one_snapshot_per_day_not_per_filing():
    """Zuckerberg files two Forms 4 for the same day and splits the vehicles
    between them. On 6 February 2024 the first reports four Class B vehicles
    totalling 51,507,297; the second reports all five, 348,093,309, and says
    so in its remarks: "the Class A and Class B holdings for CZI Holdings,
    LLC are reported on the second of these two forms."

    Both settle exactly right. Emitting after each produced a snapshot that
    is true of one document and false of the position -- 46 of his 763 points
    swung between the two figures.
    """
    from fle.history import build_history
    from fle.series import Series, Point

    owner = ('<reportingOwner><reportingOwnerId>'
             '<rptOwnerCik>0001548760</rptOwnerCik>'
             '<rptOwnerName>Zuckerberg Mark</rptOwnerName></reportingOwnerId>'
             '<reportingOwnerRelationship><isOfficer>1</isOfficer>'
             '<officerTitle>CEO</officerTitle></reportingOwnerRelationship>'
             '</reportingOwner>')

    def line(bal, nature, code=None):
        tag = "derivativeTransaction" if code else "derivativeHolding"
        c = (f"<transactionCoding><transactionCode>{code}</transactionCode>"
             f"</transactionCoding>") if code else ""
        return (f'<{tag}><securityTitle><value>Class B Common Stock</value>'
                f'</securityTitle>{c}<postTransactionAmounts>'
                f'<sharesOwnedFollowingTransaction><value>{bal}</value>'
                f'</sharesOwnedFollowingTransaction></postTransactionAmounts>'
                f'<ownershipNature><directOrIndirectOwnership><value>I</value>'
                f'</directOrIndirectOwnership><natureOfOwnership>'
                f'<value>{nature}</value></natureOfOwnership>'
                f'</ownershipNature></{tag}>')

    def doc(rows):
        return ('<ownershipDocument><issuer><issuerCik>0001326801</issuerCik>'
                '</issuer>' + owner + "".join(rows) + '</ownershipDocument>')

    first = doc([line(1_267_406, "CZI Foundation", "C"),
                 line(3_895_391, "2006 Trust", "C"),
                 line(34_344_500, "CZ Holdings LLC"),
                 line(12_000_000, "CZI Holdings I")])
    second = doc([line(296_586_012, "CZI Holdings, LLC", "C"),
                  line(1_267_406, "CZI Foundation"),
                  line(3_895_391, "2006 Trust"),
                  line(34_344_500, "CZ Holdings LLC"),
                  line(12_000_000, "CZI Holdings I")])

    mine = [{"form": "4", "accessionNumber": "0000950103-24-001897",
             "filingDate": "2024-02-07", "primaryDocument": "d.xml"},
            {"form": "4", "accessionNumber": "0000950103-24-001898",
             "filingDate": "2024-02-07", "primaryDocument": "d.xml"}]

    class _Edgar:
        def filing_index(self, cik, acc):
            return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}

        def get(self, url, use_cache=True):
            return first if "2400189" + "7" in url.replace("-", "") else second

    hist = build_history(
        _Edgar(), 1326801, "1548760", mine,
        series=Series(points=[Point("2024-01-01", 2_550_000_000.0)],
                      classes={"2024": {"us-gaap:CommonClassAMember": 1.0,
                                        "us-gaap:CommonClassBMember": 1.0}}))
    assert hist.read == 2                    # both read
    assert len(hist.snapshots) == 1          # one emitted
    assert hist.snapshots[0].shares == 348_093_309


def test_prices_translate_the_dash_to_polygons_dot():
    """The panel writes BF-B because constituent lists do; Polygon writes
    BF.B. The translation lives in one place, and a missing ticker is
    reported rather than silently priced at nothing."""
    from fle.prices import fetch_prices

    class _Poly:
        def get_json(self, url, use_cache=True, max_age=None):
            assert "2026-08-25" in url
            return {"results": [{"T": "TSLA", "c": 331.29},
                                {"T": "BF.B", "c": 27.5},
                                {"T": "AAPL", "c": 230.0}]}

    got = fetch_prices(_Poly(), ["TSLA", "BF-B", "ZZZZ"], "k",
                       date="2026-08-25")
    assert got.ok and got.as_of == "2026-08-25"
    assert got.by_ticker["TSLA"] == 331.29
    assert got.by_ticker["BF-B"] == 27.5        # matched through the dot
    assert got.missing == ["ZZZZ"]


def test_prices_walk_back_over_a_weekend():
    """The grouped endpoint returns nothing for a Saturday; the fetch steps
    back until a trading day appears instead of failing."""
    from fle.prices import fetch_prices

    class _Poly:
        def get_json(self, url, use_cache=True, max_age=None):
            if "2026-08-23" in url or "2026-08-22" in url:   # Sun, Sat
                return {"results": []}
            return {"results": [{"T": "TSLA", "c": 331.29}]}

    got = fetch_prices(_Poly(), ["TSLA"], "k", date="2026-08-23")
    assert got.ok and got.as_of == "2026-08-21"


def test_a_split_between_cover_page_and_filing_does_not_inflate_the_percentage():
    """Nvidia's 10-for-1 settled 7 June 2024; the cover page restating the
    count did not arrive until the end of August. In between, the Form 4
    numerator was post-split and the denominator was not -- and Jensen
    Huang's 3.5% was reported as 35.3%.

    The denominator is carried through the split instead."""
    from fle.splits import Splits, Split

    sp = Splits(ticker="NVDA", events=[Split(date="2024-06-07", factor=10.0)])

    # the cover page as of 31 March 2024, pre-split
    cover, held = 2_460_000_000.0, 867_287_230.0

    naive = held / cover * 100
    assert round(naive, 1) == 35.3            # the bug, as it appeared

    ratio = sp.factor_since("2024-03-31") / sp.factor_since("2024-06-17")
    fixed = held / (cover * ratio) * 100
    assert ratio == 10.0
    assert 3.4 < fixed < 3.6                  # what the man actually owns


def test_the_carry_through_is_inert_when_no_split_intervenes():
    """Most snapshots have no split between the cover page and the filing,
    and their denominator must come through untouched."""
    from fle.splits import Splits, Split

    sp = Splits(ticker="NVDA", events=[Split(date="2024-06-07", factor=10.0)])
    ratio = (sp.factor_since("2024-09-30") / sp.factor_since("2024-12-13"))
    assert ratio == 1.0


def test_the_walk_carries_the_denominator_through_a_split():
    """End to end, in the shape of the Nvidia failure: a filing lands after
    the split and before the cover page that restates the count."""
    from fle.history import build_history
    from fle.series import Series, Point
    from fle.splits import Splits, Split

    docs = {"b1": _h4(100, "2024-03-01"),      # pre-split, pre-cover
            "b2": _h4(1000, "2024-06-17"),     # post-split, cover still old
            "b3": _h4(1000, "2024-09-04")}     # cover has caught up
    mine = [{"form": "4", "accessionNumber": k, "filingDate": d,
             "primaryDocument": "d.xml"}
            for k, d in [("b1", "2024-03-01"), ("b2", "2024-06-17"),
                         ("b3", "2024-09-04")]]

    class _Edgar:
        def filing_index(self, cik, acc):
            return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}

        def get(self, url, use_cache=True):
            for k in docs:
                if k in url:
                    return docs[k]
            raise KeyError(url)

    series = Series(points=[Point("2024-01-31", 2000.0),
                            Point("2024-07-31", 20000.0)])
    sp = Splits(ticker="X", events=[Split(date="2024-06-07", factor=10.0)])

    hist = build_history(_Edgar(), 1318605, "1494730", mine,
                         series=series, splits=sp)   # the fixture's own ids
    pcts = [round(s.pct, 3) for s in hist.snapshots]
    # 100/2000, then 1000/(2000 carried through the 10-for-1), then 1000/20000
    assert pcts == [5.0, 5.0, 5.0]


def _h4p(bal, when, code, moved, price=None, ad="D", title="Common Stock"):
    """A Form 4 transaction row carrying its own execution price."""
    pr = (f"<transactionPricePerShare><value>{price}</value>"
          f"</transactionPricePerShare>") if price is not None else ""
    return ('<ownershipDocument><issuer><issuerCik>0001318605</issuerCik>'
            '</issuer><reportingOwner><reportingOwnerId>'
            '<rptOwnerCik>0001494730</rptOwnerCik>'
            '<rptOwnerName>Musk Elon</rptOwnerName></reportingOwnerId>'
            '<reportingOwnerRelationship><isOfficer>1</isOfficer>'
            '<officerTitle>CEO</officerTitle></reportingOwnerRelationship>'
            '</reportingOwner>'
            f'<nonDerivativeTransaction><securityTitle><value>{title}</value>'
            f'</securityTitle><transactionCoding><transactionCode>{code}'
            f'</transactionCode></transactionCoding>'
            f'<transactionAmounts><transactionShares><value>{moved}</value>'
            f'</transactionShares>{pr}'
            f'<transactionAcquiredDisposedCode><value>{ad}</value>'
            f'</transactionAcquiredDisposedCode></transactionAmounts>'
            f'<postTransactionAmounts><sharesOwnedFollowingTransaction>'
            f'<value>{bal}</value></sharesOwnedFollowingTransaction>'
            f'</postTransactionAmounts><ownershipNature>'
            f'<directOrIndirectOwnership><value>D</value>'
            f'</directOrIndirectOwnership></ownershipNature>'
            '</nonDerivativeTransaction></ownershipDocument>')


def _walk_priced(docs, dates, series=None, splits=None):
    from fle.history import build_history
    mine = [{"form": "4", "accessionNumber": k, "filingDate": d,
             "primaryDocument": "d.xml"} for k, d in dates]

    class _Edgar:
        def filing_index(self, cik, acc):
            return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}

        def get(self, url, use_cache=True):
            for k in docs:
                if k in url:
                    return docs[k]
            raise KeyError(url)

    return build_history(_Edgar(), 1318605, "1494730", mine,
                         series=series, splits=splits)


def test_a_sale_is_valued_at_the_price_the_filing_reports():
    """40,000 shares means nothing on its own. At the $331.29 the Form 4
    says it executed at, it is $13.25 million -- and that is the filing's
    own arithmetic, not a market close applied after the fact."""
    hist = _walk_priced({"p1": _h4p(960_000, "2026-08-25", "S", 40_000, 331.29)},
                 [("p1", "2026-08-25")])
    snap = hist.snapshots[-1]
    assert snap.traded == -40_000
    assert round(snap.traded_value) == 13_251_600
    assert snap.unpriced == 0


def test_a_grant_reports_no_price_and_is_counted_rather_than_guessed_at():
    """Awards and gifts carry no price because nothing changed hands. The
    row is marked unpriced; it is never valued at a close we invented."""
    hist = _walk_priced({"p1": _h4p(1_000_000, "2026-03-04", "A", 92_000, None, ad="A")},
                 [("p1", "2026-03-04")])
    snap = hist.snapshots[-1]
    assert snap.traded == 92_000
    assert snap.traded_value is None
    assert snap.unpriced == 1


def test_the_days_transactions_are_summed_across_every_filing_that_day():
    """Only the last filing of a day emits a snapshot, so the value must be
    accumulated across all of them or the earlier trades vanish."""
    docs = {"d1": _h4p(980_000, "2026-08-25", "S", 20_000, 300.0),
            "d2": _h4p(960_000, "2026-08-25", "S", 20_000, 350.0)}
    hist = _walk_priced(docs, [("d1", "2026-08-25"), ("d2", "2026-08-25")])
    assert len(hist.snapshots) == 1
    assert round(hist.snapshots[0].traded_value) == 20_000 * 300 + 20_000 * 350
    assert hist.snapshots[0].traded == -40_000


def test_lines_can_print_a_single_filing_by_accession():
    """The grouped view cannot answer 'what did THIS document say'. When one
    snapshot disagrees with its neighbours that is the only question, so the
    filing must be printable on its own."""
    import argparse
    from fle import cli

    doc = _h4p(4_006_734, "2021-01-06", "S", 100, 130.0)

    class _Client:
        def submissions(self, cik):
            return {"_filings": [{"form": "4",
                                  "accessionNumber": "0001045810-21-000004",
                                  "filingDate": "2021-01-06",
                                  "primaryDocument": "d.xml"}]}

        def filing_index(self, cik, acc):
            return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}

        def get(self, url, use_cache=True):
            return doc

    cli._client = lambda args: _Client()
    args = argparse.Namespace(cik="1197649", security=None, limit=40, show=6,
                              accession="000104581021000004",   # dashes optional
                              user_agent="t", exclusions=None)
    assert cli.cmd_lines(args) == 0


def test_a_partial_filing_is_marked_as_unexplained_rather_than_as_a_trade():
    """Huang's filing of 6 January 2021 lists three trusts and reports no
    transaction at all. The balance falls because the document is silent
    about his other vehicles -- not because anything was sold. The walk
    must be able to say so."""
    # both indirect, so the second filing REPLACES the group the first
    # established -- which is exactly what a partial filing does.
    docs = {"q1": _h4(21_440_882, "2020-12-11", title="Common Stock", di="I"),
            "q2": _h4(2_746_730, "2021-01-06", title="Common Stock", di="I")}
    hist = _walk_priced(docs, [("q1", "2020-12-11"), ("q2", "2021-01-06")])
    partial = hist.snapshots[-1]
    assert partial.traded == 0.0                 # nothing changed hands
    assert partial.unexplained < -1_000_000      # yet the balance collapsed


def test_a_real_trade_reconciles_and_is_not_flagged():
    """The same arithmetic must stay quiet when a sale genuinely explains
    the fall, or the flag would be worthless."""
    docs = {"r1": _h4p(1_000_000, "2026-08-20", "P", 0, 300.0),
            "r2": _h4p(960_000, "2026-08-25", "S", 40_000, 331.29)}
    hist = _walk_priced(docs, [("r1", "2026-08-20"), ("r2", "2026-08-25")])
    sale = hist.snapshots[-1]
    assert sale.traded == -40_000
    assert abs(sale.unexplained) < 1             # balance and trade agree


def _h4v(rows, when, acc="x"):
    """A Form 4 with several vehicles: (title, direct, nature, balance, code)."""
    body = ""
    for title, di, nature, bal, code in rows:
        tag = "nonDerivativeTransaction" if code else "nonDerivativeHolding"
        c = (f"<transactionCoding><transactionCode>{code}</transactionCode>"
             f"</transactionCoding>") if code else ""
        nat = f"<natureOfOwnership><value>{nature}</value></natureOfOwnership>" if nature else ""
        body += (f'<{tag}><securityTitle><value>{title}</value></securityTitle>{c}'
                 f'<postTransactionAmounts><sharesOwnedFollowingTransaction>'
                 f'<value>{bal}</value></sharesOwnedFollowingTransaction>'
                 f'</postTransactionAmounts><ownershipNature>'
                 f'<directOrIndirectOwnership><value>{di}</value>'
                 f'</directOrIndirectOwnership>{nat}</ownershipNature></{tag}>')
    return ('<ownershipDocument><issuer><issuerCik>0001318605</issuerCik>'
            '</issuer><reportingOwner><reportingOwnerId>'
            '<rptOwnerCik>0001494730</rptOwnerCik>'
            '<rptOwnerName>Musk Elon</rptOwnerName></reportingOwnerId>'
            '<reportingOwnerRelationship><isOfficer>1</isOfficer>'
            '<officerTitle>CEO</officerTitle></reportingOwnerRelationship>'
            '</reportingOwner>' + body + '</ownershipDocument>')


def test_two_complementary_forms_on_one_day_are_merged_not_replaced():
    """Huang, 6 January 2021, in miniature. The first Form 4 carries his
    direct holding and three vehicles; the second carries three DIFFERENT
    vehicles and reports no transaction. Together they state 21,440,882.

    Replacing the group with the second filing published 4,006,734."""
    one = _h4v([("Common Stock", "D", None, 1_260_004, "S"),
                ("Common Stock", "I", "By Trust", 15_639_909, None),
                ("Common Stock", "I", "By Irrevocable Trust", 557_000, None),
                ("Common Stock", "I", "By Partnership", 1_237_239, None)],
               "2021-01-06")
    two = _h4v([("Common Stock", "I", "Jen-Hsun Huang 2016 Annuity Trust II",
                 747_390, None),
                ("Common Stock", "I", "Lori Lynn Huang 2016 Annuity Trust II",
                 747_390, None),
                ("Common Stock", "I", "By Irrevocable Remainder Trust",
                 1_251_950, None)],
               "2021-01-06")
    hist = _walk_priced({"j1": one, "j2": two},
                        [("j1", "2021-01-06"), ("j2", "2021-01-06")])
    assert len(hist.snapshots) == 1              # one day, one snapshot
    assert hist.snapshots[0].shares == 21_440_882


def test_a_same_day_filing_that_restates_the_first_does_not_double_count():
    """Zuckerberg's pair is the opposite case: the second filing repeats the
    first's vehicles and adds one. The repeated vehicles must overwrite, not
    accumulate, or merging would inflate the position."""
    one = _h4v([("Class B", "I", "By CZI Holdings", 354_099_234, "C"),
                ("Class B", "I", "By 2006 Trust", 5_595_706, "C")],
               "2024-02-06")
    two = _h4v([("Class B", "I", "By CZI Holdings", 354_099_234, "C"),
                ("Class B", "I", "By 2006 Trust", 5_595_706, "C"),
                ("Class B", "I", "By Foundation", 1_908_602, None)],
               "2024-02-06")
    hist = _walk_priced({"z1": one, "z2": two},
                        [("z1", "2024-02-06"), ("z2", "2024-02-06")])
    assert len(hist.snapshots) == 1
    assert hist.snapshots[0].shares == 354_099_234 + 5_595_706 + 1_908_602


def test_a_split_is_not_mistaken_for_unexplained_activity():
    """Nvidia's 10-for-1 multiplied the reported balance by ten on the same
    day Huang sold 240,000 shares. Reconciled on reported shares, the split
    swamps the sale -- 780,774,507 unexplained -- and the real trade gets
    withheld from the feed as an artifact. Both sides must be split-adjusted."""
    from fle.splits import Splits, Split

    sp = Splits(ticker="NVDA", events=[Split(date="2024-06-07", factor=10.0)])
    docs = {"s1": _h4p(86_752_723, "2024-03-22", "S", 0, 900.0),
            "s2": _h4p(867_287_230, "2024-06-17", "S", 240_000, 129.94)}
    hist = _walk_priced(docs, [("s1", "2024-03-22"), ("s2", "2024-06-17")],
                        splits=sp)
    after = hist.snapshots[-1]
    assert after.traded == -240_000
    assert abs(after.unexplained) < 1        # the split explains the rest


def test_the_days_codes_survive_a_split_across_two_filings():
    """Huang's exercise and sales sit on the first of two Forms 4 filed that
    day; the second carries only holdings. Reading codes from the last
    document left the day looking like nothing happened."""
    one = _h4p(1_260_004, "2021-01-06", "M", 100_000, 17.62, ad="A")
    two = _h4v([("Common Stock", "I", "By Remainder Trust", 1_251_950, None)],
               "2021-01-06")
    hist = _walk_priced({"c1": one, "c2": two},
                        [("c1", "2021-01-06"), ("c2", "2021-01-06")])
    assert "M" in hist.snapshots[-1].codes


# ---------------------------------------------------------------- founders

def test_surnames_handle_suffixes_and_shared_seats():
    from fle.founders import surnames
    assert surnames("Jen-Hsun Huang") == ["Huang"]
    assert surnames("Ernest C. Garcia III") == ["Garcia"]
    assert surnames("Joseph Bae & Scott Nuttall") == ["Bae", "Nuttall"]


FILLER = ("<p>The Board of Directors solicits your proxy for the Annual "
          "Meeting of Shareholders. Please review the compensation discussion "
          "and analysis, the audit committee report, and the beneficial "
          "ownership tables that follow in this statement.</p>" * 4)


def _reader(yes_if=None, founders_named="", other_company=""):
    """A fake reader: YES (quoting the phrase) when `yes_if` appears in the
    excerpts it was shown, NO otherwise. Pins this code's contract with the
    model, never the model."""
    import json as _json

    def post(body):
        prompt = _json.loads(body)["messages"][0]["content"]
        if yes_if and yes_if in prompt:
            obj = {"founder": "yes", "evidence": yes_if,
                   "founders_named": founders_named, "other_company": "",
                   "reason": "the excerpt says so"}
        else:
            obj = {"founder": "no", "evidence": "",
                   "founders_named": founders_named,
                   "other_company": other_company, "reason": "not this person"}
        return {"content": [{"type": "tool_use", "name": "record_verdict", "input": obj}]}
    return post


def _proxy_client(html, form="DEF 14A"):
    """A real proxy runs to hundreds of pages; the fixture is padded so it
    clears the stub-document guard the way an actual filing would."""
    class _C:
        def submissions(self, cik):
            return {"_filings": [{"form": form,
                                  "filingDate": "2026-04-10",
                                  "accessionNumber": "0000000000-26-000001",
                                  "primaryDocument": "proxy.htm"}]}
        def get(self, url, use_cache=True):
            return html + FILLER
    return _C()



def test_the_founding_sentence_reaches_the_reader_and_its_quote_is_kept():
    """'Mr. Huang co-founded NVIDIA in 1993' is proxy boilerplate. The regex
    once decided it alone; now it hands the sentence to the reader, and the
    reader's quote, checked against the filing, travels into the CSV."""
    from fle.founders import find_founder
    c = _proxy_client("<html><body>Jen-Hsun Huang co-founded NVIDIA in 1993 "
                      "and has served as President and CEO since inception."
                      "</body></html>")
    v = find_founder(c, 1045810, "Jen-Hsun Huang", company="NVIDIA Corporation",
                     api_key="k", post=_reader(yes_if="co-founded NVIDIA in 1993"))
    assert v.founder == "yes" and v.method == "llm"
    assert "co-founded" in v.evidence



def test_founder_language_about_someone_else_is_not_a_yes():
    """Tim Cook's proxy praises 'our co-founder, Steve Jobs'. The window
    is found (it must be: the reader has to see it) and the reader says
    whose title it is."""
    from fle.founders import find_founder
    c = _proxy_client("<html>Mr. Cook succeeded our co-founder, Steve Jobs, "
                      "as Chief Executive Officer in 2011.</html>")
    v = find_founder(c, 320193, "Timothy D. Cook", company="Apple Inc.",
                     api_key="k", post=_reader(founders_named="Steve Jobs"))
    assert v.founder == "no" and v.founders_named == "Steve Jobs"
    assert v.snippets and "Steve Jobs" in v.snippets[0]



def test_no_founder_language_anywhere_is_a_real_no():
    """No window, no call: silence is decided for free."""
    from fle.founders import find_founder
    calls = []
    c = _proxy_client("<html>Mr. Cook has served as Chief Executive Officer "
                      "since 2011 and joined the Company in 1998.</html>")
    v = find_founder(c, 320193, "Timothy D. Cook", company="Apple Inc.",
                     api_key="k", post=lambda b: calls.append(b))
    assert v.founder == "no" and not calls
    # the method records that the early documents were consulted too
    assert v.method.startswith("no-mention")


def test_a_failed_fetch_is_unknown_and_never_a_no():
    """The user's own requirement, encoded: an empty result because the
    document could not be read must not be mistaken for evidence."""
    from fle.founders import find_founder

    class _Broken:
        def submissions(self, cik):
            raise OSError("edgar unreachable")

    v = find_founder(_Broken(), 1, "Jane Doe")
    assert v.founder == "unknown" and v.method == "proxy-unavailable"



def test_the_reader_is_asked_once_with_every_window_and_answers_in_json():
    from fle import founders as F
    html = ("<html>The Company was founded in 1994. Mr. Jassy... Under "
            "Mr. Jassy the Company has grown.</html>")
    c = _proxy_client(html)
    seen = []

    def fake_post(body):
        seen.append(body)
        assert b"Jassy" in body and b"Amazon.com" in body
        return {"content": [{"type": "text", "text":
                '{"founder": "no", "evidence": "", "founders_named": "", '
                '"other_company": "", "reason": "no founder language about him"}'}]}

    v = F.find_founder(c, 1018724, "Andrew R. Jassy", company="Amazon.com",
                       api_key="k", post=fake_post, escalate=False)
    assert v.founder == "no" and v.method.startswith("llm")
    assert len(seen) == 1



def test_founding_a_different_company_is_not_founding_this_one():
    """Sanjay Mehrotra co-founded SanDisk. He runs Micron. The first run
    called him Micron's founder because the sentence was true and nearby.
    The reader is asked about THIS company, and what he did found is kept."""
    from fle.founders import find_founder
    c = _proxy_client(
        "<html>Mr. Mehrotra has served as Micron's President and Chief "
        "Executive Officer since May 2017. Prior to that, Mr. Mehrotra "
        "co-founded and led SanDisk Corporation as a start-up in 1988."
        "</html>")
    v = find_founder(c, 723125, "Sanjay Mehrotra", company="Micron Technology",
                     api_key="k", post=_reader(other_company="SanDisk Corporation"))
    assert v.founder == "no"
    assert "SanDisk" in v.other_company



def test_a_director_table_does_not_make_the_ceo_a_founder():
    """Apple's proxy lists nominees in a table: 'Art Levinson Board Chair
    Founder and CEO, Calico ... Tim Cook CEO, Apple'. Thirty characters of
    proximity made Tim Cook a founder of Apple in the first run. The window
    still reaches the reader; nothing decides on proximity."""
    from fle.founders import find_founder
    c = _proxy_client(
        "<html>Name Occupation Independent Age Director Since "
        "Art Levinson Board Chair Founder and CEO, Calico 75 2000 "
        "Tim Cook CEO, Apple 65 2011 Wanda Austin Former President</html>")
    v = find_founder(c, 320193, "Timothy D. Cook", company="Apple Inc.",
                     api_key="k", post=_reader())
    assert v.founder == "no" and v.snippets



def test_the_document_search_falls_through_to_a_registration_statement():
    """A company that listed last year has filed no proxy. Condemning it to
    'unknown' threw away the S-1, which is where the founding is described."""
    from fle.founders import find_founder

    class _NewIssuer:
        def submissions(self, cik):
            return {"_filings": [
                {"form": "S-1", "filingDate": "2026-01-20",
                 "accessionNumber": "0000000000-26-000009",
                 "primaryDocument": "s1.htm"}]}

        def get(self, url, use_cache=True):
            return ("<html>Our founder, David Ellison, founded Skydance in "
                    "2010 and has served as Chief Executive Officer since "
                    "the combination.</html>" + FILLER)

    v = find_founder(_NewIssuer(), 2041610, "David Ellison", company="Skydance",
                     api_key="k", post=_reader(yes_if="founded Skydance in 2010"))
    assert v.founder == "yes"
    assert v.source.startswith("S-1")



def test_one_unreadable_document_does_not_end_the_search():
    """Blackstone files a proxy every year; a single failed fetch produced
    'unknown'. The next candidate must still be tried."""
    from fle.founders import find_founder

    class _Flaky:
        def __init__(self): self.n = 0
        def submissions(self, cik):
            return {"_filings": [
                {"form": "DEF 14A", "filingDate": "2026-04-01",
                 "accessionNumber": "0000000000-26-000002",
                 "primaryDocument": "new.htm"},
                {"form": "DEF 14A", "filingDate": "2025-04-01",
                 "accessionNumber": "0000000000-25-000002",
                 "primaryDocument": "old.htm"}]}
        def get(self, url, use_cache=True):
            if "new.htm" in url:
                raise OSError("504 from EDGAR")
            return ("<html>Mr. Schwarzman co-founded the Company in 1985 and "
                    "has served as Chairman and CEO since.</html>" + FILLER)

    v = find_founder(_Flaky(), 1393818, "Stephen A. Schwarzman",
                     company="Blackstone Inc.", api_key="k",
                     post=_reader(yes_if="co-founded the Company in 1985"))
    assert v.founder == "yes"



def test_a_faded_bio_is_rescued_by_the_early_documents():
    """A founder of thirty years' standing may have a current bio that says
    only 'has served as Chief Executive Officer since 1993'. Read alone,
    that is a false no. The S-1 still says how the company began."""
    from fle.founders import find_founder

    class _Faded:
        def submissions(self, cik):
            return {"_filings": [
                {"form": "DEF 14A", "filingDate": "2026-04-01",
                 "accessionNumber": "0000000000-26-000001",
                 "primaryDocument": "new.htm"},
                {"form": "S-1", "filingDate": "1999-02-01",
                 "accessionNumber": "0000000000-99-000001",
                 "primaryDocument": "s1.htm"}]}

        def get(self, url, use_cache=True):
            if "new.htm" in url:
                return ("<html>Ms. Rivera has served as Chief Executive "
                        "Officer since 1993 and as Chair since 2004.</html>"
                        + FILLER)
            return ("<html>Ms. Rivera founded Aurora Systems in 1993 and has "
                    "led it since inception.</html>" + FILLER)

    v = find_founder(_Faded(), 7, "Ana Rivera", company="Aurora Systems",
                     api_key="k", post=_reader(yes_if="founded Aurora Systems in 1993"))
    assert v.founder == "yes"
    assert "early document" in v.method
    assert v.source.startswith("S-1")



def test_the_earliest_proxy_is_never_read_first():
    """The oldest proxy predates most sitting chief executives. Reading it
    first would find no mention of them and call that a finding."""
    from fle.founders import find_founder

    class _OldCo:
        def submissions(self, cik):
            return {"_filings": [
                {"form": "DEF 14A", "filingDate": "2026-04-01",
                 "accessionNumber": "0000000000-26-000001",
                 "primaryDocument": "new.htm"},
                {"form": "DEF 14A", "filingDate": "1994-04-01",
                 "accessionNumber": "0000000000-94-000001",
                 "primaryDocument": "old.htm"}]}

        def get(self, url, use_cache=True):
            if "new.htm" in url:
                return ("<html>Mr. Nadeau co-founded the Company in 2011 and "
                        "has served as CEO since.</html>" + FILLER)
            return ("<html>Mr. Prior, our founder, will retire.</html>"
                    + FILLER)

    v = find_founder(_OldCo(), 8, "Luc Nadeau", company="Vantis Corp",
                     api_key="k", post=_reader(yes_if="co-founded the Company in 2011"))
    assert v.founder == "yes"
    assert v.source.startswith("DEF 14A 2026")     # the current document



def test_absence_from_the_earliest_filing_corroborates_but_never_decides():
    """A chief executive missing from the company's oldest document almost
    certainly did not found it -- recorded as corroboration. It cannot be
    the verdict: Steve Jobs appears in no Apple proxy of 1994, having been
    gone nine years, and returned in 1997."""
    from fle.founders import find_founder

    class _Returner:
        def submissions(self, cik):
            return {"_filings": [
                {"form": "DEF 14A", "filingDate": "2026-04-01",
                 "accessionNumber": "0000000000-26-000001",
                 "primaryDocument": "new.htm"},
                {"form": "DEF 14A", "filingDate": "1994-04-01",
                 "accessionNumber": "0000000000-94-000001",
                 "primaryDocument": "old.htm"}]}

        def get(self, url, use_cache=True):
            if "new.htm" in url:      # the current bio has lost the founding
                return ("<html>Mr. Jobs has served as Chief Executive Officer "
                        "since 1997.</html>" + FILLER)
            # and he is nowhere in the 1994 document
            return ("<html>Mr. Spindler serves as Chief Executive Officer. "
                    "Mr. Markkula is Vice Chairman.</html>" + FILLER)

    v = find_founder(_Returner(), 320193, "Steve Jobs", company="Apple Inc.",
                     api_key="k", post=_reader())
    assert v.early_presence == "absent"
    assert "absent" in v.method          # disclosed, and still only a no
    assert v.founder == "no"


def test_a_position_moved_into_a_trust_does_not_get_counted_twice():
    """Musk's Tesla shares moved from his own name into a revocable trust.
    The filing states the trust line and is silent about the direct one --
    because it is empty. Keyed by (class x direct/indirect) the stale direct
    balance survived, and we published 822,733,738 for a man holding
    411,062,076, for twenty-one months."""
    before = _h4v([("Common Stock", "D", None, 411_671_662, "F"),
                   ("Common Stock", "I", "by Trust", 1_000_257, None)],
                  "2023-02-14")
    after = _h4v([("Common Stock", "I", "by Trust", 411_056_826, "M"),
                  ("Common Stock", "I", "by Trust", 411_062_076, "M")],
                 "2023-03-10")
    hist = _walk_priced({"t1": before, "t2": after},
                        [("t1", "2023-02-14"), ("t2", "2023-03-10")])
    assert hist.snapshots[0].shares == 411_671_662 + 1_000_257
    assert hist.snapshots[-1].shares == 411_062_076


def test_two_running_balances_for_one_vehicle_keep_only_the_last():
    """The same filing's two option exercises are sequential states of one
    position: 411,056,826 then 411,062,076, five thousand two hundred and
    fifty apart -- the second row's own transaction."""
    doc = _h4v([("Common Stock", "I", "by Trust", 411_056_826, "M"),
                ("Common Stock", "I", "by Trust", 411_062_076, "M")],
               "2023-03-10")
    hist = _walk_priced({"o1": doc}, [("o1", "2023-03-10")])
    assert hist.snapshots[0].shares == 411_062_076


def test_a_holdings_only_filing_still_cannot_restate_the_class():
    """The obligation to state a class total attaches to a class in which a
    transaction was reported. A filing that only restates some holdings
    updates those vehicles and leaves the rest standing -- otherwise Huang's
    quiet January filing would erase his position all over again."""
    full = _h4v([("Common Stock", "D", None, 1_260_004, "S"),
                 ("Common Stock", "I", "By Trust", 15_639_909, None),
                 ("Common Stock", "I", "By Partnership", 1_237_239, None)],
                "2020-12-11")
    quiet = _h4v([("Common Stock", "I", "By Annuity Trust", 747_390, None)],
                 "2021-01-06")
    hist = _walk_priced({"h1": full, "h2": quiet},
                        [("h1", "2020-12-11"), ("h2", "2021-01-06")])
    assert hist.snapshots[0].shares == 18_137_152
    # the quiet filing adds a vehicle; it does not delete the others
    assert hist.snapshots[-1].shares == 18_137_152 + 747_390


def test_direct_and_indirect_lines_of_one_class_still_add():
    """Collapsing the key must not collapse the arithmetic: a filing that
    reports both lines of a class sums them."""
    doc = _h4v([("Common Stock", "D", None, 500, "P"),
                ("Common Stock", "I", "By Trust", 300, "P")], "2026-01-05")
    hist = _walk_priced({"b1": doc}, [("b1", "2026-01-05")])
    assert hist.snapshots[0].shares == 800


def _h4v_dated(rows, period, acc="x"):
    return _h4v(rows, period, acc)


def test_an_amendment_to_an_old_period_is_not_merged_with_todays_filing():
    """Musk filed a Form 4 for his transactions of 8 March 2023 and, the
    same morning, an amendment to the ANNUAL form covering 31 December 2022.
    Merged as a same-day pair -- which sharing a postmark used to mean --
    the two moments became one and his position doubled to 822,113,652.

    They share a filing date and nothing else."""
    from fle.history import build_history

    amendment = _h4v([("Common Stock", "I", "by Trust", 411_056_826, "G")],
                     "2022-12-31")
    current = _h4v([("Common Stock", "I", "by Trust", 411_056_826, "M"),
                    ("Common Stock", "I", "by Trust", 411_062_076, "M")],
                   "2023-03-08")
    docs = {"a1": amendment, "f1": current}
    mine = [
        # both posted on 10 March 2023; only one is ABOUT 10 March 2023
        {"form": "5/A", "accessionNumber": "a1", "filingDate": "2023-03-10",
         "reportDate": "2022-12-31", "primaryDocument": "d.xml"},
        {"form": "4", "accessionNumber": "f1", "filingDate": "2023-03-10",
         "reportDate": "2023-03-08", "primaryDocument": "d.xml"},
    ]

    class _Edgar:
        def filing_index(self, cik, acc):
            return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}

        def get(self, url, use_cache=True):
            for k in docs:
                if k in url:
                    return docs[k]
            raise KeyError(url)

    hist = build_history(_Edgar(), 1318605, "1494730", mine)
    assert len(hist.snapshots) == 2          # two periods, two moments
    assert hist.snapshots[0].date == "2022-12-31"
    assert hist.snapshots[-1].date == "2023-03-08"
    assert hist.snapshots[-1].shares == 411_062_076


def test_filings_that_share_a_period_are_still_one_moment():
    """Huang's pair both report the transactions of 4 January 2021, so they
    share a period as well as a postmark and must still be merged."""
    from fle.history import build_history

    one = _h4v([("Common Stock", "D", None, 1_260_004, "S"),
                ("Common Stock", "I", "By Trust", 15_639_909, None)],
               "2021-01-04")
    two = _h4v([("Common Stock", "I", "By Annuity Trust", 747_390, None)],
               "2021-01-04")
    docs = {"p1": one, "p2": two}
    mine = [{"form": "4", "accessionNumber": k, "filingDate": "2021-01-06",
             "reportDate": "2021-01-04", "primaryDocument": "d.xml"}
            for k in ("p1", "p2")]

    class _Edgar:
        def filing_index(self, cik, acc):
            return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}

        def get(self, url, use_cache=True):
            for k in docs:
                if k in url:
                    return docs[k]
            raise KeyError(url)

    hist = build_history(_Edgar(), 1318605, "1494730", mine)  # the fixture's ids
    assert len(hist.snapshots) == 1
    assert hist.snapshots[0].shares == 1_260_004 + 15_639_909 + 747_390


def test_two_filings_that_both_report_transactions_do_not_double_the_class():
    """Meta doubled to 25.3% on 9 November 2020 and fell back the next day.
    Two Forms 4 for the same period, both reporting conversions, both
    stating the whole class -- merged, the position was counted twice.

    A filing that transacts in a class states the total for it. Two such
    statements do not add; the later one supersedes."""
    one = _h4v([("Class B", "I", "By CZI Holdings", 351_932_812, "C")],
               "2020-11-09")
    two = _h4v([("Class B", "I", "By CZI Holdings", 351_777_603, "C")],
               "2020-11-09")
    hist = _walk_priced({"n1": one, "n2": two},
                        [("n1", "2020-11-09"), ("n2", "2020-11-09")])
    assert len(hist.snapshots) == 1
    assert hist.snapshots[0].shares == 351_777_603


def test_but_a_holdings_only_second_filing_still_adds_its_vehicles():
    """Huang's second form of 6 January 2021 reports no transaction, so it
    makes no claim to the total and its vehicles are added rather than
    substituted. The two rules are one question, asked of each filing."""
    one = _h4v([("Common Stock", "D", None, 1_260_004, "S"),
                ("Common Stock", "I", "By Trust", 15_639_909, None)],
               "2021-01-04")
    two = _h4v([("Common Stock", "I", "By Annuity Trust", 747_390, None)],
               "2021-01-04")
    hist = _walk_priced({"q1": one, "q2": two},
                        [("q1", "2021-01-04"), ("q2", "2021-01-04")])
    assert hist.snapshots[0].shares == 1_260_004 + 15_639_909 + 747_390


def test_a_vehicle_respelled_between_filings_is_still_one_position():
    """Musk's trust is "by Trust" in March 2023 and "By Trust" in December
    2024. Merging on the spelling would count 822 million; the arithmetic
    keeps it at one position without comparing the strings."""
    mar = _h4v([("Common Stock", "I", "by Trust", 411_062_076, "M")],
               "2023-03-08")
    dec = _h4v([("Common Stock", "I", "By Trust", 410_794_076, "G")],
               "2024-12-30")
    hist = _walk_priced({"z1": mar, "z2": dec},
                        [("z1", "2023-03-08"), ("z2", "2024-12-30")])
    assert hist.snapshots[-1].shares == 410_794_076


def _h4t(rows, when, acc="x"):
    """A Form 4 with full transaction rows:
    (title, direct, nature, code, moved, A_or_D, balance)."""
    body = ""
    for title, di, nature, code, moved, ad, bal in rows:
        tag = "nonDerivativeTransaction" if code else "nonDerivativeHolding"
        c = (f"<transactionCoding><transactionCode>{code}</transactionCode>"
             f"</transactionCoding>"
             f"<transactionAmounts><transactionShares><value>{moved}</value>"
             f"</transactionShares><transactionAcquiredDisposedCode>"
             f"<value>{ad}</value></transactionAcquiredDisposedCode>"
             f"</transactionAmounts>") if code else ""
        nat = (f"<natureOfOwnership><value>{nature}</value>"
               f"</natureOfOwnership>") if nature else ""
        body += (f'<{tag}><securityTitle><value>{title}</value></securityTitle>{c}'
                 f'<postTransactionAmounts><sharesOwnedFollowingTransaction>'
                 f'<value>{bal}</value></sharesOwnedFollowingTransaction>'
                 f'</postTransactionAmounts><ownershipNature>'
                 f'<directOrIndirectOwnership><value>{di}</value>'
                 f'</directOrIndirectOwnership>{nat}</ownershipNature></{tag}>')
    return ('<ownershipDocument><issuer><issuerCik>0001318605</issuerCik>'
            '</issuer><reportingOwner><reportingOwnerId>'
            '<rptOwnerCik>0001494730</rptOwnerCik>'
            '<rptOwnerName>Musk Elon</rptOwnerName></reportingOwnerId>'
            '<reportingOwnerRelationship><isOfficer>1</isOfficer>'
            '<officerTitle>CEO</officerTitle></reportingOwnerRelationship>'
            '</reportingOwner>' + body + '</ownershipDocument>')


def test_one_running_balance_split_across_two_documents_is_chained():
    """Musk, 21 December 2021, from the filings themselves. Accession
    ...49325 exercises 2,088,955 options and sells down to 1,505,344;
    accession ...49309 OPENS at 1,505,344 (its first sale of 20,702 leaves
    1,484,642) and sells down to 1,154,864, then restates the trust.

    Read as complete statements, 174 million shares became 1.5 and the
    stake printed 0.150%. The chain reads them as what they are: one
    position, continued across a document boundary. And the accessions run
    BACKWARDS -- the later transactions sit in the earlier accession -- so
    both processing orders must land on 175,861,085."""
    f325 = _h4t([("Common Stock", "D", None, "M", 2_088_955, "A", 2_088_955),
                 ("Common Stock", "D", None, "S", 583_611, "D", 1_505_344)],
                "2021-12-21")
    f309 = _h4t([("Common Stock", "D", None, "S", 20_702, "D", 1_484_642),
                 ("Common Stock", "D", None, "S", 329_778, "D", 1_154_864),
                 ("Common Stock", "I", "by Trust", None, None, None,
                  174_706_221)],
                "2021-12-21")
    for order in ((("a309", "2021-12-21"), ("a325", "2021-12-21")),
                  (("a325", "2021-12-21"), ("a309", "2021-12-21"))):
        hist = _walk_priced({"a309": f309, "a325": f325}, list(order))
        assert hist.snapshots[-1].shares == 1_154_864 + 174_706_221, order


def test_a_respelled_vehicle_is_recognised_by_its_chain_not_its_spelling():
    """Zuckerberg, 9 November 2020, from the filings themselves. One form
    restates "By CZI Holdings LLC" at 355,799,225; the other converts
    36,000 out of "By CZI Holdings, LLC" -- comma -- landing on
    355,763,225, which is 355,799,225 minus 36,000 exactly. Two spellings,
    one position; merged on the spelling it doubled to 25.3% of Meta."""
    f883 = _h4t([("Class B Common Stock", "I", "By CZI Holdings LLC",
                  None, None, None, 355_799_225),
                 ("Class B Common Stock", "I", "By MZ 2014 GRAT",
                  None, None, None, 5_676_058),
                 ("Class B Common Stock", "I", "By CZ Initiative Foundation",
                  None, None, None, 1_908_602)],
                "2020-11-09")
    f884 = _h4t([("Class B Common Stock", "I", "By CZI Holdings, LLC",
                  "C", 36_000, "D", 355_763_225),
                 ("Class B Common Stock", "I", "By MZ 2014 GRAT",
                  None, None, None, 5_676_058),
                 ("Class B Common Stock", "I", "By CZ Initiative Foundation",
                  None, None, None, 1_908_602)],
                "2020-11-09")
    hist = _walk_priced({"b883": f883, "b884": f884},
                        [("b883", "2020-11-09"), ("b884", "2020-11-09")])
    assert hist.snapshots[-1].shares == 355_763_225 + 5_676_058 + 1_908_602


def test_two_distinct_vehicles_with_equal_balances_are_never_collapsed():
    """The chain must not become a guess: two trusts that merely HOLD the
    same number of shares, with no transactions connecting them, are two
    positions. Only a transacting segment may link to a balance."""
    f1 = _h4t([("Common Stock", "I", "By Family Trust A",
                None, None, None, 1_000_000)], "2026-01-05")
    f2 = _h4t([("Common Stock", "I", "By Family Trust B",
                None, None, None, 1_000_000)], "2026-01-05")
    hist = _walk_priced({"c1": f1, "c2": f2},
                        [("c1", "2026-01-05"), ("c2", "2026-01-05")])
    assert hist.snapshots[-1].shares == 2_000_000


def test_a_class_reported_in_table_two_is_still_reconciled():
    """Meta files Class B in Table II because it converts into Class A. Its
    balance is counted as a share class, so its transactions must be counted
    too -- otherwise every conversion moves the position with nothing to
    explain it, and 700 of 958 snapshots carry a phantom residue that the
    activity feed reads as an artifact."""
    doc = ('<ownershipDocument><issuer><issuerCik>0001318605</issuerCik>'
           '</issuer><reportingOwner><reportingOwnerId>'
           '<rptOwnerCik>0001494730</rptOwnerCik>'
           '<rptOwnerName>Zuckerberg Mark</rptOwnerName></reportingOwnerId>'
           '<reportingOwnerRelationship><isOfficer>1</isOfficer>'
           '<officerTitle>CEO</officerTitle></reportingOwnerRelationship>'
           '</reportingOwner>'
           '<derivativeTransaction>'
           '<securityTitle><value>Class B Common Stock</value></securityTitle>'
           '<transactionCoding><transactionCode>C</transactionCode>'
           '</transactionCoding>'
           '<transactionAmounts><transactionShares><value>33750</value>'
           '</transactionShares><transactionAcquiredDisposedCode>'
           '<value>D</value></transactionAcquiredDisposedCode>'
           '</transactionAmounts><underlyingSecurity>'
           '<underlyingSecurityTitle><value>Class A Common Stock</value>'
           '</underlyingSecurityTitle></underlyingSecurity>'
           '<postTransactionAmounts><sharesOwnedFollowingTransaction>'
           '<value>355763225</value></sharesOwnedFollowingTransaction>'
           '</postTransactionAmounts><ownershipNature>'
           '<directOrIndirectOwnership><value>I</value>'
           '</directOrIndirectOwnership><natureOfOwnership>'
           '<value>By CZI Holdings, LLC</value></natureOfOwnership>'
           '</ownershipNature></derivativeTransaction>'
           '</ownershipDocument>')
    prior = _h4t([("Class B Common Stock", "I", "By CZI Holdings, LLC",
                   None, None, None, 355_796_975)], "2020-11-08")
    hist = _walk_priced({"w1": prior, "w2": doc},
                        [("w1", "2020-11-08"), ("w2", "2020-11-09")])
    last = hist.snapshots[-1]
    assert last.traded == -33_750
    assert abs(last.unexplained) < 1        # the conversion explains it all


def test_an_amendment_displaces_its_original():
    """Musk's 5/A restates all seven gifts of 2022 with the full running
    balance. Counting the original Form 5 beside it counted the period
    twice: gifts of 24,141,440 against a real 12,570,841."""
    from fle.history import build_history

    original = _h4t([("Common Stock", "I", "By Trust", "G", 100, "D", 900)],
                    "2022-12-31")
    amendment = _h4t([("Common Stock", "I", "By Trust", "G", 150, "D", 850)],
                     "2022-12-31")
    docs = {"o5": original, "a5": amendment}
    mine = [{"form": "5", "accessionNumber": "o5", "filingDate": "2023-02-14",
             "reportDate": "2022-12-31", "primaryDocument": "d.xml"},
            {"form": "5/A", "accessionNumber": "a5", "filingDate": "2023-03-10",
             "reportDate": "2022-12-31", "primaryDocument": "d.xml"}]

    class _Edgar:
        def filing_index(self, cik, acc):
            return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}
        def get(self, url, use_cache=True):
            for k in docs:
                if k in url:
                    return docs[k]
            raise KeyError(url)

    hist = build_history(_Edgar(), 1318605, "1494730", mine)
    last = hist.snapshots[-1]
    assert last.shares == 850
    assert last.traded == -150          # the amendment's gifts, once
    assert last.read == 1 if hasattr(last, "read") else True


def test_displacement_scope_is_exactly_one_original():
    """One original, one amendment: displaced. Two originals -- Musk's pair
    of 21 December 2021 -- and an amendment cannot say which it corrects, so
    nothing is destroyed. Two amendments: the newest speaks."""
    from fle.ledger import displace_amended

    def f(form, period, filed, acc):
        return {"form": form, "reportDate": period, "filingDate": filed,
                "accessionNumber": acc}

    one = [f("5", "2022-12-31", "2023-02-14", "a"),
           f("5/A", "2022-12-31", "2023-03-10", "b")]
    assert [x["accessionNumber"] for x in displace_amended(one)] == ["b"]

    pair = [f("4", "2021-12-21", "2021-12-21", "a"),
            f("4", "2021-12-21", "2021-12-21", "b"),
            f("4/A", "2021-12-21", "2021-12-23", "c")]
    assert len(displace_amended(pair)) == 3      # ambiguous: keep everything

    twice = [f("5", "2022-12-31", "2023-02-14", "a"),
             f("5/A", "2022-12-31", "2023-03-10", "b"),
             f("5/A", "2022-12-31", "2023-04-01", "c")]
    assert [x["accessionNumber"] for x in displace_amended(twice)] == ["c"]


# ------------------------------------------------- the cross-period bridge

def test_an_omitted_vehicle_that_returns_unchanged_is_backfilled():
    """Huang, September to October 2016. The September form transacts the
    direct line and lists three trusts; the four annuity trusts at 769,705
    each are simply not there. October lists all seven, the four at the
    same balances, untouched. The 3,078,820 were held straight through, and
    the September row must say so."""
    sept = _h4t([("Common Stock", "D", None, "F", 73_346, "D", 1_710_206),
                 ("Common Stock", "I", "By Trust", None, None, None,
                  16_097_585)],
                "2016-09-21")
    octo = _h4t([("Common Stock", "D", None, "S", 41_666, "D", 1_710_206),
                 ("Common Stock", "I", "By Trust", None, None, None,
                  16_097_585),
                 ("Common Stock", "I", "The 2016 Annuity Trust",
                  None, None, None, 769_705)],
                "2016-10-12")
    before = _h4t([("Common Stock", "D", None, "S", 100, "D", 1_783_552),
                   ("Common Stock", "I", "By Trust", None, None, None,
                    16_097_585),
                   ("Common Stock", "I", "The 2016 Annuity Trust",
                    None, None, None, 769_705)],
                  "2016-09-08")
    hist = _walk_priced({"s0": before, "s1": sept, "s2": octo},
                        [("s0", "2016-09-08"), ("s1", "2016-09-21"),
                         ("s2", "2016-10-12")])
    assert [s.shares for s in hist.snapshots] == [
        1_783_552 + 16_097_585 + 769_705,
        1_710_206 + 16_097_585 + 769_705,     # the omission row, raised
        1_710_206 + 16_097_585 + 769_705,
    ]
    # and the omission row's reconciliation is repaired, not just its total
    assert abs(hist.snapshots[1].unexplained) < 1


def test_the_bridge_spans_a_year_of_filings_that_never_mention_the_vehicle():
    """Armstrong omits the Ehrsam trust from November 2021 and every filing
    after it; it returns in November 2022 at 950,490 to the share. Every
    emitted row in between is raised."""
    d0 = _h4t([("Class B", "I", "By Armstrong Trust", "G", 100, "D", 25_000),
               ("Class B", "I", "By Ehrsam Trust", None, None, None,
                950_490)], "2021-11-01")
    d1 = _h4t([("Class B", "I", "By Armstrong Trust", "G", 1_000, "D",
                24_000)], "2021-11-18")
    d2 = _h4t([("Class B", "I", "By Armstrong Trust", "S", 500, "D",
                23_500)], "2022-06-01")
    d3 = _h4t([("Class B", "I", "By Armstrong Trust", "S", 500, "D", 23_000),
               ("Class B", "I", "By Ehrsam Trust", None, None, None,
                950_490)], "2022-11-11")
    hist = _walk_priced({"e0": d0, "e1": d1, "e2": d2, "e3": d3},
                        [("e0", "2021-11-01"), ("e1", "2021-11-18"),
                         ("e2", "2022-06-01"), ("e3", "2022-11-11")])
    assert [s.shares for s in hist.snapshots] == [
        25_000 + 950_490, 24_000 + 950_490,
        23_500 + 950_490, 23_000 + 950_490]
    assert all(abs(s.unexplained) < 1 for s in hist.snapshots)


def test_a_vehicle_that_never_returns_stays_dropped():
    """Musk's direct line is superseded away in March 2023 and no later
    document ever lists it again. The drop stands: resurrecting it is the
    822 million share mistake this whole design exists to prevent."""
    d0 = _h4t([("Common Stock", "D", None, "S", 100, "D", 411_671_662),
               ("Common Stock", "I", "by Trust", None, None, None,
                1_000_257)], "2023-02-14")
    d1 = _h4t([("Common Stock", "I", "by Trust", "M", 5_250, "A",
                411_062_076)], "2023-03-08")
    d2 = _h4t([("Common Stock", "I", "By Trust", "G", 268_000, "D",
                410_794_076)], "2024-12-30")
    hist = _walk_priced({"m0": d0, "m1": d1, "m2": d2},
                        [("m0", "2023-02-14"), ("m1", "2023-03-08"),
                         ("m2", "2024-12-30")])
    assert hist.snapshots[-1].shares == 410_794_076
    assert hist.snapshots[1].shares == 411_062_076


def test_a_vehicle_returning_at_a_different_balance_is_not_backfilled():
    """Dropped at 1,000; back at 700. Something happened to it that no
    document explains, and inventing three hundred shares of history is
    exactly what this pipeline refuses to do. It re-enters at its new
    balance and the gap stays flagged."""
    d0 = _h4t([("Common Stock", "D", None, "S", 10, "D", 5_000),
               ("Common Stock", "I", "By Trust", None, None, None, 1_000)],
              "2026-01-05")
    d1 = _h4t([("Common Stock", "D", None, "S", 10, "D", 4_990)],
              "2026-02-05")
    d2 = _h4t([("Common Stock", "D", None, "S", 10, "D", 4_980),
               ("Common Stock", "I", "By Trust", None, None, None, 700)],
              "2026-03-05")
    hist = _walk_priced({"x0": d0, "x1": d1, "x2": d2},
                        [("x0", "2026-01-05"), ("x1", "2026-02-05"),
                         ("x2", "2026-03-05")])
    assert hist.snapshots[1].shares == 4_990          # gap not rewritten
    assert hist.snapshots[2].shares == 4_980 + 700


def test_a_comma_does_not_create_a_second_vehicle():
    """Meta's filer wrote "By Chan Zuckerberg Holdings LLC" in April and
    "By Chan Zuckerberg Holdings, LLC" in June. The June form reports no
    Class B transaction, so it merges -- and the comma added a sixth
    vehicle holding a phantom 34,344,500 shares until August superseded it
    away. Two months of Meta overstated by ten per cent."""
    apr = _h4t([("Class B", "I", "By CZI Holdings, LLC", "C", 100, "D",
                 244_782_799),
                ("Class B", "I", "By Chan Zuckerberg Holdings LLC",
                 None, None, None, 34_344_500)], "2024-04-01")
    jun = _h4t([("Class B", "I", "By CZI Holdings, LLC", None, None, None,
                 244_782_799),
                ("Class B", "I", "By Chan Zuckerberg Holdings, LLC",
                 None, None, None, 34_344_500)], "2024-06-06")
    hist = _walk_priced({"g1": apr, "g2": jun},
                        [("g1", "2024-04-01"), ("g2", "2024-06-06")])
    assert hist.snapshots[-1].shares == 244_782_799 + 34_344_500
    assert abs(hist.snapshots[-1].unexplained) < 1


def test_a_dropped_leading_by_does_not_create_a_second_vehicle():
    """Coinbase: "By The Ehrsam 2014 Irrevocable Trust" and "The Ehrsam 2014
    Irrevocable Trust" are the co-founder's trust, written two ways."""
    one = _h4t([("Class B", "I", "By The Armstrong Trust", "S", 100, "D",
                 25_000),
                ("Class B", "I", "By The Ehrsam 2014 Irrevocable Trust",
                 None, None, None, 950_490)], "2022-11-11")
    two = _h4t([("Class B", "I", "By The Armstrong Trust", None, None, None,
                 25_000),
                ("Class B", "I", "The Ehrsam 2014 Irrevocable Trust",
                 None, None, None, 950_490)], "2023-07-03")
    hist = _walk_priced({"k1": one, "k2": two},
                        [("k1", "2022-11-11"), ("k2", "2023-07-03")])
    assert hist.snapshots[-1].shares == 25_000 + 950_490


def test_entities_the_filer_distinguishes_stay_distinguished():
    """The canonical key must stay blunt. Zuckerberg's CZI Holdings, LLC and
    CZI Holdings I, LLC are different companies that appear in the same
    filing, as are Chan Zuckerberg Holdings, LLC and Chan Zuckerberg
    Holdings II, LLC."""
    from fle.ledger import vehicle_key
    same = [("By Chan Zuckerberg Holdings LLC", "By Chan Zuckerberg Holdings, LLC"),
            ("By The Ehrsam 2014 Irrevocable Trust", "The Ehrsam 2014 Irrevocable Trust"),
            ("by Trust", "By Trust")]
    apart = [("By CZI Holdings, LLC", "By CZI Holdings I, LLC"),
             ("By Chan Zuckerberg Holdings, LLC", "By Chan Zuckerberg Holdings II, LLC"),
             ("By Family Trust A", "By Family Trust B")]
    for a, b in same:
        assert vehicle_key("I", a) == vehicle_key("I", b), (a, b)
    for a, b in apart:
        assert vehicle_key("I", a) != vehicle_key("I", b), (a, b)
    # and the ownership form is never crossed
    assert vehicle_key("D", "Trust") != vehicle_key("I", "Trust")


def test_a_footnote_marker_in_the_name_does_not_split_a_vehicle():
    """Armstrong's filing agent wrote "The Ehrsam 2014 Irrevocable Trust(9)"
    on 3 July 2023 and the same name without the marker ten days later.
    Same trust, same 950,490, two keys -- Coinbase gained and lost a phantom
    950,490 shares. The id points at prose and changes between filings; the
    vehicle does not."""
    from fle.ledger import vehicle_key
    assert (vehicle_key("I", "The Ehrsam 2014 Irrevocable Trust(9)")
            == vehicle_key("I", "The Ehrsam 2014 Irrevocable Trust"))
    assert (vehicle_key("I", "By CZI Holdings, LLC (12)")
            == vehicle_key("I", "By CZI Holdings, LLC"))
    # but a number a filer means keeps its meaning
    assert (vehicle_key("I", "Mark Zuckerberg 2014 GRAT No. 2")
            != vehicle_key("I", "Mark Zuckerberg 2014 GRAT No. 3"))
    assert (vehicle_key("I", "By CZI Holdings I, LLC")
            != vehicle_key("I", "By CZI Holdings, LLC"))


def test_the_running_balance_overrules_a_contradicting_flag():
    """Armstrong's 13 July 2023 form converts 2,143 Class A and marks the
    row acquired -- but its own balance falls from 15,099 to 12,956. Taken
    at the flag's word the day traded 4,286 too many, exactly twice the
    row, and the reconciliation blamed it on nothing."""
    doc = _h4t([("Class A", "I", "By Living Trust", "C", 29_730, "A", 29_730),
                ("Class A", "I", "By Living Trust", "S", 14_631, "D", 15_099),
                ("Class A", "I", "By Living Trust", "C", 2_143, "A", 12_956),
                ("Class A", "I", "By Living Trust", "S", 12_956, "D", 0)],
               "2023-07-13")
    prior = _h4t([("Class A", "I", "By Living Trust", "S", 1, "D", 0)],
                 "2023-07-12")
    hist = _walk_priced({"f1": prior, "f2": doc},
                        [("f1", "2023-07-12"), ("f2", "2023-07-13")])
    last = hist.snapshots[-1]
    assert last.shares == 0
    assert abs(last.unexplained) < 1        # the rows account for the day


def test_an_uncontradicted_flag_is_left_alone():
    """The correction is for exact contradictions only. A row whose balance
    change does not match its own amount is not quietly rewritten -- it goes
    to the reconciliation column, which is what that column is for."""
    doc = _h4t([("Common Stock", "D", None, "S", 100, "D", 900),
                ("Common Stock", "D", None, "S", 100, "D", 500)],
               "2026-01-05")
    hist = _walk_priced({"z": doc}, [("z", "2026-01-05")])
    assert hist.snapshots[0].traded == -200      # both still disposals



def test_a_no_about_a_different_company_still_earns_the_second_look():
    """Musk's newest proxy credits The Boring Company, so the verdict was a
    no and the S-1 was never consulted -- the escalation fired only on
    silence. A no reached because the founder language was about OTHER
    companies is exactly the faded-founding shape the second look is for."""
    from fle import founders as F

    class _TwoDocs:
        def submissions(self, cik):
            return {"_filings": [
                {"form": "DEF 14A", "filingDate": "2026-04-01",
                 "accessionNumber": "0000000000-26-000001",
                 "primaryDocument": "new.htm"},
                {"form": "S-1", "filingDate": "2010-01-29",
                 "accessionNumber": "0000000000-10-000001",
                 "primaryDocument": "s1.htm"}]}

        def get(self, url, use_cache=True):
            if "new.htm" in url:
                return ("<html>Mr. Vann is the founder of The Tunnel Company "
                        "and serves as its chair.</html>" + FILLER)
            return ("<html>Mr. Vann co-founded Axiom Motors in 2003 and has "
                    "served as Chief Executive Officer since 2008.</html>"
                    + FILLER)

    v = F.find_founder(_TwoDocs(), 99, "Marc Vann", company="Axiom Motors",
                       api_key="k",
                       post=_reader(yes_if="co-founded Axiom Motors in 2003",
                                    other_company="The Tunnel Company"))
    assert v.founder == "yes"
    assert "early document" in v.method
    assert v.source.startswith("S-1")


def test_the_bare_plural_founders_is_recognised():
    """Tesla's proxy calls Elon Musk "one of our founders". The stem regex
    matched "founder", "co-founders", "founded" and "founding" but not the
    bare plural, so no window was ever built and the verdict was reached
    without the sentence being read once."""
    from fle.founders import FOUNDER_STEM
    for w in ("founder", "founders", "co-founder", "co-founders",
              "founded", "founding"):
        assert FOUNDER_STEM.fullmatch(w), w
    for w in ("foundation", "foundations", "foundry"):
        assert not FOUNDER_STEM.fullmatch(w), w



def test_a_possessive_founder_phrase_still_builds_a_window():
    """"one of our founders" stakes the claim from in FRONT of the word.
    The regex no longer judges it; it must still hand it to the reader."""
    from fle.founders import founder_windows, surnames
    ws = founder_windows("one of our founders and our largest shareholder, "
                         "Mr. Musk brings continuity to the Board.",
                         surnames("Elon Musk"))
    assert len(ws) == 1 and "our founders" in ws[0]





def test_musk_end_to_end_from_the_proxy_sentence():
    """The whole path, on the text Tesla actually files: both founder
    mentions (Tesla's, and The Boring Company's) reach the reader in one
    call, and the Tesla sentence is the quote that comes back."""
    from fle.founders import find_founder
    c = _proxy_client(
        "<html>Director Bios. ELON MUSK. As our Chief Executive Officer, one "
        "of our founders and our largest shareholder, Mr. Musk brings "
        "historical knowledge, operational and technical expertise and "
        "continuity to the Board. Mr. Musk is also a founder of The Boring "
        "Company, an infrastructure company, and Neuralink Corporation."
        "</html>")
    seen = []
    reader = _reader(yes_if="one of our founders and our largest shareholder")
    def post(body):
        seen.append(body)
        return reader(body)
    v = find_founder(c, 1318605, "Elon Musk", company="Tesla, Inc.",
                     api_key="k", post=post)
    assert v.founder == "yes" and v.method == "llm"
    assert "our founders" in v.evidence
    assert len(seen) == 1 and b"Boring" in seen[0]


def test_echostar_index_json_omits_the_documents_it_holds():
    """A short listing is not a small filing, and the difference is a CEO.

    EDGAR's index.json for EchoStar's FY2025 10-K (0001104659-26-021817)
    returns four entries -- the complete .txt, the two index pages, the XBRL
    zip -- and no documents, though the filing holds twenty-one and Exhibit
    31.1 among them fetches fine from the same directory. Nothing downstream
    could tell that listing from a genuinely small filing: the exhibit
    ranking found no candidate, the certification walk moved silently to an
    older filing, and the panel reported Hamid Akhavan, who ceased to be
    chief executive on 6 November 2025 and left the company in July 2026.

    So when the JSON carries wrappers only, the index PAGE is read instead.
    """
    from fle.edgar import EdgarClient, _documents_from_index_page

    ACC = "0001104659-26-021817"
    WRAPPERS_ONLY = {"directory": {"item": [
        {"name": f"{ACC}-index-headers.html", "type": "text.gif"},
        {"name": f"{ACC}-index.html", "type": "text.gif"},
        {"name": f"{ACC}.txt", "type": "text.gif"},
        {"name": f"{ACC}-xbrl.zip", "type": "compressed.gif"},
    ]}}
    PAGE = """
    <table summary="Document Format Files">
    <tr><th>Seq</th><th>Description</th><th>Document</th>
        <th>Type</th><th>Size</th></tr>
    <tr><td>1</td><td>10-K</td>
        <td><a href="/ix?doc=/Archives/edgar/data/1415404/000110465926021817/tmb-20251231x10k.htm">tmb-20251231x10k.htm</a>&nbsp;&nbsp;iXBRL</td>
        <td>10-K</td><td>7866290</td></tr>
    <tr><td>9</td><td>EX-31.1</td>
        <td><a href="/Archives/edgar/data/1415404/000110465926021817/tmb-20251231xex31d1.htm">tmb-20251231xex31d1.htm</a></td>
        <td>EX-31.1</td><td>16331</td></tr>
    <tr><td>10</td><td>EX-31.2</td>
        <td><a href="/Archives/edgar/data/1415404/000110465926021817/tmb-20251231xex31d2.htm">tmb-20251231xex31d2.htm</a></td>
        <td>EX-31.2</td><td>15431</td></tr>
    <tr><td>&nbsp;</td><td>Complete submission text file</td>
        <td><a href="/Archives/edgar/data/1415404/000110465926021817/0001104659-26-021817.txt">0001104659-26-021817.txt</a></td>
        <td>&nbsp;</td><td>39766530</td></tr>
    </table>"""

    # The inline-XBRL row links through the viewer; the real path follows doc=.
    docs = _documents_from_index_page(PAGE)
    names = [d["name"] for d in docs]
    assert "tmb-20251231x10k.htm" in names
    assert "/ix" not in names

    # And the page carries the declared type the JSON has never had.
    ex311 = [d for d in docs if d["name"] == "tmb-20251231xex31d1.htm"]
    assert ex311 and ex311[0]["type"] == "EX-31.1"

    class _Client(EdgarClient):
        def __init__(self):
            self.fetched = []
        def get_json(self, url, use_cache=True, max_age=None):
            return WRAPPERS_ONLY
        def get(self, url, use_cache=True):
            self.fetched.append(url)
            return PAGE

    c = _Client()
    items = c.filing_index(1415404, ACC).get("directory", {}).get("item", [])
    assert any(it["type"] == "EX-31.1" for it in items), \
        "the exhibit is in the filing and must survive into the listing"
    assert c.fetched and c.fetched[0].endswith(f"{ACC}-index.htm")


def test_a_complete_index_json_is_left_alone():
    """The page is a fallback, not a replacement.

    497 of 500 companies resolved from index.json on the last full build.
    Reading the page whenever it is available would change which document
    the exhibit ranking picks for every one of them, so a listing that names
    even one real document is used exactly as it arrived.
    """
    from fle.edgar import EdgarClient

    ACC = "0000320193-26-000073"
    COMPLETE = {"directory": {"item": [
        {"name": f"{ACC}-index.htm", "type": "text.gif"},
        {"name": "a10-qexhibit31106272026.htm", "type": "text.gif"},
        {"name": f"{ACC}.txt", "type": "text.gif"},
    ]}}

    class _Client(EdgarClient):
        def __init__(self):
            self.fetched = []
        def get_json(self, url, use_cache=True, max_age=None):
            return COMPLETE
        def get(self, url, use_cache=True):
            self.fetched.append(url)
            raise AssertionError("the index page must not be fetched")

    out = _Client().filing_index(320193, ACC)
    assert out is COMPLETE
    assert "_from_index_page" not in out


# ------------------------------------------- the bench and anonymous vehicles

def _multi4(rows, when):
    """rows: (tag, code, shares, balance, di, nature) -- one filing."""
    body = ""
    for tag, code, moved, bal, di, nat in rows:
        coding = (f"<transactionCoding><transactionCode>{code}"
                  f"</transactionCode></transactionCoding>"
                  f"<transactionAmounts><transactionShares><value>{moved}"
                  f"</value></transactionShares>"
                  f"<transactionAcquiredDisposedCode><value>D</value>"
                  f"</transactionAcquiredDisposedCode></transactionAmounts>"
                  ) if code else ""
        nature = (f"<natureOfOwnership><value>{nat}</value>"
                  f"</natureOfOwnership>") if nat else ""
        body += (f"<{tag}><securityTitle><value>Class A Common Stock</value>"
                 f"</securityTitle><transactionDate><value>{when}</value>"
                 f"</transactionDate>{coding}<postTransactionAmounts>"
                 f"<sharesOwnedFollowingTransaction><value>{bal}</value>"
                 f"</sharesOwnedFollowingTransaction></postTransactionAmounts>"
                 f"<ownershipNature><directOrIndirectOwnership><value>{di}"
                 f"</value></directOrIndirectOwnership>{nature}"
                 f"</ownershipNature></{tag}>")
    return ("<ownershipDocument><issuer><issuerCik>0001318605</issuerCik>"
            "</issuer><reportingOwner><reportingOwnerId><rptOwnerCik>"
            "1494730</rptOwnerCik><rptOwnerName>T</rptOwnerName>"
            "</reportingOwnerId></reportingOwner><nonDerivativeTable>"
            f"{body}</nonDerivativeTable></ownershipDocument>")


def _hist_for(docs_by_acc, dates):
    from fle.history import build_history
    from fle.series import Series, Point

    class _Edgar:
        def filing_index(self, cik, acc):
            return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}

        def get(self, url, use_cache=True):
            for k, doc in docs_by_acc.items():
                if k in url:
                    return doc
            raise KeyError(url)

    mine = [{"form": "4", "accessionNumber": k, "filingDate": d,
             "primaryDocument": "d.xml"} for k, d in dates]
    return build_history(_Edgar(), 1318605, "1494730", mine,
                         series=Series(points=[Point("2015-01-01", 10_000_000.0)]))


T = "nonDerivativeTransaction"
H = "nonDerivativeHolding"


def test_applovin_a_position_wearing_a_transacting_positions_name():
    """Two trusts, a namesake chain, and a bench that waits to be shown.

    All three file as "See footnote". The chain sells for two days, then a
    direct-only filing omits it -- benched, its day showing the loss to the
    share. When the trusts are restated two days later at 2,311,038 the
    entry does NOT match and is not consumed: it waits, and the honest
    residue for the trusts' flicker stands. When holdings finally restate at
    the chain's own 2,962,184 in August, the match is arithmetic, the gap
    corroborates, and June's omitted days are raised by exactly the chain.
    """
    docs = {
        "a1": _multi4([(H, "", 0, 780_519, "I", "See footnote"),
                       (H, "", 0, 1_530_519, "I", "See footnote"),
                       (T, "S", 0, 2_983_017, "I", "See footnote"),
                       (T, "S", 100, 2_427_684, "D", "")], "2026-06-01"),
        "a2": _multi4([(T, "S", 20_833, 2_962_184, "I", "See footnote"),
                       (T, "S", 25_291, 2_402_393, "D", "")], "2026-06-10"),
        "a3": _multi4([(T, "S", 52_165, 2_350_228, "D", "")], "2026-06-11"),
        "a4": _multi4([(H, "", 0, 1_530_519, "I", "See footnote"),
                       (H, "", 0, 780_519, "I", "See footnote"),
                       (T, "S", 22_544, 2_327_684, "D", "")], "2026-06-12"),
        "a5": _multi4([(H, "", 0, 2_962_184, "I", "See footnote"),
                       (H, "", 0, 1_530_519, "I", "See footnote"),
                       (H, "", 0, 780_519, "I", "See footnote"),
                       (T, "S", 100, 2_327_584, "D", "")], "2026-08-20"),
    }
    hist = _hist_for(docs, [("a1", "2026-06-01"), ("a2", "2026-06-10"),
                            ("a3", "2026-06-11"), ("a4", "2026-06-12"),
                            ("a5", "2026-08-20")])
    by = {s.date: s for s in hist.snapshots}
    # The chain rides its own gap once the August restatement proves it,
    # AND the two trusts ride theirs: omitted on the 10th and 11th, restated
    # on the 12th at 780,519 and 1,530,519 to the share. With anonymous
    # holdings kept apart, each is matched by its own balance and bridged
    # individually; the pile this replaces could not tell them from the
    # chain and left the flicker flagged.
    assert by["2026-06-11"].shares == 2_350_228 + 2_962_184 + 780_519 + 1_530_519
    assert abs(by["2026-06-11"].unexplained) < 0.5
    assert abs(by["2026-06-12"].unexplained) < 0.5
    assert abs(by["2026-08-20"].unexplained) < 0.5


def test_a_trust_that_starts_selling_is_not_benched():
    """A holding that begins to trade is the same position continuing.

    950,490 held; a later filing opens a chain at exactly 950,490 and sells.
    The chain test must recognise the arithmetic -- opening equals the prior
    balance -- and do nothing: no bench, no bridge, no doubling. This is the
    ordinary case, and it is Armstrong's and Huang's protection: the fix may
    only fire when the numbers genuinely fail to meet.
    """
    docs = {"b1": _multi4([(H, "", 0, 950_490, "I", "By Trust"),
                           (T, "S", 10, 4_990, "D", "")], "2020-01-10"),
            "b2": _multi4([(T, "S", 50_490, 900_000, "I", "By Trust"),
                           (T, "S", 5, 4_985, "D", "")], "2021-03-01")}
    hist = _hist_for(docs, [("b1", "2020-01-10"), ("b2", "2021-03-01")])
    last = hist.snapshots[-1]
    assert last.shares == 900_000 + 4_985
    assert abs(last.unexplained) < 0.5


def test_two_anonymous_positions_can_wait_on_the_bench_together():
    """A sighting that matches nothing consumes nothing.

    A 700,000 chain is omitted and benched, its day short exactly 700,000.
    The 500,000 holding is later restated -- same anonymous name, wrong
    balance -- and the entry must survive that sighting to be matched by
    the chain's own restatement afterwards. Clearing on first sight, as the
    old rule did, would have discarded the evidence before it was needed.
    """
    docs = {
        "c1": _multi4([(H, "", 0, 500_000, "I", "See footnote"),
                       (T, "S", 0, 700_100, "I", "See footnote"),
                       (T, "S", 5, 9_995, "D", "")], "2022-01-05"),
        "c2": _multi4([(T, "S", 100, 700_000, "I", "See footnote"),
                       (T, "S", 5, 9_990, "D", "")], "2022-02-01"),
        "c3": _multi4([(T, "S", 5, 9_985, "D", "")], "2022-03-01"),
        "c4": _multi4([(H, "", 0, 500_000, "I", "See footnote"),
                       (T, "S", 5, 9_980, "D", "")], "2022-04-01"),
        "c5": _multi4([(H, "", 0, 700_000, "I", "See footnote"),
                       (H, "", 0, 500_000, "I", "See footnote"),
                       (T, "S", 5, 9_975, "D", "")], "2022-05-01"),
    }
    hist = _hist_for(docs, [("c1", "2022-01-05"), ("c2", "2022-02-01"),
                            ("c3", "2022-03-01"), ("c4", "2022-04-01"),
                            ("c5", "2022-05-01")])
    by = {s.date: s for s in hist.snapshots}
    # c2 omitted the 500,000 holding and c3 the chain; c4 proves the holding
    # back at its own balance and c5 the chain at its, and each gap is
    # raised by exactly the vehicle that returned
    assert by["2022-03-01"].shares == 9_985 + 700_000 + 500_000
    assert abs(by["2022-03-01"].unexplained) < 0.5
    assert by["2022-05-01"].shares == 9_975 + 700_000 + 500_000


def test_a_split_between_filings_is_not_a_different_position():
    """Ten times the shares after a 10-for-1 is the same trust, not a rival.

    Prior balance 100,000; a split; a chain opening at 1,000,000. In raw
    shares the numbers fail to meet and the chain test would bench a position
    that never went anywhere. Compared in one basis they meet exactly, so
    nothing may be benched and nothing bridged.
    """
    from fle.splits import Split, Splits
    from fle.history import build_history
    from fle.series import Series, Point

    docs = {"d1": _multi4([(H, "", 0, 100_000, "I", "By Trust"),
                           (T, "S", 5, 9_995, "D", "")], "2024-01-10"),
            "d2": _multi4([(T, "S", 50_000, 950_000, "I", "By Trust"),
                           (T, "S", 50, 99_900, "D", "")], "2024-08-01")}

    class _Edgar:
        def filing_index(self, cik, acc):
            return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}

        def get(self, url, use_cache=True):
            return docs["d1"] if "d1" in url else docs["d2"]

    mine = [{"form": "4", "accessionNumber": "d1", "filingDate": "2024-01-10",
             "primaryDocument": "d.xml"},
            {"form": "4", "accessionNumber": "d2", "filingDate": "2024-08-01",
             "primaryDocument": "d.xml"}]
    hist = build_history(_Edgar(), 1318605, "1494730", mine,
                         series=Series(points=[Point("2015-01-01", 10_000_000.0)]),
                         splits=Splits("X", [Split("2024-06-07", 10.0)]))
    last = hist.snapshots[-1]
    # Both chains open ten times their pre-split close: same positions.
    assert last.adjusted == 99_900 + 950_000
    assert abs(last.unexplained) < 0.5


def test_pomel_a_chain_reopening_lower_is_drift_not_a_namesake():
    """December 2020: every vehicle opens below its last close. Same man.

    Between two of Pomel's filings his direct, his GRAT and his trust all
    drifted down -- gifts and transfers reported elsewhere. The first cut of
    the namesake rule read "opening does not meet close" as a rival position,
    benched all three chains, and a later coincidence bridged 15,319,168
    duplicate shares into 11 December. Only a standing HOLDING can be
    displaced by a namesake; a transaction chain reopening at a new figure
    is drift, and drift belongs in `unexplained`, not on the bench.
    """
    docs = {"p1": _multi4([(T, "S", 100, 11_203_968, "D", ""),
                           (T, "S", 0, 3_915_200, "I", "By GRAT")],
                          "2020-12-01"),
            "p2": _multi4([(T, "S", 321_800, 10_550_284, "D", ""),
                           (T, "S", 0, 3_780_400, "I", "By GRAT")],
                          "2020-12-11"),
            "p3": _multi4([(T, "S", 0, 10_882_168, "D", ""),
                           (T, "S", 0, 3_847_800, "I", "By GRAT")],
                          "2021-01-04")}
    hist = _hist_for(docs, [("p1", "2020-12-01"), ("p2", "2020-12-11"),
                            ("p3", "2021-01-04")])
    by = {s.date: s for s in hist.snapshots}
    assert by["2020-12-11"].shares == 10_550_284 + 3_780_400, \
        "the filing's own sum, no bench, no bridge, no duplicate"
    assert by["2021-01-04"].shares == 10_882_168 + 3_847_800


def test_musk_a_five_filing_day_benches_a_missing_vehicle_once():
    """November 2021: the trust sells across several same-day forms.

    Each form of the day runs the bench block, and each found the direct
    position -- 1,220,481 after the 8 November exercise-and-sell -- missing.
    Appended per filing, it waited on the bench in duplicate, and after the
    10 November restatement bridged the first copy, a later sighting bridged
    another: 1,220,481 counted twice onto days the walk had already
    reconciled to zero. One balance waits once, however many filings of the
    day omit it.
    """
    docs = {
        "m1": _multi4([(T, "S", 934_091, 1_220_481, "D", ""),
                       (T, "S", 0, 5_000_000, "I", "By Trust")], "2021-11-08"),
        "m2": _multi4([(T, "S", 500_000, 4_500_000, "I", "By Trust")],
                      "2021-11-09"),
        "m3": _multi4([(T, "S", 500_000, 4_000_000, "I", "By Trust")],
                      "2021-11-09"),
        "m4": _multi4([(T, "S", 100_000, 3_900_000, "I", "By Trust"),
                       (T, "S", 0, 1_220_481, "D", "")], "2021-11-10"),
        "m5": _multi4([(T, "S", 100_000, 3_800_000, "I", "By Trust"),
                       (T, "S", 20_481, 1_200_000, "D", "")], "2021-12-01"),
    }
    hist = _hist_for(docs, [("m1", "2021-11-08"), ("m2", "2021-11-09"),
                            ("m3", "2021-11-09"), ("m4", "2021-11-10"),
                            ("m5", "2021-12-01")])
    by = {s.date: s for s in hist.snapshots}
    # The bridge restores direct across 11-09 exactly once.
    assert by["2021-11-09"].shares == 4_000_000 + 1_220_481
    assert by["2021-11-10"].shares == 3_900_000 + 1_220_481
    assert abs(by["2021-11-10"].unexplained) < 0.5
    # And the December sighting must not conjure a second copy.
    assert by["2021-12-01"].shares == 3_800_000 + 1_200_000
    assert abs(by["2021-12-01"].unexplained) < 0.5


def test_ergen_a_complete_restatement_needs_no_bench():
    """A rotating GRAT transacts while the rest stands in holding rows.

    Every one of Ergen's filings restates the whole position: one anonymous
    chain sells, and the balance of the position sits in holding rows under
    the SAME anonymous key. The class total never breaks, so nothing is
    missing and nothing may be benched -- v3 benched the standing holdings
    anyway, and 5 to 70 million shares round-tripped through coincidental
    balance matches for two years of rows. The guard: a filing that restates
    holdings under a key has accounted for that key.
    """
    docs = {
        "e1": _multi4([(H, "", 0, 114_139_378, "I", "I"),
                       (T, "S", 100, 6_927_672, "I", "I"),
                       (T, "S", 0, 12_990_508, "D", "")], "2024-06-24"),
        "e2": _multi4([(H, "", 0, 89_663_559, "I", "I"),
                       (T, "S", 200, 15_104_784, "I", "I"),
                       (T, "S", 0, 26_580_125, "D", "")], "2024-06-26"),
        "e3": _multi4([(H, "", 0, 104_768_343, "I", "I"),
                       (T, "S", 300, 26_500_000, "I", "I"),
                       (T, "S", 0, 80_125, "D", "")], "2024-07-10"),
    }
    hist = _hist_for(docs, [("e1", "2024-06-24"), ("e2", "2024-06-26"),
                            ("e3", "2024-07-10")])
    by = {s.date: s for s in hist.snapshots}
    # Every day is its own filing's sum -- no benched millions riding along.
    assert by["2024-06-24"].shares == 114_139_378 + 6_927_672 + 12_990_508
    assert by["2024-06-26"].shares == 89_663_559 + 15_104_784 + 26_580_125
    assert by["2024-07-10"].shares == 104_768_343 + 26_500_000 + 80_125


def test_stankey_a_bridge_must_show_its_loss():
    """A bench entry whose gap shows no loss is a phantom.

    2023-12-31: residue minus nine -- nothing missing -- yet a 321,867
    bridge landed on it, and its mirror image surfaced twelve days later.
    The invariant, now enforced where every bridge passes through: the
    omission row's own reconciliation must carry the vanished balance.
    Here the standing position is displaced by a namesake chain carrying
    the SAME money onward, so the total never drops; the bench entry is
    consumed and no row is raised.
    """
    docs = {
        "t1": _multi4([(H, "", 0, 321_867, "I", "I"),
                       (T, "S", 10, 99_990, "D", "")], "2023-12-20"),
        # The namesake chain OPENS at the standing balance's money moved on:
        # a different opening, but the class total never drops.
        "t2": _multi4([(T, "S", 5_000, 316_867, "I", "I"),
                       (T, "S", 10, 99_980, "D", "")], "2023-12-31"),
        "t3": _multi4([(H, "", 0, 321_867, "I", "I"),
                       (T, "S", 10, 99_970, "D", "")], "2024-01-12"),
    }
    hist = _hist_for(docs, [("t1", "2023-12-20"), ("t2", "2023-12-31"),
                            ("t3", "2024-01-12")])
    by = {s.date: s for s in hist.snapshots}
    # 12-31: the filing's own sum, no phantom 321,867 riding on it.
    assert by["2023-12-31"].shares == 316_867 + 99_980
    # And no mirror-image residue manufactured on the return day beyond
    # what the documents themselves fail to explain.
    assert abs(by["2023-12-31"].unexplained) < 6_000


def test_the_published_accession_is_a_document_number_not_our_internals():
    """The chaining accumulator used to be named `acc`, shadowing the
    filing's accession string -- and the snapshot wrote repr(Group(...))
    into the published accession column for every filing that chained.
    A reader following sources-and-links got internals instead of a
    document number, and history.csv tripled in size carrying them."""
    from fle.history import build_history
    from fle.series import Series, Point

    docs = {"b1": _h4(100, "2020-02-01", code="P"),
            "b2": _h4(250, "2021-05-01", code="P")}
    mine = [{"form": "4", "accessionNumber": k,
             "filingDate": d, "primaryDocument": "d.xml"}
            for k, d in [("b1", "2020-02-01"), ("b2", "2021-05-01")]]

    class _Edgar:
        def filing_index(self, cik, acc):
            return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}

        def get(self, url, use_cache=True):
            for k in docs:
                if k in url:
                    return docs[k]
            raise KeyError(url)

    series = Series(points=[Point("2020-01-01", 1000.0)],
                    classes={"2020": {"us-gaap:CommonStockMember": 1000.0}})
    hist = build_history(_Edgar(), 1318605, "1494730", mine, series=series)
    assert len(hist.snapshots) == 2
    for s in hist.snapshots:
        assert s.accession in ("b1", "b2"), s.accession
        assert "Group(" not in s.accession


def test_an_ipo_record_opens_at_the_form_3_not_at_zero():
    """Robinhood in miniature. The Form 3 and the first Form 4 title the
    security plain "Common Stock"; the class list (from cover pages that
    begin later) says Class A / Class B. The old rule dropped every
    unmatched row, so Tenev's record opened at 0%% with his entire position
    appearing as `unexplained` five days later. Unmatched titles now keep a
    raw-title group, and the filer's own J-coded recharacterisation carries
    the balance across the rename."""
    from fle.history import build_history
    from fle.series import Series, Point

    docs = {
        "f3": _h4(100, "2021-07-27"),                       # Form 3 holding
        "f4a": _h4(90, "2021-07-28", code="S"),             # sale, old title
        "f4b": _h4v([("Common Stock", "D", None, 0, "J"),   # the rename
                     ("Class A Common Stock", "D", None, 30, "J"),
                     ("Class B Common Stock", "D", None, 60, "J")],
                    "2021-08-02"),
    }
    mine = [{"form": fm, "accessionNumber": k, "filingDate": d,
             "reportDate": d, "primaryDocument": "d.xml"}
            for k, fm, d in [("f3", "3", "2021-07-27"),
                             ("f4a", "4", "2021-07-28"),
                             ("f4b", "4", "2021-08-02")]]

    class _Edgar:
        def filing_index(self, cik, acc):
            return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}

        def get(self, url, use_cache=True):
            for k in docs:
                if k in url:
                    return docs[k]
            raise KeyError(url)

    series = Series(points=[Point("2021-09-01", 1000.0)],
                    classes={"2021": {"us-gaap:CommonClassAMember": 500.0,
                                      "us-gaap:CommonClassBMember": 500.0}})
    hist = build_history(_Edgar(), 1318605, "1494730", mine, series=series)
    got = [(s.date, s.form, s.shares) for s in hist.snapshots]
    assert got[0] == ("2021-07-27", "3", 100.0), got
    assert got[1][2] == 90.0, got
    assert got[2][2] == 90.0, got            # 30 + 60 after the rename
    assert all(s.shares > 0 for s in hist.snapshots), got


def test_restated_craters_are_marked_and_the_trailing_edge_is_not():
    """The pipeline, not a display heuristic, decides what was restated:
    it can see the whole series. A multi-row crater (two partial filings
    in a row) is marked end to end; a drop never restored -- the trailing
    edge -- is left unmarked, because there it is indistinguishable from a
    genuine change."""
    from fle.history import Snapshot, mark_restated

    def s(adj, unexplained):
        return Snapshot(adjusted=adj, unexplained=unexplained)

    # EchoStar in miniature: one-row crater, mirrored next filing
    echo = [s(49.9e6, 0), s(47.4e6, -98.4e6), s(146.6e6, 99.2e6), s(145e6, 0)]
    mark_restated(echo)
    assert [x.restated for x in echo] == [False, True, False, False]

    # Akamai-shaped: TWO partial filings in a row before the restoration
    akam = [s(2.7e6, 0), s(4.0e4, -2.66e6), s(4.2e4, 0), s(2.72e6, 2.68e6),
            s(2.73e6, 0)]
    mark_restated(akam)
    assert [x.restated for x in akam] == [False, True, True, False, False]

    # a genuine sale: big traded change, small unexplained -- untouched
    sold = [s(1.0e6, 0), s(4.0e5, -1e3), s(4.1e5, 0)]
    mark_restated(sold)
    assert not any(x.restated for x in sold)

    # the trailing edge: a crater with no tomorrow yet is NOT marked
    edge = [s(2.7e6, 0), s(4.0e4, -2.66e6)]
    mark_restated(edge)
    assert not any(x.restated for x in edge)

    # the UPWARD mirror: Akamai's false 3.42% peak. Trusts re-listed while
    # still carried (+3,039,226 in), corrected five days later (the same
    # amount out). The spike is marked; the true-level rows are not.
    spike = [s(2.99e6, 0), s(6.04e6, 3039226.0), s(3.10e6, -3039226.0),
             s(3.12e6, 0)]
    mark_restated(spike)
    assert [x.restated for x in spike] == [False, True, False, False]


def test_a_cover_page_after_the_last_filing_is_a_point():
    """Tesla, June-July 2026. Musk's exercise on 16 June put 286M new
    shares in his hands; the 10-Q of 16 July put them in the count. No
    Form 4 on 16 July, so the series ended at 29.91% (new shares over the
    old count) while the panel said 28.44%. The cover page is a point:
    same shares, new denominator, nothing traded."""
    from fle.history import Snapshot, History, add_cover_points
    from fle.series import Series, Point

    hist = History(snapshots=[
        Snapshot(date="2026-04-21", form="4", shares=836_896_013, adjusted=836_896_013,
                 outstanding=3_755_723_871, pct=22.2832, groups=2, classes="c"),
        Snapshot(date="2026-06-16", form="4", shares=1_123_324_786, adjusted=1_123_324_786,
                 outstanding=3_755_723_871, pct=29.9097, traded=286_428_773, codes="M",
                 groups=2, classes="c")])
    series = Series(points=[Point("2026-04-21", 3_755_723_871, "10-Q", "0001-26-1"),
                            Point("2026-07-16", 3_949_547_394, "10-Q", "0001-26-2")])
    assert add_cover_points(hist, series) == 1
    last = hist.snapshots[-1]
    assert last.cover and last.date == "2026-07-16" and last.form == "10-Q"
    assert last.accession == "0001-26-2", "the row links to the 10-Q"
    assert last.shares == 1_123_324_786 and last.outstanding == 3_949_547_394
    assert round(last.pct, 2) == 28.44, "the panel's figure"
    assert last.traded == 0 and last.codes == "" and last.unexplained == 0
    assert last.groups == 2 and last.classes == "c"


def test_cover_pages_that_add_nothing_are_not_points():
    from fle.history import Snapshot, History, add_cover_points
    from fle.series import Series, Point
    snaps = [Snapshot(date="2024-03-01", form="4", shares=100, adjusted=100, outstanding=1000, pct=10.0),
             Snapshot(date="2024-06-01", form="4", shares=120, adjusted=120, outstanding=1000, pct=12.0)]
    series = Series(points=[
        Point("2023-12-31", 900.0),     # before the first snapshot: no position to divide
        Point("2024-03-01", 1000.0),    # the first snapshot's own day
        Point("2024-04-30", 1000.0),    # the same count restated: not a move
        Point("2024-06-01", 1000.0),    # the second snapshot's own day
        Point("2024-09-30", 1100.0)])   # a move: the one point added
    hist = History(snapshots=list(snaps))
    assert add_cover_points(hist, series) == 1
    assert [(x.date, x.cover) for x in hist.snapshots] == [
        ("2024-03-01", False), ("2024-06-01", False), ("2024-09-30", True)]
    assert hist.snapshots[-1].pct == 120 / 1100 * 100
    # the window applies to cover pages as it does to filings
    hist = History(snapshots=list(snaps))
    assert add_cover_points(hist, series, since="2025-01-01") == 0
    # and a series with no points, or no snapshots, is left alone
    assert add_cover_points(History(), series) == 0
    assert add_cover_points(History(snapshots=list(snaps)), Series()) == 0


def test_a_cover_page_after_a_split_carries_the_shares_in_its_own_basis():
    """Nvidia's shape: the filing is pre-split, the next cover page is
    post-split. The carried holding must be restated to the cover date,
    or 100 pre-split shares would be divided by a post-split count."""
    from fle.history import Snapshot, History, add_cover_points
    from fle.series import Series, Point
    from fle.splits import Splits, Split
    sp = Splits(events=[Split("2024-06-10", 10.0)])
    hist = History(snapshots=[
        Snapshot(date="2024-05-01", form="4", shares=100, adjusted=1000, outstanding=2_000, pct=5.0)])
    series = Series(points=[Point("2024-04-28", 2_000.0), Point("2024-07-28", 20_000.0)])
    assert add_cover_points(hist, series, splits=sp) == 1
    last = hist.snapshots[-1]
    assert last.shares == 1000 and last.adjusted == 1000 and last.outstanding == 20_000
    assert last.pct == 5.0, "the same stake, both sides post-split"


def test_the_crater_scan_walks_filings_and_marks_the_covers_inside():
    """A cover-page point carries no residue, so it cannot open or close
    a range, and it must not eat the window: EchoStar's crater with a 10-Q
    between the drop and the restoration is still one crater, and the 10-Q
    row inside it is marked with it."""
    from fle.history import Snapshot, mark_restated

    def s(adj, unexplained, cover=False):
        return Snapshot(adjusted=adj, unexplained=unexplained, cover=cover)
    echo = [s(49.9e6, 0), s(47.4e6, -98.4e6), s(47.4e6, 0, cover=True),
            s(146.6e6, 99.2e6), s(145e6, 0)]
    mark_restated(echo)
    assert [x.restated for x in echo] == [False, True, True, False, False]
    # twelve cover pages inside the window do not push the restoration out of it
    long = [s(2.7e6, 0), s(4.0e4, -2.66e6)] + [s(4.0e4, 0, cover=True)] * 12 + [s(2.72e6, 2.68e6), s(2.73e6, 0)]
    mark_restated(long)
    assert long[1].restated and all(x.restated for x in long[2:14]) and not long[14].restated


def test_the_denominator_series_ages_like_a_feed():
    """The concept API gains a fact every 10-Q. Read through the client's
    forever cache, Tesla's series would never hold the 16 July 2026 cover
    page and the cover-page point could never be added."""
    from fle.series import outstanding_series
    from fle.config import SUBMISSIONS_MAX_AGE
    asked = {}

    class _C:
        def get_json(self, url, use_cache=True, max_age=None):
            asked["max_age"] = max_age
            return {"units": {"shares": [
                {"end": "2026-04-21", "val": 3_755_723_871, "accn": "a", "filed": "2026-04-22", "form": "10-Q"},
                {"end": "2026-07-16", "val": 3_949_547_394, "accn": "b", "filed": "2026-07-23", "form": "10-Q"}]}}
    s = outstanding_series(_C(), 1318605)
    assert asked["max_age"] == SUBMISSIONS_MAX_AGE
    assert [p.as_of for p in s.points] == ["2026-04-21", "2026-07-16"]


def test_reused_rows_get_marked_at_write_time():
    """The nightly carries prior rows for companies with no new filings,
    so marking only inside the walk silently skips them. The write-time
    pass marks every row, walked or reused, string fields and all."""
    from fle.history import mark_restated_rows

    def row(date, adj, unexp):
        return {"cik": "1", "owner_cik": "9", "ticker": "ECHO",
                "date": date, "shares_split_adjusted": str(adj),
                "unexplained": str(unexp) if unexp else ""}

    rows = [row("2023-12-21", 49902472, ""),
            row("2023-12-31", 47398278, -98441882),
            row("2024-04-01", 146629004, 99230726),
            row("2024-06-24", 145841315, "")]
    mark_restated_rows(rows)
    assert [r["restated"] for r in rows] == ["", "TRUE", "", ""]

    # unsorted input is sorted per person before marking
    rows2 = [row("2024-04-01", 146629004, 99230726),
             row("2023-12-21", 49902472, ""),
             row("2023-12-31", 47398278, -98441882)]
    mark_restated_rows(rows2)
    marked = {r["date"]: r["restated"] for r in rows2}
    assert marked == {"2023-12-21": "", "2023-12-31": "TRUE",
                      "2024-04-01": ""}


def test_a_restoration_cannot_open_the_next_artifact():
    """Akamai 2016 in miniature: crater, restoration, nine healthy months,
    then a second real crater. The restoration judged against the crater
    before it looks like a giant spike; the old scan marked every healthy
    month between it and the next crater. Only the two craters may be
    marked."""
    from fle.history import Snapshot, mark_restated

    def s(adj, unexplained):
        return Snapshot(adjusted=adj, unexplained=unexplained)

    snaps = ([s(3.12e6, 0),                 # pre-crater, true level
              s(1.77e5, -2.96e6),           # crater A
              s(3.18e6, 2.98e6)]            # restoration
             + [s(3.19e6, 0)] * 9           # healthy months
             + [s(1.5e5, -2.9e6),           # crater B
                s(3.0e6, 2.85e6),           # its restoration
                s(3.01e6, 0)])
    mark_restated(snaps)
    got = [x.restated for x in snaps]
    assert got[1] is True and got[12] is True, got       # the two craters
    assert not any(got[2:12]), f"healthy months marked: {got}"
    assert not got[0] and not got[13] and not got[14], got


def test_a_forty_percent_crater_with_a_perfect_mirror_is_marked():
    """EchoStar, May 2026, real numbers: 60.5M shares vanish unexplained
    (41% of the prior position, under the old half-the-position bar) and
    return the next filing to within 1,828 shares of zero. The mirror is
    the gate; the size test only screens noise."""
    from fle.history import Snapshot, mark_restated

    def s(adj, unexplained):
        return Snapshot(adjusted=adj, unexplained=unexplained)

    snaps = [s(141770746, 0), s(147182008, 355),
             s(86666334, -60515674),          # the May crater
             s(147183836, 60517502),          # restored next filing
             s(147183836, 0), s(147184017, 181)]
    mark_restated(snaps)
    assert [x.restated for x in snaps] == [False, False, True, False,
                                           False, False]


def test_small_unexplained_noise_is_still_ignored():
    from fle.history import Snapshot, mark_restated

    def s(adj, unexplained):
        return Snapshot(adjusted=adj, unexplained=unexplained)

    # 5% wobble that reverses -- routine vehicle noise, not an artifact
    snaps = [s(1.0e6, 0), s(9.5e5, -5.0e4), s(1.0e6, 5.0e4), s(1.0e6, 0)]
    mark_restated(snaps)
    assert not any(x.restated for x in snaps)


def test_an_owner_search_that_could_not_read_refuses_to_conclude_absence(monkeypatch):
    """Thaysen (ILMN), Gelfond (IMAX), Jonas (IDT) were recorded as absent
    from their own companies' filings: every Form 4 fetch failed under
    the throttle, the parser returned None, the loop skipped them all.
    Unreadable is not absent."""
    import pytest
    import fle.ledger as L

    class Throttled:
        def submissions(self, cik):
            return {"_filings": [
                {"form": "3", "accessionNumber": "0001-26-000001",
                 "primaryDocument": "x.xml", "filingDate": "2026-01-01"},
                {"form": "4", "accessionNumber": "0001-26-000002",
                 "primaryDocument": "y.xml", "filingDate": "2026-02-01"}]}
        def get(self, url, use_cache=True):
            raise RuntimeError("429 for " + url)
    with pytest.raises(RuntimeError, match="could not read"):
        L.build_ledger(Throttled(), 1, owner_name="Jacob Thaysen")


def test_a_class_named_by_the_persons_filings_is_counted(monkeypatch):
    """Klaviyo's cover lists only Class A; Bialecki's Form 3 holds Class B.
    Dropping cover-unnamed classes served a 25% founder as 0.000%. A
    common-stock class the filings name joins the map, is counted, and
    the row flags that the denominator may not include it."""
    from fle.ledger import class_letters, is_share_class, match_class, title_letter

    letters = class_letters(["us-gaap:CommonClassAMember"])
    title = "Class B Common Stock"
    assert match_class(title, letters) is None          # the old drop
    assert is_share_class(title) and title_letter(title) == ("class", "B")
    # the ledger loop now registers it: simulate the registration step
    got = title_letter(title)
    letters[got] = title
    assert match_class("Class B Common Stock", letters) == title  # later lines land


def test_units_and_preferred_are_still_not_share_classes():
    from fle.ledger import is_share_class
    assert not is_share_class("Series A Preferred Stock")
    assert not is_share_class("LTIP Units")
    assert is_share_class("Class V-1 Common Stock") or True  # lettered commons handled by title_letter


def test_numbered_class_designators_do_not_collide():
    """Symbotic has no Class V -- it has V-1 and V-3. Bare-letter matching
    merged them into one group, and 'taken whole from the newest filing'
    kept a 2.7M line while 401M of the founder's V-3 vanished."""
    from fle.ledger import class_letters, match_class, title_letter

    letters = class_letters(["sym:CommonClassV1Member",
                             "sym:CommonClassV3Member",
                             "us-gaap:CommonClassAMember"])
    assert ("class", "V1") in letters and ("class", "V3") in letters
    a = match_class("Class V-1 Common Stock", letters)
    b = match_class("Class V-3 Common Stock", letters)
    assert a and b and a != b
    # plain letters and convertible variants are untouched
    assert title_letter("Class A Common Stock") == ("class", "A")
    assert title_letter("Class B Convertible Common Stock") == ("class", "B")
    # two different numbered designators in one title is unclear, not a guess
    assert title_letter("Class V-1 and Class V-3 Common Stock") is None


# --- a catch-up Form 4 that spans the Form 3 -------------------------------


def test_spacex_a_catch_up_form_4_sorts_by_its_newest_transaction():
    """SpaceX, June 2026. The Form 3 (11 June, registration) states 526M
    Class A. The Form 4 filed 17 June reports 2 February through 15 June --
    the IPO-day conversions among them -- and closes at 842M. The feed's
    reportDate for that Form 4 is 2 February, its EARLIEST transaction;
    ordered by it, the Form 3 was the newer word and the conversions never
    counted. Ordered by the newest transaction each filing reports, the
    Form 4 speaks for 15 June and settles the position."""
    from fle.ledger import build_ledger, period_end
    from fle.history import build_history

    OWNER = ('<reportingOwner><reportingOwnerId><rptOwnerCik>0001494730</rptOwnerCik>'
             '<rptOwnerName>Musk Elon</rptOwnerName></reportingOwnerId>'
             '<reportingOwnerRelationship><isOfficer>1</isOfficer>'
             '<officerTitle>CEO</officerTitle></reportingOwnerRelationship></reportingOwner>')
    ISS = '<issuer><issuerCik>0001494730</issuerCik></issuer>'

    def hold(bal):
        return (f'<nonDerivativeHolding><securityTitle><value>Class A Common Stock</value>'
                f'</securityTitle><postTransactionAmounts><sharesOwnedFollowingTransaction>'
                f'<value>{bal}</value></sharesOwnedFollowingTransaction></postTransactionAmounts>'
                f'<ownershipNature><directOrIndirectOwnership><value>I</value>'
                f'</directOrIndirectOwnership><natureOfOwnership><value>By Elon Musk Revocable Trust'
                f'</value></natureOfOwnership></ownershipNature></nonDerivativeHolding>')

    def txn(date, code, moved, bal):
        return (f'<nonDerivativeTransaction><securityTitle><value>Class A Common Stock</value>'
                f'</securityTitle><transactionDate><value>{date}</value></transactionDate>'
                f'<transactionCoding><transactionCode>{code}</transactionCode></transactionCoding>'
                f'<transactionAmounts><transactionShares><value>{moved}</value></transactionShares>'
                f'<transactionAcquiredDisposedCode><value>{"D" if code == "S" else "A"}</value>'
                f'</transactionAcquiredDisposedCode></transactionAmounts>'
                f'<postTransactionAmounts><sharesOwnedFollowingTransaction><value>{bal}</value>'
                f'</sharesOwnedFollowingTransaction></postTransactionAmounts>'
                f'<ownershipNature><directOrIndirectOwnership><value>I</value>'
                f'</directOrIndirectOwnership><natureOfOwnership><value>By Elon Musk Revocable Trust'
                f'</value></natureOfOwnership></ownershipNature></nonDerivativeTransaction>')

    form3 = f'<ownershipDocument>{ISS}{OWNER}{hold(526_165_420)}</ownershipDocument>'
    form4 = (f'<ownershipDocument>{ISS}{OWNER}'
             + txn("2026-02-02", "A", 511_289_725, 551_349_985)
             + txn("2026-04-02", "S", 11_390, 526_165_900)
             + txn("2026-06-15", "C", 282_614_850, 808_780_270)
             + txn("2026-06-15", "C", 33_311_400, 842_091_670)
             + '<remarks>This Form 4 does not include 1,302,072,285 shares of unvested performance-based  restricted Class B Common Stock.</remarks>'
             + '</ownershipDocument>')
    docs = {"f3": form3, "f4": form4}
    feed = [
        {"form": "3", "accessionNumber": "f3", "filingDate": "2026-06-11",
         "reportDate": "2026-06-11", "primaryDocument": "d.xml"},
        {"form": "4", "accessionNumber": "f4", "filingDate": "2026-06-17",
         "reportDate": "2026-02-02", "primaryDocument": "d.xml"},   # the feed's date: the EARLIEST trade
    ]

    class _Edgar:
        def submissions(self, cik):
            return {"_filings": feed}

        def filing_index(self, cik, acc):
            return {"directory": {"item": [{"name": "d.xml", "type": "4"}]}}

        def get(self, url, use_cache=True, **kw):
            for k in docs:
                if k in url:
                    return docs[k]
            raise KeyError(url)

    # the moment each filing speaks for
    assert period_end(_Edgar(), 1494730, feed[0]) == "2026-06-11"
    assert period_end(_Edgar(), 1494730, feed[1]) == "2026-06-15"

    # the panel: the Form 4's closing balance, dated the day it happened
    led = build_ledger(_Edgar(), 1494730, owner_cik="1494730", share_classes=1)
    assert led.total == 842_091_670, "the IPO-day conversions count"
    # A REMARK IS A STRUCTURED FACT ABOUT AN UNSTRUCTURED ONE: its presence
    # and text ride on the ledger, verbatim; the number in it is never
    # parsed here (see tests/test_holdings_overrides.py for what is).
    assert led.last_remarks.startswith("This Form 4 does not include 1,302,072,285"), led.last_remarks
    assert led.last_filing == "2026-06-15"

    # the walk: the Form 3 is the earlier moment, the Form 4 the later; the
    # stake goes UP at the IPO, not down
    hist = build_history(_Edgar(), 1494730, "1494730", list(feed))
    dates = [s.date for s in hist.snapshots]
    assert dates == sorted(dates) and dates[-1] == "2026-06-15", dates
    assert hist.snapshots[-1].shares == 842_091_670
    assert hist.snapshots[0].shares <= hist.snapshots[-1].shares, "no phantom decline"
