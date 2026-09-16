

def _cover(counts):
    """A cover page with one bare context per count, as Archer's 10-Qs tag them."""
    ctx = "".join(f'<xbrli:context id="c-{i}"><xbrli:entity><xbrli:identifier scheme="x">1</xbrli:identifier></xbrli:entity>'
                  f'<xbrli:period><xbrli:instant>{d}</xbrli:instant></xbrli:period></xbrli:context>' for i, (d, _v) in enumerate(counts, 4))
    facts = "".join(f'<ix:nonFraction name="dei:EntityCommonStockSharesOutstanding" contextRef="c-{i}" unitRef="shares" decimals="INF">{v:,}</ix:nonFraction>'
                    for i, (_d, v) in enumerate(counts, 4))
    return f"<html><body>{ctx}{facts}</body></html>"


class _Client:
    def __init__(self, docs, filings):
        self.docs, self.filings = docs, filings

    def submissions(self, cik):
        return {"_filings": self.filings}

    def primary_document(self, cik, acc, name):
        return self.docs[acc]

    def filing_index(self, cik, acc):
        return {"directory": {"item": [{"name": "d.htm"}]}}


def test_archer_two_bare_cover_counts_are_two_classes_and_the_oldest_cover_is_read(monkeypatch):
    """ARCHER (2026-09-16). Its 2024 10-Qs tagged Class A and Class B in
    bare contexts (c-4, c-5) with no member; the newest cover, after the
    charter abolished Class B, has one. The class list was taken from the
    newest cover alone and applied to every year, so the walk saw one
    class in 2024, folded Goldstein's Class B into it and wrote 0 for a
    36M holding. Now: two bare counts are two classes, and the oldest
    cover in the window is read too, so a structure that changed takes
    the cover-pages path with a class list per year."""
    import fle.series as S
    from fle.series import from_cover_pages, denominator_series, Series, Point
    docs = {"q24": _cover([("2024-11-04", 389161681), ("2024-11-04", 36110992)]),
            "k25": _cover([("2025-02-20", 542470264)]),
            "q26": _cover([("2026-08-01", 770023800)])}
    filings = [{"form": "10-Q", "accessionNumber": "q24", "filingDate": "2024-11-08", "reportDate": "2024-09-30", "primaryDocument": "d.htm"},
               {"form": "10-K", "accessionNumber": "k25", "filingDate": "2025-02-28", "reportDate": "2024-12-31", "primaryDocument": "d.htm"},
               {"form": "10-Q", "accessionNumber": "q26", "filingDate": "2026-08-05", "reportDate": "2026-06-30", "primaryDocument": "d.htm"}]
    c = _Client(docs, filings)
    s = from_cover_pages(c, 1824502, since="2024-01-01")
    assert s.classes["2024"] and len(s.classes["2024"]) == 2, "two bare counts, two classes"
    assert len(s.classes["2025"]) == 1 and len(s.classes["2026"]) == 1, "one bare count, one class, as before"
    assert [p.shares for p in s.points] == [389161681 + 36110992, 542470264, 770023800], "the denominator sums both classes"
    # the API path has points and the newest cover says one class: before, that settled it for every year
    monkeypatch.setattr(S, "outstanding_series", lambda client, cik, since="": Series(points=[Point("2025-03-31", 549011059.0), Point("2026-06-30", 770023800.0)]))
    d = denominator_series(c, 1824502, since="2024-01-01")
    assert "2024" in d.classes and len(d.classes["2024"]) == 2, "the oldest cover shows two counts: the cover pages settle the classes year by year"
    assert d.points[0].as_of == "2024-09-30", "and the dual-class years have their own cover points"
    # a company with one class at both ends still takes the API path with the one cover
    single = _Client({"a": _cover([("2024-11-04", 100)]), "b": _cover([("2026-08-01", 120)])},
                     [{"form": "10-Q", "accessionNumber": "a", "filingDate": "2024-11-08", "reportDate": "2024-09-30", "primaryDocument": "d.htm"},
                      {"form": "10-Q", "accessionNumber": "b", "filingDate": "2026-08-05", "reportDate": "2026-06-30", "primaryDocument": "d.htm"}])
    d = denominator_series(single, 1, since="2024-01-01")
    assert list(d.classes) == ["0000"] and len(d.classes["0000"]) == 1
    # a cover that tags the same count twice as of the same instant is one class
    twice = _Client({"t": _cover([("2026-08-01", 500), ("2026-08-01", 500)])}, [{"form": "10-Q", "accessionNumber": "t", "filingDate": "2026-08-05", "reportDate": "2026-06-30", "primaryDocument": "d.htm"}])
    assert len(from_cover_pages(twice, 2, since="2026-01-01").classes["2026"]) == 1
