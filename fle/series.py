"""Shares outstanding at any past date, and the classes in force then.

A percentage needs a denominator FROM THE SAME MOMENT. Tesla went from 3.33
billion shares to 3.95 billion in ten years; dividing a 2016 holding by
today's count understates it by a sixth, and the error grows the further back
you go.

The same is true of the class list. Today's cover page names today's classes.
Block's "Common Stock" WAS the class in 2019; Dell's "Series A" was Class A
before the 2018 rename. A series keyed on today's classes loses both.

WHERE IT COMES FROM.

`dei:EntityCommonStockSharesOutstanding` is tagged on every cover page, and
the XBRL concept API returns every value ever filed -- not just the newest.
Each carries an `end` date, a `form` and an accession, so the series is free
once the request is made.

For a multi-class filer the API holds nothing un-dimensioned and the cover
page must be read instead, once per quarter. That is the expensive path, and
it is why `classes_by_year` reads one filing a year rather than one a
quarter: class structures change rarely, share counts change constantly.

WHERE IT STOPS.

Cover-page tagging begins around 2009 and is reliable from about 2011. Before
that there is no machine-readable denominator, so a series cannot honestly
start earlier. Ten years is comfortably inside that.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .outstanding import CONCEPT, class_names, _facts_from_document, counted_dates


@dataclass
class Point:
    """The denominator as one filing reported it."""
    as_of: str
    shares: float
    form: str = ""
    accession: str = ""
    counted: str = ""      # the instant the count is as of (outstanding.counted_dates); as_of is the period end


@dataclass
class Series:
    points: list = field(default_factory=list)     # oldest first
    classes: dict = field(default_factory=dict)    # year -> {member: shares}
    note: str = ""

    def at(self, when: str) -> Point | None:
        """The newest cover date at or before `when`.

        Forward-fill, because a denominator holds until the next cover page
        restates it -- and a filing made in April is measured against the
        count printed on the March cover, not on one that does not exist yet.
        """
        got = None
        for p in self.points:
            if p.as_of <= when:
                got = p
            else:
                break
        return got or (self.points[0] if self.points else None)

    def classes_at(self, when: str) -> dict:
        """The classes in force in that year, falling back to the nearest."""
        if not self.classes:
            return {}
        year = (when or "")[:4]
        if year in self.classes:
            return self.classes[year]
        years = sorted(self.classes)
        earlier = [y for y in years if y <= year]
        return self.classes[earlier[-1]] if earlier else self.classes[years[0]]

    def __bool__(self) -> bool:
        return bool(self.points)


def outstanding_series(client, cik: int, since: str = "") -> Series:
    """Every cover-page count this company has filed, oldest first."""
    out = Series()
    try:
        # THE CONCEPT API IS A FEED, NOT A DOCUMENT: it gains a fact every
        # 10-Q. Cached forever (the client's default), the series ended at
        # whatever cover page was newest the first time a company was
        # walked, and a cover-page point after the person's last filing
        # (history.add_cover_points) could never appear. The panel's
        # reader (outstanding.shares_outstanding) ages it with the
        # submissions feeds; this one does the same.
        from .config import SUBMISSIONS_MAX_AGE
        data = client.get_json(CONCEPT.format(cik=int(cik)),
                               max_age=SUBMISSIONS_MAX_AGE)
    except Exception:  # noqa: BLE001
        out.note = "no un-dimensioned cover-page fact; read per filing"
        return out

    rows = [u for u in data.get("units", {}).get("shares", [])
            if isinstance(u.get("val"), (int, float)) and u["val"] > 0]
    if not rows:
        out.note = "no un-dimensioned cover-page fact; read per filing"
        return out

    # One cover date can carry several facts -- an amendment restating the
    # same date, or one fact per class. Keep the newest FILING for each date,
    # and sum only within that filing.
    by_date: dict = {}
    for u in rows:
        end = u.get("end") or ""
        if since and end < since:
            continue
        by_date.setdefault(end, []).append(u)

    for end, group in sorted(by_date.items()):
        by_acc: dict = {}
        for u in group:
            by_acc.setdefault(u.get("accn") or "", []).append(u)
        chosen = max(by_acc.items(),
                     key=lambda kv: max((x.get("filed") or "") for x in kv[1]))[1]
        out.points.append(Point(
            as_of=end,
            shares=sum(float(u["val"]) for u in chosen),
            form=chosen[0].get("form") or "",
            accession=chosen[0].get("accn") or ""))
    reject_outliers(out)
    return out


# A cover page a filer got wrong is still a cover page. Six were found in
# 500 companies, and every one was read correctly -- the DOCUMENT is wrong:
#
#   Smurfit Westrock   100 shares, no scale         (~522,000,000 actual)
#   Paramount Skydance 1,000, scale="0"             (~1,111,000,000)
#   ResMed             145,681, decimals="INF"      (~145,723,000)
#   Chipotle           27,962                       (~27,910,000)
#   Packaging Corp     89,932,185 with scale="3"    (~94,205,000)
#   Edison Intl        797,458,179,000,000          (~816,520,000)
#
# The last two are the filer misapplying the inline-XBRL scale attribute,
# which this module applies faithfully; the rest are simply typed wrong.
# Five rows of 25,028 produced percentages that cannot exist -- Paramount
# at 7,621,074% and Smurfit at 1,493,878% of their own companies.
#
# So the point is DROPPED, never rescaled: guessing that 145,681 "meant"
# 145,681,000 would invent a number no document states. Dropped, the
# denominator forward-fills from the previous cover page, which is what
# `Series.at` does for every filing that does not restate the count.
OUTLIER_FACTOR = 50.0
MIN_POINTS_TO_JUDGE = 6


def reject_outliers(out: "Series") -> None:
    """Drop cover-page counts a company's own history contradicts.

    Judged against the MEDIAN, which a handful of absurd values cannot move,
    and only where there are enough points for a median to mean anything --
    a company with three cover pages has no basis to call one of them wrong.
    """
    good = [p for p in out.points if p.shares > 0]
    if len(good) < MIN_POINTS_TO_JUDGE:
        return
    mid = statistics.median(p.shares for p in good)
    if mid <= 0:
        return
    keep, dropped = [], []
    for p in out.points:
        if p.shares > 0 and (p.shares > mid * OUTLIER_FACTOR
                             or p.shares < mid / OUTLIER_FACTOR):
            dropped.append(p)
        else:
            keep.append(p)
    if not dropped:
        return
    out.points = keep
    said = "; ".join(f"{p.as_of} {p.shares:,.0f} ({p.form} {p.accession})"
                     for p in dropped[:4])
    out.note = ((out.note + " | ") if out.note else "") + (
        f"dropped {len(dropped)} cover-page count(s) more than "
        f"{OUTLIER_FACTOR:.0f}x from this company's median of "
        f"{mid:,.0f}: {said}")


PERIODIC = ("10-K", "10-K/A", "10-Q", "10-Q/A", "20-F")


def from_cover_pages(client, cik: int, since: str = "",
                     on_step=None) -> Series:
    """Read every periodic cover page in the window.

    THE CONCEPT API HAS NOTHING FOR A MULTI-CLASS FILER. It holds only
    un-dimensioned facts, and a company tagging its count once per class has
    none -- which is the 404 that sends the panel to the cover page. The
    series had no such fallback, so Meta, Coinbase and Block came back with
    no denominator on a single one of their 952 snapshots.

    One pass gives both things the walk needs: the per-class counts, and the
    class MEMBERS from the same document. Reading them separately meant the
    class list came back empty for exactly the companies that need it, and
    Meta's "Clas A Common Stock" fell through to the raw-title fallback --
    restoring, in the history, the 184,659-share error the panel had fixed.

    Roughly forty documents over ten years. They are cached, so this is paid
    once per company.
    """
    subs = client.submissions(int(cik))
    filings = [f for f in subs.get("_filings", [])
               if (f.get("form") or "") in PERIODIC
               and (not since or (f.get("filingDate") or "") >= since)]
    filings.sort(key=lambda f: (f.get("filingDate") or ""))

    out = Series()
    seen_year: dict = {}
    for n, f in enumerate(filings, 1):
        if on_step:
            on_step(n, len(filings))
        acc = f.get("accessionNumber") or ""
        try:
            name = f.get("primaryDocument")
            if not name:
                idx = client.filing_index(int(cik), acc)
                items = idx.get("directory", {}).get("item", [])
                name = next((i["name"] for i in items
                             if (i.get("name") or "").lower()
                             .endswith((".htm", ".html"))), None)
            if not name:
                continue
            raw = client.primary_document(int(cik), acc, name)
        except Exception:  # noqa: BLE001
            continue

        facts = _facts_from_document(raw)
        if not facts:
            continue
        names = class_names(raw)
        per_class = {names.get(ctx, ctx): v for ctx, v in facts.items()}
        when = f.get("reportDate") or f.get("filingDate") or ""
        dates = counted_dates(raw)
        out.points.append(Point(as_of=when, shares=sum(facts.values()),
                                form=f.get("form") or "", accession=acc,
                                counted=max((dates.get(ctx, "") for ctx in facts), default="") or f.get("filingDate") or ""))
        # The class list, keyed by year. A structure changes almost never, so
        # the first filing of each year settles it.
        # TWO COUNTS ON A COVER ARE TWO CLASSES WHETHER OR NOT THE CONTEXTS
        # NAME THEM (2026-09-16, Archer): its 10-Qs tagged Class A (389.2M)
        # and Class B (36.1M) in bare contexts, c-4 and c-5, with no member;
        # the list was stored only when a member was named, so the walk saw
        # one class, folded Goldstein's Table II Class B into it, and wrote 0
        # for a 36M holding. Without member names the walk keys each row on
        # its own title, which keeps the classes apart; a single bare context
        # is one class, as before. Contexts stating the same count as of the
        # same instant are one class tagged twice.
        year = (f.get("filingDate") or "")[:4]
        distinct = {(dates.get(ctx, ""), v) for ctx, v in facts.items()}
        if year and year not in seen_year and per_class:
            seen_year[year] = per_class if len(distinct) == len(per_class) else dict(list(per_class.items())[:len(distinct)])
    out.points.sort(key=lambda p: p.as_of)
    # The multi-class path sums several facts per cover page, so a filer's
    # scale error lands here too -- Edison International's 797 trillion came
    # through this route.
    reject_outliers(out)
    out.classes = seen_year
    return out


def denominator_series(client, cik: int, since: str = "",
                       on_step=None) -> Series:
    """The concept API where it works, cover pages where it does not.

    The API returns the whole history in one request, so a filer it covers
    needs no cover pages for the DENOMINATOR. It still needs a class list --
    but the API only ever holds un-dimensioned facts, which is what a
    single-class filer files, so ONE cover page settles it rather than forty.
    """
    got = outstanding_series(client, cik, since=since)
    if not got.points:
        return from_cover_pages(client, cik, since=since, on_step=on_step)

    # One document, the newest in the window, for the class list alone.
    one = _newest_cover(client, cik, since)
    if one is not None and len(one) > 1:
        # Dimensioned after all: the API's un-dimensioned history is not the
        # whole company, so fall back and read them all.
        return from_cover_pages(client, cik, since=since, on_step=on_step)
    # A STRUCTURE THAT CHANGED NEEDS THE COVER PAGES (2026-09-16, Archer):
    # the newest cover said one class, because Class B was abolished on
    # 31 December 2024, and that one class was applied to every year, the
    # dual-class ones included, whose per-class counts the API path had
    # dropped besides. The oldest cover in the window is read too; if either
    # end shows more than one count, the cover pages settle the classes year
    # by year. One extra cached document per company.
    first = _oldest_cover(client, cik, since)
    if first is not None and len(first) > 1:
        return from_cover_pages(client, cik, since=since, on_step=on_step)
    got.classes = {"0000": one} if one else {}
    return got


def _oldest_cover(client, cik: int, since: str) -> dict | None:
    """The class list from the earliest periodic filing in the window, or None."""
    subs = client.submissions(int(cik))
    filings = [f for f in subs.get("_filings", [])
               if (f.get("form") or "") in PERIODIC and (not since or (f.get("filingDate") or "") >= since)]
    filings.sort(key=lambda f: (f.get("filingDate") or ""))
    for f in filings[:3]:
        acc = f.get("accessionNumber") or ""
        try:
            name = f.get("primaryDocument")
            if not name:
                continue
            raw = client.primary_document(int(cik), acc, name)
        except Exception:  # noqa: BLE001
            continue
        facts = _facts_from_document(raw)
        if not facts:
            continue
        names = class_names(raw)
        return {names.get(ctx, ctx): v for ctx, v in facts.items()}
    return None


def _newest_cover(client, cik: int, since: str) -> dict | None:
    """The class list from the most recent periodic filing, or None."""
    subs = client.submissions(int(cik))
    filings = [f for f in subs.get("_filings", [])
               if (f.get("form") or "") in PERIODIC]
    filings.sort(key=lambda f: (f.get("filingDate") or ""), reverse=True)
    for f in filings[:3]:
        acc = f.get("accessionNumber") or ""
        try:
            name = f.get("primaryDocument")
            if not name:
                continue
            raw = client.primary_document(int(cik), acc, name)
        except Exception:  # noqa: BLE001
            continue
        facts = _facts_from_document(raw)
        if not facts:
            continue
        names = class_names(raw)
        return {names.get(ctx, ctx): v for ctx, v in facts.items()}
    return None
