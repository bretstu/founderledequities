"""Name matching, carried from v1 because it was right."""
from fle.names import names_match


def test_surname_order_and_initials():
    for a, b in [("Elon Musk", "Musk Elon"),
                 ("Satya Nadella", "Nadella Satya"),
                 ("Timothy D. Cook", "COOK TIMOTHY D"),
                 ("Jen-Hsun Huang", "Huang Jen Hsun")]:
        assert names_match(a, b) >= 0.7, (a, b)


def test_accents_survive_the_round_trip():
    """EDGAR writes ASCII; a proxy typesets properly. This cost v1 five
    companies before the Unicode decomposition was fixed."""
    assert names_match("Stéphane Bancel", "BANCEL STEPHANE") >= 0.7
    assert names_match("Carol Tomé", "TOME CAROL B") >= 0.7


def test_it_refuses_the_wrong_person():
    """The failure that mattered: picking whoever had the best job title
    returned Microsoft's "CEO Microsoft Commercial" instead of Nadella."""
    assert names_match("Satya Nadella", "Althoff Judson") < 0.7
    assert names_match("Mark Zuckerberg", "Mahoney Curtis J.") < 0.7
    assert names_match("Timothy D. Cook", "Newstead Jennifer") < 0.7


# --- when the certification and EDGAR disagree on the name ---------------

def test_a_working_name_against_a_legal_one():
    """Cognizant's certification says "Ravi Kumar S"; EDGAR holds "Singisetti
    Ravi Kumar" -- his legal surname, absent from the working name. The score
    is 0.00 and the search fails outright.
    """
    from fle.names import token_overlap, is_plain_ceo_title
    assert names_match("Ravi Kumar S", "Singisetti Ravi Kumar") == 0.0
    assert token_overlap("Ravi Kumar S", "Singisetti Ravi Kumar") >= 0.5
    # and the former CEO on the same list shares nothing
    assert token_overlap("Ravi Kumar S", "Humphries Brian") == 0.0
    # both facts are needed; neither alone would do
    assert is_plain_ceo_title("Chief Executive Officer")


def test_a_scoped_ceo_title_is_not_the_chief_executive():
    """v1 handed Microsoft to "CEO Microsoft Commercial" over Satya Nadella.
    A plain chief-executive title has nothing left once the words that make
    it one are removed; a scoped one leaves a business unit behind."""
    from fle.names import is_plain_ceo_title
    for good in ["Chief Executive Officer", "CEO",
                 "President and Chief Executive Officer",
                 "Chairman, President and CEO", "Interim Chief Executive Officer"]:
        assert is_plain_ceo_title(good), good
    for bad in ["CEO Microsoft Commercial", "EVP; CEO State Street Int'l",
                "President, Digital Business", "Chief Financial Officer",
                "EVP-Global Head of Operations", ""]:
        assert not is_plain_ceo_title(bad), bad


def test_the_fallback_needs_both_signals():
    """Either alone is dangerous. Every officer at Cognizant has a title;
    only one shares name parts with the certification."""
    from fle.names import token_overlap, is_plain_ceo_title
    cands = [("Singisetti Ravi Kumar", "Chief Executive Officer"),
             ("Humphries Brian", "Chief Executive Officer"),
             ("Nambiar Rajesh", "President, Digital Business")]
    taken = [n for n, t in cands
             if is_plain_ceo_title(t) and token_overlap("Ravi Kumar S", n) >= 0.5]
    assert taken == ["Singisetti Ravi Kumar"]


def test_the_partial_route_is_reported():
    import inspect
    from fle import ledger, ownership
    assert "partial_match" in {f.name for f in ledger.Ledger.__dataclass_fields__.values()}
    assert "matched on shared name parts" in inspect.getsource(ownership.build)


def test_edgar_writes_irish_surnames_two_ways():
    """State Street's certification says "Ronald P. O'Hanley"; EDGAR holds
    "O HANLEY RONALD P" -- the apostrophe replaced by a space, splitting one
    surname into two tokens so nothing matched at all.

    Only a LEADING single letter is joined, because EDGAR writes surname
    first. A trailing "L" in "RICHARDS MICHAEL L" is a middle initial, and
    joining it would invent a name.
    """
    from fle.names import join_name_prefix, normalize_name
    assert names_match("Ronald P. O'Hanley", "O HANLEY RONALD P") >= 0.7
    assert names_match("Sean O'Sullivan", "O SULLIVAN SEAN") >= 0.7

    # a trailing initial is left alone
    assert join_name_prefix(normalize_name("RICHARDS MICHAEL L")) == \
           ["richards", "michael", "l"]
    assert names_match("Michael L Richards", "RICHARDS MICHAEL L") >= 0.7

    # and it does not start matching unrelated people
    assert names_match("Satya Nadella", "Althoff Judson") < 0.7
    assert names_match("Mark Zuckerberg", "Mahoney Curtis J.") < 0.7


def test_an_officer_title_records_the_role_at_filing():
    """O'Hanley's filings carry "EVP; President and CEO of ..." -- his 2015
    title, when he ran State Street Global Advisors. He became chief
    executive of the corporation in 2019 and never filed a new Form 3.

    So a title is evidence of seniority at a moment, never of the current
    role, and the Cognizant fallback could not have rescued this one.
    """
    from fle.names import is_plain_ceo_title
    assert not is_plain_ceo_title("EVP; President and CEO of Global Advisors")
    # which is why the name had to be fixed instead
    assert names_match("Ronald P. O'Hanley", "O HANLEY RONALD P") >= 0.7


def test_a_curly_apostrophe_in_a_certification():
    """Gilead and Northern Trust both failed with "no Section 302
    certification found". The certification was found, read, and the name
    extracted correctly -- then discarded by a shape test that allowed a
    straight apostrophe and not a curly one.

    Both CFOs, with no apostrophe in their names, parsed fine on the same
    documents. That is the tell: the reader worked, one character did not.
    """
    from fle.identity import extract_names_from_certification as names_in
    assert names_in("I, Daniel P. O\u2019Day, certify that: 1. I have reviewed") \
        == ["Daniel P. O'Day"]
    assert names_in("I, Michael G. O\u2019Grady, certify that: 1. I have reviewed") \
        == ["Michael G. O'Grady"]
    # the straight-quote and plain cases still work
    assert names_in("I, Sean O'Sullivan, certify that: 1. I have reviewed") \
        == ["Sean O'Sullivan"]
    assert names_in("I, Andrew D. Dickinson, certify that: 1. I have reviewed") \
        == ["Andrew D. Dickinson"]


def test_apostrophes_break_three_different_ways():
    """A recurring failure, and each place needed its own fix:

      EDGAR writes a space          "O HANLEY RONALD P"   -> join the prefix
      filers write a curly quote    "O\u2019Day"                -> normalise it
      we write a straight quote     "O'Hanley"            -> the baseline

    Irish and French surnames are common enough among chief executives that
    this is worth a test rather than a comment.
    """
    from fle.identity import extract_names_from_certification as names_in
    cert = names_in("I, Michael G. O\u2019Grady, certify that: 1.")[0]
    assert names_match(cert, "O GRADY MICHAEL G") >= 0.7
    assert names_match(cert, "OGrady Michael G") >= 0.7
    assert names_match(cert, "O'Grady Michael G") >= 0.7


def test_a_bare_initial_is_never_a_surname():
    """WRB, live-site bug: the certification 'W. Robert Berkley' matched
    GOSSELINK ROBERT W at 1.0 -- surname 'W' -- and an SVP's shares were
    published under the chief executive's name. The real CEO's EDGAR name
    is BERKLEY WILLIAM R JR: initial-variant given names, right surname."""
    from fle.names import names_match

    cert = "W. Robert Berkley"
    assert names_match(cert, "GOSSELINK ROBERT W") == 0.0
    assert names_match(cert, "BERKLEY WILLIAM R JR") == 0.75
    assert names_match(cert, "BERKLEY WILLIAM R") == 0.75
    # the motivating conventions still work
    assert names_match("Ron M. Vachris", "Vachris Roland Michael") >= 0.85
    assert names_match("R. Vachris", "Vachris Roland") >= 0.75
