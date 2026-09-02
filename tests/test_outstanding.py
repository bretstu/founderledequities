"""The denominator."""
from fle.outstanding import shares_outstanding, jumped


class _C:
    def __init__(self, payload):
        self.payload = payload

    def get_json(self, url, use_cache=True, max_age=None):
        return self.payload


def _facts(rows):
    return {"units": {"shares": rows}}


def test_multi_class_is_summed_not_picked():
    """A dual-class filer tags the cover-page fact once per class. Taking
    "the most recent value" picks one arbitrarily and can understate the
    denominator several-fold."""
    out = shares_outstanding(_C(_facts([
        {"val": 100, "end": "2026-03-31", "filed": "2026-04-20", "form": "10-Q", "accn": "a"},
        {"val": 5_800_000_000, "end": "2026-06-30", "filed": "2026-07-25", "form": "10-Q", "accn": "b"},
        {"val": 800_000_000, "end": "2026-06-30", "filed": "2026-07-25", "form": "10-Q", "accn": "b"},
        {"val": 5_500_000_000, "end": "2026-06-30", "filed": "2026-07-25", "form": "10-Q", "accn": "b"},
    ])), 1652044)
    assert out.shares == 12_100_000_000
    assert out.classes == 3
    assert "3 share classes" in out.note


def test_an_amendment_supersedes_rather_than_adds():
    """An amended filing restates the same cover date. Summing both doubles
    the denominator."""
    out = shares_outstanding(_C(_facts([
        {"val": 1_000, "end": "2026-06-30", "filed": "2026-07-25", "form": "10-Q", "accn": "orig"},
        {"val": 1_010, "end": "2026-06-30", "filed": "2026-08-02", "form": "10-Q/A", "accn": "amend"},
    ])), 1)
    assert out.shares == 1_010
    assert out.classes == 1


def test_a_jump_is_reported_rather_than_absorbed():
    """Tesla went 3.33bn to 3.95bn in ten months. Genuine -- one option
    exercise -- but a misread tag looks identical without the history."""
    moved, how = jumped([("2025-09-30", 3_325_150_886, "10-Q"),
                         ("2026-06-30", 3_949_547_394, "10-Q")])
    assert moved and "+18.8%" in how

    quiet, _ = jumped([("2026-03-31", 1_000_000, "10-Q"),
                       ("2026-06-30", 995_000, "10-Q")])
    assert not quiet            # buybacks are not events


def test_an_empty_concept_falls_through_to_the_filing():
    """An empty or 404 concept is the multi-class signal, not a dead end --
    so it must reach the filing rather than give up."""
    class _NoFilings:
        def get_json(self, url, use_cache=True, max_age=None):
            return {"units": {"shares": []}}

        def submissions(self, cik):
            return {"_filings": []}

    out = shares_outstanding(_NoFilings(), 1)
    assert not out.ok
    assert "recent filings" in out.note      # it tried the fallback


# --- the multi-class fallback -------------------------------------------

def test_dimensional_facts_are_read_from_the_filing():
    """The SEC's XBRL APIs report only facts WITHOUT dimensional qualifiers.
    A dual-class filer tags the cover-page count once per class, each against
    a class-specific context -- so for Coinbase the concept endpoint returns
    NoSuchKey and companyfacts has no `dei` section at all.

    Every single-class company in the first test run worked; every multi-class
    one returned nothing.
    """
    from fle.outstanding import _facts_from_document
    doc = ('<ix:nonFraction contextRef="cA" '
           'name="dei:EntityCommonStockSharesOutstanding">2,204,000,000'
           '</ix:nonFraction>'
           '<ix:nonFraction contextRef="cB" '
           'name="dei:EntityCommonStockSharesOutstanding">5,800,000'
           '</ix:nonFraction>')
    facts = _facts_from_document(doc)
    assert len(facts) == 2
    assert sum(facts.values()) == 2_209_800_000


def test_the_scale_attribute_is_applied():
    """`scale` is the power of ten the printed figure was divided by. A cover
    reading "3,949.5" with scale="6" is 3,949,500,000; ignoring it understates
    by a factor of a million."""
    from fle.outstanding import _facts_from_document
    facts = _facts_from_document(
        '<ix:nonFraction contextRef="c" scale="6" '
        'name="dei:EntityCommonStockSharesOutstanding">3,949.5</ix:nonFraction>')
    assert list(facts.values()) == [3_949_500_000]


def test_one_fact_per_context_not_per_occurrence():
    """A cover page can restate the same class twice. Summing occurrences
    rather than contexts would double it."""
    from fle.outstanding import _facts_from_document
    facts = _facts_from_document(
        '<ix:nonFraction contextRef="cA" '
        'name="dei:EntityCommonStockSharesOutstanding">100</ix:nonFraction>'
        '<ix:nonFraction contextRef="cA" '
        'name="dei:EntityCommonStockSharesOutstanding">100</ix:nonFraction>')
    assert sum(facts.values()) == 100


def test_the_api_is_tried_first_and_the_filing_is_the_fallback():
    import inspect
    from fle import outstanding
    src = inspect.getsource(outstanding.shares_outstanding)
    assert "from_latest_filing(client, cik)" in src
    assert src.index("companyconcept") < src.index("from_latest_filing") \
        if "companyconcept" in src else True


def test_a_stale_api_value_is_as_bad_as_none():
    """Fox's concept API holds exactly one value ever recorded -- 1 share,
    dated 2019-03-18, from the shell entity that existed before the spin-off.
    It has been dual-class since, so every later fact is dimensional and the
    API omits it.

    Falling back only on an EMPTY response let that single stale datum win,
    and one share as a denominator turned an 87 million share holding into
    8,790,139,900%.
    """
    from fle.outstanding import _is_stale

    class _C:
        def __init__(self, latest): self.latest = latest
        def submissions(self, cik):
            return {"_filings": [{"form": "10-Q", "filingDate": self.latest}]}

    assert _is_stale(_C("2026-08-03"), 1, "2019-03-18")      # Fox
    assert not _is_stale(_C("2026-08-03"), 1, "2026-06-30")  # current
    assert not _is_stale(_C("2026-08-03"), 1, "2025-12-31")  # two quarters
    # a company that has genuinely stopped filing is not condemned for it
    assert not _is_stale(_C("2019-06-30"), 1, "2019-03-18")


def test_a_denominator_below_the_numerator_is_a_problem():
    """Nothing else would have caught Fox: the numerator was right, the
    arithmetic was right, and the answer was 8,790,139,900%."""
    import inspect
    from fle import ownership
    src = inspect.getsource(ownership.build)
    assert "rec.outstanding < rec.shares" in src
    assert "denominator is wrong" in " ".join(src.split())


def test_class_names_do_not_depend_on_a_namespace_prefix():
    """The prefix is a choice each filer makes -- `xbrli:context`, plain
    `context`, or something else. Insisting on `xbrli:` found nothing in
    Meta's 10-Q and the class names came back EMPTY WITH NO ERROR, which is
    the failure mode worth guarding: a silent nothing rather than a crash.
    """
    from fle.outstanding import class_names

    for frag in [
        '<xbrli:context id="c-8"><xbrldi:explicitMember dimension="d">'
        'us-gaap:CommonClassAMember</xbrldi:explicitMember></xbrli:context>',
        '<context id="c-8"><explicitMember dimension="d">'
        'us-gaap:CommonClassAMember</explicitMember></context>',
        '<x:context id="c-8"><y:explicitMember dimension="d">'
        'us-gaap:CommonClassAMember</y:explicitMember></x:context>',
    ]:
        assert class_names(frag) == {"c-8": "us-gaap:CommonClassAMember"}


def test_a_context_with_no_member_is_not_a_class():
    """An un-dimensioned context is the whole company, not one of its
    classes."""
    from fle.outstanding import class_names
    assert class_names('<context id="c-1"><entity/></context>') == {}


# ------------------------------------------------ cover pages a filer got wrong

def _series_of(vals):
    from fle.series import Series, Point
    return Series(points=[Point(as_of=f"20{10+i:02d}-06-30", shares=v,
                                form="10-Q", accession=f"acc-{i}")
                          for i, v in enumerate(vals)])


def test_resmed_a_cover_page_typed_in_thousands_is_dropped_not_rescaled():
    """145,681 where the company has 145,723,142 -- and 297% ownership.

    ResMed's 10-K/A tags the count with decimals="INF" and no scale, so the
    document says one hundred forty-five thousand shares. It was read
    correctly; it is simply wrong. Rescaling it by a guessed 1000 would
    invent a figure no filing states, so the point is dropped and the
    denominator forward-fills from the previous cover page.
    """
    from fle.series import reject_outliers
    ser = _series_of([145_600_000, 145_700_000, 145_681, 145_750_000,
                      145_800_000, 145_900_000, 146_000_000])
    reject_outliers(ser)
    assert [p.shares for p in ser.points] == [145_600_000, 145_700_000,
                                              145_750_000, 145_800_000,
                                              145_900_000, 146_000_000]
    assert "145,681" in ser.note and "dropped 1" in ser.note
    # And the gap forward-fills, which is what `at` has always done.
    assert ser.at("2012-07-01").shares == 145_700_000


def test_packaging_corp_a_filers_own_scale_error_is_dropped_too():
    """89,932,185 tagged scale="3" -- ninety BILLION shares.

    Inline XBRL lets a filer display a number and declare a multiplier; this
    module applies it faithfully, and here the filer declared the wrong one.
    Too large fails the same test as too small.
    """
    from fle.series import reject_outliers
    ser = _series_of([94_000_000, 94_100_000, 89_932_185_000, 94_200_000,
                      94_300_000, 94_400_000, 94_500_000])
    reject_outliers(ser)
    assert 89_932_185_000 not in [p.shares for p in ser.points]
    assert len(ser.points) == 6


def test_paramount_a_thousand_share_placeholder_cannot_survive():
    """scale="0" and a displayed 1,000: the filer asserts one thousand shares.

    It produced 7,621,074% ownership -- the largest impossible figure in the
    file. Nothing about the tagging is ambiguous, which is exactly why no
    parsing change can help and the point must simply go.
    """
    from fle.series import reject_outliers
    ser = _series_of([1_111_000_000, 1_112_000_000, 1_000, 1_113_000_000,
                      1_114_000_000, 1_115_000_000, 1_116_000_000])
    reject_outliers(ser)
    assert all(p.shares > 1_000_000 for p in ser.points)


def test_too_few_cover_pages_to_call_one_of_them_wrong():
    """A median needs a history behind it.

    A company with three filings has no basis for declaring one of them an
    outlier -- the "wrong" one might be the only right one. Below the
    threshold the series is returned untouched, however odd it looks.
    """
    from fle.series import reject_outliers
    ser = _series_of([100, 500_000_000, 500_000_000])
    reject_outliers(ser)
    assert len(ser.points) == 3 and not ser.note


def test_a_healthy_series_is_left_completely_alone():
    """Ordinary growth, buybacks and splits must never trip this.

    493 of 498 companies were untouched by this guard, and that is the point:
    it fires on documents that contradict their own company by fifty times,
    not on companies that changed.
    """
    from fle.series import reject_outliers
    ser = _series_of([100_000_000, 140_000_000, 200_000_000, 900_000_000,
                      880_000_000, 870_000_000, 2_000_000_000])
    before = [p.shares for p in ser.points]
    reject_outliers(ser)
    assert [p.shares for p in ser.points] == before
    assert not ser.note


def test_a_scale_that_makes_the_count_absurd_is_refused():
    """JBS's cover prints '776,086,920 Class A common shares' and tags it
    scale='3' -- a filer error worth 776 BILLION shares. The printed
    figure outranks a scale that makes it absurd; the note says so."""
    from fle.outstanding import _facts_from_document

    html = (
        '<ix:nonfraction name="dei:EntityCommonStockSharesOutstanding" '
        'contextref="C1" scale="3" decimals="0">776,086,920</ix:nonfraction>'
        '<ix:nonfraction name="dei:EntityCommonStockSharesOutstanding" '
        'contextref="C2" scale="3" decimals="0">294,842,267</ix:nonfraction>')
    notes: list = []
    facts = _facts_from_document(html, notes)
    assert facts == {"C1": 776086920.0, "C2": 294842267.0}
    assert len(notes) == 2 and "scale=3" in notes[0]

    # a LEGITIMATE scale still applies: "3,949.5" with scale=6 is Tesla
    html2 = ('<ix:nonfraction name="dei:EntityCommonStockSharesOutstanding" '
             'contextref="C1" scale="6" decimals="-5">3,949.5</ix:nonfraction>')
    notes2: list = []
    assert _facts_from_document(html2, notes2) == {"C1": 3949500000.0}
    assert not notes2
