"""The denominator: shares outstanding.

Source is dei:EntityCommonStockSharesOutstanding from the XBRL companyfacts
API -- the cover-page share count, free and machine-readable.

Two things to know.

1. Multi-class filers report this once PER CLASS on the cover page, but
   companyfacts does not preserve the class dimension. The classes therefore
   surface as several facts sharing an `end` date and `accn`. Summing within
   that group reconstructs total shares outstanding; the group size tells you
   how many classes there are.

2. companyfacts keeps only the LATEST value -- a restatement overwrites
   history. For a backtest this is fatal, so `snapshot()` freezes the values
   at ingest. Never re-pull a denominator for a historical period.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, asdict

from .edgar import EdgarClient

TAG = "EntityCommonStockSharesOutstanding"
FALLBACK_TAGS = ["CommonStockSharesOutstanding", "CommonStockSharesIssued"]


@dataclass
class OutstandingSnapshot:
    cik: int
    end_date: str
    filed_date: str
    accession: str
    form: str
    total_shares: float
    class_count: int
    per_class: list[float]
    tag_used: str
    captured_at: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _collect(facts: dict, taxonomy: str, tag: str) -> list[dict]:
    return (
        facts.get("facts", {})
        .get(taxonomy, {})
        .get(tag, {})
        .get("units", {})
        .get("shares", [])
    )


def outstanding_series(client: EdgarClient, cik: int) -> list[OutstandingSnapshot]:
    """Every cover-page share count, newest first, classes summed."""
    facts = client.company_facts(cik)

    entries: list[dict] = []
    tag_used = TAG
    entries = _collect(facts, "dei", TAG)
    if not entries:
        for alt in FALLBACK_TAGS:
            entries = _collect(facts, "us-gaap", alt)
            if entries:
                tag_used = alt
                break
    if not entries:
        return []

    # Group by (end, accession): one group == one cover page == all classes.
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for e in entries:
        groups[(e.get("end"), e.get("accn"))].append(e)

    out: list[OutstandingSnapshot] = []
    for (end, accn), members in groups.items():
        vals = [float(m["val"]) for m in members if m.get("val") is not None]
        if not vals:
            continue
        first = members[0]
        out.append(
            OutstandingSnapshot(
                cik=cik,
                end_date=end or "",
                filed_date=first.get("filed", ""),
                accession=accn or "",
                form=first.get("form", ""),
                total_shares=sum(vals),
                class_count=len(vals),
                per_class=sorted(vals, reverse=True),
                tag_used=tag_used,
            )
        )

    out.sort(key=lambda s: (s.filed_date, s.end_date), reverse=True)
    return out


def outstanding_as_of(
    client: EdgarClient, cik: int, as_of: str | None = None,
    skip_latest: bool = False,
) -> OutstandingSnapshot | None:
    """Share count available as of a date, keyed on FILED date.

    Keying on `filed` rather than `end` is the look-ahead guard: a Q1 cover
    page dated March is not knowable until the 10-Q is filed in May.
    """
    series = outstanding_series(client, cik)
    if skip_latest and series:
        # The quarter BEFORE the most recent one, so the two can be compared
        # to measure how fast the share count is actually moving.
        series = series[:-1]
    if not series:
        return None
    if as_of is None:
        return series[0]
    eligible = [s for s in series if s.filed_date and s.filed_date <= as_of]
    return eligible[0] if eligible else None


def snapshot(series: list[OutstandingSnapshot], captured_at: str) -> list[dict]:
    """Freeze denominators at ingest so restatements cannot rewrite history."""
    frozen = []
    for s in series:
        d = s.as_dict()
        d["captured_at"] = captured_at
        frozen.append(d)
    return frozen


# ---------------------------------------------------------------------------
# Denominator from the proxy document itself.
#
# companyfacts is unusable for multi-class issuers: they report share counts
# as DIMENSIONED facts (one per class), companyfacts strips dimensions, and
# nothing survives. Meta's companyfacts contains no dei tag and no
# CommonStockSharesOutstanding at all -- and multi-class is exactly the
# founder-led population that matters most here.
#
# The proxy states the number in plain text, on the same record date as the
# ownership table. That is a better source than the XBRL cover page anyway,
# because it removes a date mismatch between numerator and denominator.
# ---------------------------------------------------------------------------

import re as _re

_SHARE_COUNT = r"([\d]{1,3}(?:,\d{3})+)"

_NUM_RE = _re.compile(r"\b(\d{1,3}(?:,\d{3}){2,})\b")
_CLASS_RE = _re.compile(r"Class\s+([A-Z])\b", _re.I)


def shares_outstanding_from_proxy(text: str, window: int | None = None) -> dict:
    """Scrape total shares outstanding out of proxy prose.

    Sentence-based rather than one big regex, because the phrasings vary far
    more than a pattern list can anticipate: "there were X shares ...
    outstanding", "X shares of Class A common stock and Y shares of Class B
    common stock were outstanding", "based on X shares outstanding".

    Scans the WHOLE document. An earlier version looked only at the first
    400k characters and missed Meta entirely, because Meta puts its
    record-date share counts in the Q&A section at the end of a 1.3M-char
    proxy.

    Returns {"total": float|None, "per_class": {...}, "matches": [...]}.
    Takes the largest figure per class; proxies quote smaller partial counts
    alongside the record-date total.
    """
    haystack = text if window is None else text[:window]
    per_class: dict[str, float] = {}
    matches: list[str] = []
    matched_values: list[float] = []

    for sentence in _re.split(r"(?<=[.;])\s+", haystack):
        low = sentence.lower()
        if "outstanding" not in low or "share" not in low:
            continue
        if len(sentence) > 1200:
            continue
        # Skip option/plan sentences -- those counts are not shares outstanding.
        if _re.search(r"option|award|rsu|restricted|reserved for issuance|"
                      r"available for (?:future )?(?:grant|issuance)", low):
            continue
        # "ExxonMobil has authorized capital consisting of 9,000,000,000
        # shares of common stock" -- authorized is a charter ceiling, not a
        # share count. It beat the real 4,179,747,572 because the scraper
        # takes the largest figure per class.
        if _re.search(r"\bauthoriz\w+\b|\bpar value of\b|treasury", low):
            continue
        # Acquirable shares are not outstanding shares. Enova's footnote --
        # "This amount includes 1,023,200 shares that directors and executive
        # officers have the right to acquire within 60 days" -- was taken as
        # the denominator, making its CEO look like a 19.3% owner instead of
        # 0.8%. A 24x overstatement on the second-largest figure in the panel.
        if _re.search(r"right to acquire|may be acquired|deemed to be "
                      r"outstanding|subject to (?:stock )?options?", low):
            continue
        # A holding measured AGAINST the outstanding count is not the count.
        # Johnson & Johnson writes "In the aggregate, these 5,760,367 shares
        # represent less than 1% of the shares outstanding" in the paragraph
        # introducing its table -- the first region searched -- and that
        # became the denominator, against a real 2,408,613,219.
        if _re.search(r"represent\w*\s+(?:approximately\s+)?"
                      r"(?:less than\s+|more than\s+)?[\d.]+\s*%|"
                      r"(?:is|are|was|were)\s+(?:less|more) than\s+[\d.]+\s*%|"
                      r"\bof the (?:total\s+)?shares outstanding\b.*%|"
                      r"%\s+of (?:our|the|its)?\s*(?:total\s+)?"
                      r"(?:shares |common stock )?outstanding", low):
            continue

        # "6,659,444,154 shares of Class A common stock and Class B common
        # stock issued and outstanding, consisting of 5,823,665,113 shares of
        # Class A ..." -- the leading figure is a TOTAL of the classes that
        # follow. Counting both double-counts Alphabet by ~836M shares.
        consisting_at = sentence.lower().find("consisting of")

        for m in _NUM_RE.finditer(sentence):
            if consisting_at != -1 and m.start() < consisting_at:
                continue
            try:
                val = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            if val < 1_000_000:
                continue
            # Which class does this number belong to? Look just after it,
            # then just before, taking the nearest mention.
            after = sentence[m.end(): m.end() + 70]
            before = sentence[max(0, m.start() - 70): m.start()]
            cm = _CLASS_RE.search(after) or _CLASS_RE.search(before)
            key = f"Class {cm.group(1).upper()}" if cm else "Common"
            if val > per_class.get(key, 0):
                per_class[key] = val
                matches.append(_re.sub(r"\s+", " ", sentence)[:160])
                # Keep the value beside its sentence so each can be judged
                # on what the sentence actually says it is.
                matched_values.append(val)

    # A bare "Common" alongside named classes is usually a restatement of one
    # of them, not an extra class -- drop it to avoid double counting.
    if len(per_class) > 1 and "Common" in per_class:
        per_class.pop("Common")

    total = sum(per_class.values()) if per_class else None
    return {"total": total, "per_class": per_class, "matches": matches[:4],
            "matched_values": matched_values[:4]}


def denominator_is_credible(
    outstanding: float | None, group_shares: float | None
) -> tuple[bool, str]:
    """Sanity-check a scraped denominator against the group row.

    The aggregate held by all directors and officers is a hard floor: it
    cannot exceed the shares outstanding. Enova's scraped denominator implied
    the group held 213% of the company, which no reading of a filing
    supports.
    """
    if not outstanding:
        return False, "no denominator"
    if group_shares and group_shares > outstanding:
        return False, (
            f"directors and officers hold {group_shares:,.0f}, more than the "
            f"{outstanding:,.0f} shares said to be outstanding -- the "
            f"denominator is wrong"
        )
    return True, "plausible"


def implied_outstanding(shares: float | None, pct: float | None,
                        options_60d: float | None = None) -> float | None:
    """Back out the denominator from a row that states both shares and percent.

    Always available when any row shows a real percentage, and it is the
    filer's own arithmetic, so it needs no external source. Rule 13d-3(d)(1)(i)
    puts that holder's own options in their denominator, so remove them to
    recover plain shares outstanding.
    """
    if not shares or not pct or pct <= 0:
        return None
    denom_for_row = shares / (pct / 100.0)
    out = denom_for_row - (options_60d or 0)
    return out if out > 0 else None


# ---------------------------------------------------------------------------
# Resolving the denominator: agreement between sources, not faith in one.
#
# Nothing gives shares outstanding at the proxy record date in structured
# form. Schedule 14A Item 6(a) mandates that the proxy STATE it, but not how,
# and "outstanding" appears throughout ownership prose for unrelated reasons
# -- "deemed to be outstanding for the purpose of computing the percentage",
# "shares that may be acquired are deemed outstanding". Enova had four
# candidate numbers within a hundred words, and the scraper took a footnote
# about acquirable shares: its CEO was reported at 19.3% instead of 0.8%.
#
# The tagged cover-page figure is unambiguous but carries a different date.
# A quarter of drift is typically 0.5-2%; a mis-scrape is unbounded. So the
# tagged figure leads, and the others corroborate it.
# ---------------------------------------------------------------------------

RECORD_DATE_RE = _re.compile(
    r"record date[^.]{0,120}?(\w+ \d{1,2},\s*\d{4})|"
    r"(\w+ \d{1,2},\s*\d{4})[^.]{0,40}?\(the [\"“']?record date",
    _re.I,
)


@dataclass
class DenominatorCandidate:
    value: float
    source: str
    as_of: str | None = None
    note: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


MONTH_DATE_RE = _re.compile(
    r"([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})")
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}


def _to_iso(text: str | None) -> str | None:
    """"March 20, 2026" -> "2026-03-20". Returns None if unparseable."""
    if not text:
        return None
    if _re.match(r"^\d{4}-\d{2}-\d{2}$", text.strip()):
        return text.strip()
    m = MONTH_DATE_RE.search(text)
    if not m:
        return None
    month = MONTHS.get(m.group(1).lower())
    if not month:
        return None
    return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(2)):02d}"


def date_gap_days(a: str | None, b: str | None) -> int | None:
    """Days between two dates, either ISO or "March 20, 2026"."""
    from datetime import date
    ia, ib = _to_iso(a), _to_iso(b)
    if not ia or not ib:
        return None
    try:
        pa = date(*(int(x) for x in ia.split("-")))
        pb = date(*(int(x) for x in ib.split("-")))
    except (ValueError, TypeError):
        return None
    return abs((pa - pb).days)


@dataclass
class DenominatorResult:
    value: float | None = None
    source: str | None = None
    as_of: str | None = None
    record_date: str | None = None
    gap_days: int | None = None
    disagreement: float | None = None   # largest relative gap to another source
    region: str | None = None           # where in the proxy the figure was found
    # Both readings, kept separately. The resolved value is often the
    # model's, so a single column labelled "ours" hid which reader produced
    # the number actually being reported.
    parser_value: float | None = None
    model_value: float | None = None
    model_reading = None                # CountReading, when the model was used
    confirmed_by: int = 0
    spread: float | None = None
    candidates: list[DenominatorCandidate] = None
    notes: list[str] = None

    def __post_init__(self):
        if self.candidates is None:
            self.candidates = []
        if self.notes is None:
            self.notes = []


def record_date_from_proxy(text: str) -> str | None:
    m = RECORD_DATE_RE.search(text[:400_000])
    if not m:
        return None
    return (m.group(1) or m.group(2) or "").strip() or None


def implied_from_row(row) -> float | None:
    """Back the denominator out of a row's own percentage.

    This is the filer's arithmetic on the filer's date, so it needs no
    date adjustment at all. But Rule 13d-3(d)(1)(i) puts that holder's own
    60-day options into their denominator, so the result runs high by
    exactly those options -- 4.1% of the company for Enova's group row.
    Subtract them when the table breaks them out.
    """
    shares = getattr(row, "shares_reported", None)
    pct = getattr(row, "pct_reported", None)
    if not shares or not pct or pct <= 0:
        return None

    # Only valid when the share count and the percentage describe the SAME
    # class. In a multi-class table the shares are summed across classes
    # while the percentage belongs to one of them, so dividing gives a
    # meaningless figure: Peter Thiel's three-class total over his Class A
    # percentage implies 3,277,833,333 shares against Palantir's real
    # 2,397,157,109 -- a 37% disagreement invented entirely by the
    # calculation.
    if "xclass" in (getattr(row, "notes", "") or ""):
        return None
    denom = shares / (pct / 100.0)
    opts = getattr(row, "options_60d", None)
    if opts:
        denom -= opts
    return denom if denom > 0 else None


# ---------------------------------------------------------------------------
# Region-first extraction.
#
# Item 6(a) mandates that the proxy state shares outstanding, but not where.
# Searching two million characters for it is the wrong shape of problem: the
# word "outstanding" appears constantly in unrelated senses -- "deemed to be
# outstanding for the purpose of computing the percentage", "shares that may
# be acquired are deemed outstanding" -- and a pattern cannot prefer one
# sense over another.
#
# But the correct figure is rarely far away. Filers state it where they need
# it, which is beside the ownership table:
#
#   Enova     "...is based on the number of shares of our Common Stock issued
#              and outstanding on March 20, 2026, which was 24,945,366."
#   Cabot     "The calculation of percentage of ownership ... is based on
#              52,221,604 shares of Cabot common stock..."
#   Tesla     "Applicable percentage ownership is based on 3,325,150,886
#              shares of Tesla's common stock outstanding..."
#
# All three sit in the paragraph introducing the table or in its footnotes --
# a region already located and already captured. Searching there first turns
# an open-ended hunt into a small one, which is what made the numerator
# tractable. The whole document remains a fallback, but it is where the wrong
# answers live.
# ---------------------------------------------------------------------------

# Language tying a figure to the ownership calculation itself. A number in a
# sentence like this is the denominator by construction.
# The proxy Q&A heading where Item 6(a) is most often satisfied. Palantir
# answers it with a total and a per-class breakdown; most filers phrase it
# within a word or two of this. Far more reliable than scanning the document
# and taking the largest number.
ENTITLED_TO_VOTE_RE = _re.compile(
    r"how many shares (?:are|were) outstanding|"
    r"shares? (?:are|were) outstanding and entitled to vote|"
    r"outstanding and entitled to vote (?:as of|on) the record date|"
    r"who is entitled to vote",
    _re.I,
)

BASIS_PHRASE_RE = _re.compile(
    r"percentage[s]? (?:of )?(?:ownership|beneficial ownership)|"
    r"ownership percentage|is based (?:up)?on|are based (?:up)?on|"
    r"calculation of percentage|percent(?:age)? of class is",
    _re.I,
)


def denominator_regions(
    proxy_html: str,
    table_context: str | None = None,
    footnotes: str | None = None,
    preceding: str | None = None,
) -> list[tuple[str, str]]:
    """Text to search, most reliable region first.

    Returns (region_name, text) so the winning region can be reported --
    knowing a figure came from the table's own footnote rather than from
    somewhere in the document is most of what tells you to trust it.
    """
    regions: list[tuple[str, str]] = []
    # The introduction comes first. Capital One states its count there, and
    # so do most filers -- it is the sentence that makes the percentages in
    # the table meaningful.
    if preceding:
        regions.append(("table_introduction", preceding))
    if footnotes:
        regions.append(("table_footnotes", footnotes))
    # The table body is deliberately NOT searched. Item 403 governs the table
    # and it reports HOLDINGS; Item 6(a) requires the outstanding count and is
    # satisfied in prose. Every filing examined states it in text -- Costco,
    # Capital One, Tesla, ServiceNow, Enova in a paragraph, Cabot in a
    # footnote -- and none states it in the table.
    #
    # Searching the table body took BlackRock's 158,217,849 Class A holding as
    # Palantir's share count, because its header reads "Percentage of Votes
    # (Record Date Outstanding Shares)" and the flattened table therefore
    # looks like a sentence about shares outstanding. Karp was reported at
    # 59.2% instead of 3.9%.
    _ = table_context

    text = _re.sub(r"<[^>]+>", " ", proxy_html)
    text = _re.sub(r"&nbsp;?|&#160;", " ", text)

    # The "how many shares are outstanding" question, answered directly.
    for m in ENTITLED_TO_VOTE_RE.finditer(text):
        window = text[m.start(): m.start() + 1800]
        if _NUM_RE.search(window):
            regions.append(("entitled_to_vote_qa", window))
            break

    # Sentences that explicitly tie a number to the ownership calculation,
    # wherever they appear.
    basis = [sent for sent in _re.split(r"(?<=[.;])\s+", text)
             if BASIS_PHRASE_RE.search(sent) and "outstanding" in sent.lower()]
    if basis:
        regions.append(("ownership_basis_sentence", " ".join(basis[:6])))

    # The record-date paragraph, which Item 6(a) is usually satisfied in.
    for m in _re.finditer(r"record date", text[:600_000], _re.I):
        window = text[max(0, m.start() - 700): m.start() + 700]
        if _NUM_RE.search(window):
            regions.append(("record_date_paragraph", window))
            break

    regions.append(("whole_document", text))
    return regions


# Every way a filer might say it. The sweep below is about RECALL: get the
# answer in front of the model somewhere, and let it decide which mention is
# the count. The targeted regions above are about precision and exist for the
# regex path, which cannot reason and so must be pointed at the right place.
MENTION_RE = _re.compile(
    r"shares?\s+(?:of\s+(?:our\s+|the\s+)?[\w\s]{0,30}?stock\s+)?"
    r"(?:issued\s+and\s+)?outstanding|"
    r"outstanding\s+shares?\s+of|"
    r"(?:issued\s+and\s+)?outstanding\s+(?:common|capital|voting)\s+stock|"
    r"shares?\s+entitled\s+to\s+vote|"
    r"total\s+(?:number\s+of\s+)?shares?\s+outstanding",
    _re.I,
)


def outstanding_mentions(
    proxy_html: str,
    radius: int = 400,
    max_windows: int = 12,
) -> str:
    """Every mention of shares outstanding, with context around each.

    The targeted regions were each added after a company failed: the voting
    Q&A came from Palantir, the table introduction from Capital One. That is
    a list built from hindsight, and it will keep missing filers whose
    phrasing nobody has hit yet -- three companies in the last run found no
    region at all.

    A sweep cannot miss the sentence for want of the right heading. It
    returns several candidates rather than one, which a regex could not
    resolve, but a reader can.
    """
    text = _re.sub(r"<[^>]+>", " ", proxy_html)
    text = _re.sub(r"&nbsp;?|&#160;|&amp;", " ", text)
    text = _re.sub(r"\s+", " ", text)

    spans: list[tuple[int, int]] = []
    for m in MENTION_RE.finditer(text):
        lo, hi = max(0, m.start() - radius), min(len(text), m.end() + radius)
        # Only worth sending if there is a number in it that could be a
        # share count at all.
        if not _NUM_RE.search(text[lo:hi]):
            continue
        if spans and lo <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], hi))   # merge overlaps
        else:
            spans.append((lo, hi))
        if len(spans) >= max_windows:
            break

    return "\n---\n".join(text[lo:hi].strip() for lo, hi in spans)


def regions_for_model(
    proxy_html: str,
    footnotes: str | None = None,
    preceding: str | None = None,
) -> list[tuple[str, str]]:
    """What the reader sees: the targeted regions, plus every mention.

    Recall first. A reader given several candidates can pick the right one;
    a reader given none cannot.
    """
    regions = [(n, t) for n, t in
               denominator_regions(proxy_html, None, footnotes, preceding)
               if n != "whole_document"]
    sweep = outstanding_mentions(proxy_html)
    if sweep:
        regions.append(("every_mention_of_shares_outstanding", sweep))
    return regions


def outstanding_by_region(
    proxy_html: str,
    table_context: str | None = None,
    footnotes: str | None = None,
    preceding: str | None = None,
) -> tuple[dict, str]:
    """Scrape shares outstanding, nearest region first. -> (result, region)."""
    for name, text in denominator_regions(
            proxy_html, table_context, footnotes, preceding):
        found = shares_outstanding_from_proxy(text, window=None)
        if found["total"]:
            return found, name
    return {"total": None, "per_class": {}, "matches": []}, "not_found"


def resolve_denominator(
    proxy_html: str,
    xbrl_snapshot,
    all_rows: list,
    group_row=None,
    agree_within: float = 0.02,
    always_prefer_proxy: bool = True,
    classify: bool = False,
    table_context: str | None = None,
    footnotes: str | None = None,
    preceding: str | None = None,
) -> DenominatorResult:
    """Report the proxy's own figure; use other sources to check it.

    With always_prefer_proxy (the default), the proxy's stated count is used
    whenever it survives the plausibility floor, and the other sources only
    raise flags. The column then means one thing for every company -- "what
    the proxy says" -- and shares a date with the numerator, so the
    percentage is computed on the basis the filer used.

    The alternative, switching sources when they disagree, makes the column
    mean different things for different companies and reintroduces the date
    mismatch it was meant to remove. Disagreement is surfaced instead, as
    `disagreement` and a flag, so a doubtful figure is visible rather than
    quietly replaced.

    The plausibility floor still applies, and is not an outside source: it
    compares the count against the group row in the SAME proxy. Enova's
    footnote figure implied its directors held 213% of the company.
    """
    res = DenominatorResult()
    cands: list[DenominatorCandidate] = []

    scraped, region = outstanding_by_region(
        proxy_html, table_context, footnotes, preceding)

    if scraped["total"]:
        cands.append(DenominatorCandidate(
            scraped["total"], "proxy_text",
            record_date_from_proxy(proxy_html),
            f"{len(scraped['per_class'])} class(es), found in {region}"))
    res.region = region

    # The model reads the parser's candidate REGIONS rather than being handed
    # a number to judge. That takes the number-extraction regex off the
    # critical path: every phrasing a filer might use has to survive it, and
    # each exclusion in it was written after a company was already reported
    # wrong. The parser still does the locating, which it does well.
    if classify:
        from .reader import read_share_count
        reading = read_share_count(
            regions_for_model(proxy_html, footnotes, preceding))
        res.model_reading = reading
        if reading.shares_outstanding and not reading.error:
            cands.append(DenominatorCandidate(
                reading.shares_outstanding, "model_read_regions", reading.as_of,
                (reading.quote or "")[:90]
                + ("" if reading.quote_verified else " [UNVERIFIED QUOTE]")))

    if xbrl_snapshot is not None:
        cands.append(DenominatorCandidate(
            xbrl_snapshot.total_shares, "xbrl_cover_page",
            xbrl_snapshot.end_date, xbrl_snapshot.tag_used))

    if group_row is not None:
        v = implied_from_row(group_row)
        if v:
            cands.append(DenominatorCandidate(
                v, "implied_from_group_row", None,
                "filer's own arithmetic; high by any undisclosed group options"))

    for r in all_rows:
        if getattr(r, "is_group_row", False):
            continue
        v = implied_from_row(r)
        if v:
            cands.append(DenominatorCandidate(
                v, "implied_from_a_row", None,
                f"from {getattr(r, 'name_raw', '?')[:28]}"))
            break

    # Anything smaller than the shares insiders hold is impossible.
    floor = getattr(group_row, "shares_reported", None) if group_row else None
    if floor:
        kept = [c for c in cands if c.value >= floor]
        if len(kept) < len(cands):
            dropped = [c.source for c in cands if c.value < floor]
            res.notes.append(
                f"rejected {', '.join(dropped)}: below the {floor:,.0f} shares "
                f"held by directors and officers")
            cands = kept

    res.candidates = cands
    if not cands:
        res.notes.append("no usable denominator from any source")
        return res

    # Prefer a value two independent sources agree on.
    best: tuple[int, float, DenominatorCandidate] | None = None
    for c in cands:
        agreeing = sum(1 for o in cands
                       if o is not c
                       and abs(o.value - c.value) / max(c.value, 1) <= agree_within)
        # Agreement is the first sort key, so an unconfirmed prose figure
        # never beats a confirmed one no matter how well it is dated.
        # The proxy's own figure leads, but only once corroborated. It is
        # the sole source dated to the record date, which is also the date
        # the numerator uses -- so the percentage is computed on the basis
        # the filer used, with no internal date mismatch.
        #
        # Prose was demoted at one point because its failures are unbounded
        # (Enova 24x, Exxon's authorized capital). That reasoning applied to
        # an UNVALIDATED scrape. Both of those are now rejected before they
        # reach this ranking: the group-row floor catches anything smaller
        # than what insiders hold, and a lone figure that no other source
        # confirms cannot outrank agreement.
        rank = {"proxy_text": 0, "xbrl_cover_page": 1,
                "implied_from_group_row": 2, "implied_from_a_row": 3}
        key = (-agreeing, rank.get(c.source, 9))
        if best is None or key < (-best[0], rank.get(best[2].source, 9)):
            best = (agreeing, c.value, c)

    # The proxy's figure wins outright when it survived the floor.
    if always_prefer_proxy:
        # The model's reading of the same regions supersedes the regex's, when
        # available: both look at the identical text, and only one of them can
        # tell a holding from a count.
        proxy_cand = next(
            (c for c in cands if c.source == "model_read_regions"), None)
        proxy_cand = proxy_cand or next(
            (c for c in cands if c.source == "proxy_text"), None)
        if proxy_cand is not None:
            agreeing = sum(
                1 for o in cands if o is not proxy_cand
                and abs(o.value - proxy_cand.value) / max(proxy_cand.value, 1)
                <= agree_within)
            best = (agreeing, proxy_cand.value, proxy_cand)

    agreeing, value, chosen = best
    res.value, res.source, res.as_of = chosen.value, chosen.source, chosen.as_of
    res.parser_value = next((c.value for c in cands
                             if c.source == "proxy_text"), None)
    res.model_value = next((c.value for c in cands
                            if c.source == "model_read_regions"), None)
    others = [c for c in cands if c is not chosen]
    if others:
        res.disagreement = max(
            abs(o.value - chosen.value) / max(chosen.value, 1) for o in others)
    # How stale is the figure we chose, measured against the record date the
    # percentages are actually computed on? Reported rather than assumed.
    res.record_date = record_date_from_proxy(proxy_html)
    res.gap_days = date_gap_days(chosen.as_of, res.record_date)
    res.confirmed_by = agreeing
    vals = [c.value for c in cands]
    res.spread = (max(vals) - min(vals)) / max(min(vals), 1) if len(vals) > 1 else 0.0

    if agreeing == 0 and len(cands) > 1:
        res.notes.append(
            "using the proxy figure; other sources disagree: " + ", ".join(
                f"{c.source}={c.value:,.0f}" for c in cands if c is not chosen))
    elif agreeing:
        res.notes.append(f"confirmed by {agreeing} other source(s)")
    else:
        res.notes.append(f"single source ({chosen.source}), unconfirmed")
    return res
