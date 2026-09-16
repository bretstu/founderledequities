"""One company's answer, and what has to agree before it is published.

    ownership = common stock the chief executive holds
                --------------------------------------
                shares outstanding on the latest cover page

Both are structured. Neither is prose. No model runs.

WHY THIS METRIC AND NOT v1'S. v1 counted options exercisable within sixty
days in the numerator, over a denominator that excludes them. That is not
merely imprecise, it is directionally wrong: exercising an option issues
shares, so the denominator grows while the numerator does not, and the figure
FALLS as the person acquires stock. Musk exercised 303,960,630 options and
v1's metric moved him from 21.6% to 19.8%.

    common / outstanding            rises on exercise   correct
    13d-3 / (outstanding + theirs)  unchanged           not comparable
    13d-3 / outstanding    (v1)     falls               wrong

Common over outstanding is also the only one continuous with the source
data: Form 4 Table I reports common stock, so anchor and updates measure the
same quantity, and a series built from them has no discontinuity.

WHAT IS COUNTED. Issued common, including unvested restricted stock -- which
is issued, votable, and in the denominator, so excluding it would make this
the outlier. It is flagged rather than removed, because it matters to what a
stake is worth far more than to what fraction it represents.

CHECKS. Losing the proxy loses the one independent statement of the same
number, and every ledger bug found in v1 was caught by an outside reference
rather than by internal logic. So the checks here are deliberately about
whether the ledger is COMPLETE, not whether it is arithmetically consistent
with itself -- which it always is, including when it is wrong.

CONFIDENCE WEIGHS FLAGS, IT DOES NOT COUNT THEM. Counting made "denominator
sums 2 share classes" -- which is the correct behaviour for a dual-class
filer, not a defect -- weigh the same as a line missing from the total. Meta
came back LOW while matching its own proxy to the share, and Apple slipped
from high to medium for one dropped line.

Three severities, assigned where each flag is raised:

  note      correct behaviour worth recording
  caution   a judgment was made, or two dates are far apart
  problem   data is known to be missing

A rating describes what can be vouched for, not what happens to be true. Meta
still rates low, because a line whose balance was only ever footnoted might
hold anything -- that it turned out to be nothing is not something the code
can know.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from .config import SETTINGS
from .schedule13 import is_foreign_reporter, stake_from_schedule13
from .identity import peo_from_certification
from .ledger import build_ledger, retired_classes, closed_groups, title_letter
from .splits import fetch_splits
from .successor import find_predecessor
from .outstanding import shares_outstanding, jumped


NOTE, CAUTION, PROBLEM = "note", "caution", "problem"


@dataclass
class Ownership:
    cik: int
    company: str = ""
    ceo: str = ""
    ceo_source: str = ""
    owner_cik: str = ""
    filed_under: int | None = None     # when the history is under another CIK
    owner_name: str = ""          # as EDGAR spells it, which may not be a person
    is_officer: bool = False      # the one signal that says it IS the CEO

    shares: float | None = None
    # "SC 13G/A 2024-02-13" when the figure came from a Schedule 13D/G
    # (foreign-regime fallback) rather than Section 16; empty otherwise.
    stake_source: str = ""
    outstanding: float | None = None
    pct: float | None = None

    shares_as_of: str = ""
    outstanding_as_of: str = ""
    gap_days: int | None = None

    lines: int = 0
    options: float = 0.0
    # Every uncounted security, largest first, as the filings name them.
    # A CEO commonly holds several: options, RSUs and PSUs at once, and at an
    # up-C, partnership units alongside them. A single total cannot tell
    # unvested pay apart from already-issued equity in an operating entity,
    # and that distinction is the whole question -- so the titles travel too.
    option_titles: str = ""
    # An up-C or UPREIT, flagged so the analytics layer can segment these
    # rather than treat them as ordinary companies that happen to look odd.
    partnership_units: float = 0.0
    operating_partnership: bool = False

    # HOW THE STAKE WAS ACQUIRED, over their whole filing history. Lifetime
    # flows, never a position: someone can buy a million shares and sell a
    # million, so these answer "how did they come by stock", not "what do
    # they still hold".
    held_at_start: float = 0.0     # on the Form 3 -- a founding stake
    founded_share: float | None = None
    bought: float = 0.0            # code P, their own money
    granted: float = 0.0           # code A, the company's
    from_derivative: float = 0.0   # codes M, C, X -- a grant, one step on
    sold: float = 0.0              # code S
    surrendered: float = 0.0       # codes D, F, U -- withholding is not a sale
    bought_share: float | None = None   # of all acquisitions, what was bought
    codes: str = ""                # the full tally, for checking the rest
    # WHAT THE CLOSED-LINE RULE REMOVED. It fired on 130 of 500 companies and
    # the flag said only how many lines -- never how many shares, nor which.
    # A rule that deletes data has to show its work in the sheet, not only on
    # a console nobody reads.
    # A holding the company itself says is not theirs, removed from the
    # curated list. Never silent: the row says what went and why.
    excluded_shares: float = 0.0
    excluded_detail: str = ""
    single_class: bool = False     # the security title was not used
    classes: str = ""              # the classes the company names
    # A security whose class the cover page does not name -- excluded,
    # because the denominator has no room for it.
    unnamed_class: str = ""
    splits: str = ""               # every split applied, and when
    split_note: str = ""           # why none were, if none were
    flow_residual: float = 0.0     # holding minus what the flows explain
    flows_reconcile: bool = False  # can these columns safely be added up?
    converted: str = ""
    share_classes: int = 1

    filings_read: int = 0
    settled: bool = False
    confidence: str = "none"
    flags: list = field(default_factory=list)          # text, for the CSV
    graded: list = field(default_factory=list)         # (severity, text)
    error: str = ""
    # Where to look to check the row. A panel without these is a list of
    # assertions; with them it is a worksheet.
    form4_url: str = ""
    remarks: str = ""              # the newest filing's remark, verbatim (structural presence; prose never parsed)
    shares_tabled: float | None = None   # when a supplement was injected: what the tables alone report
    cover_url: str = ""

    @property
    def acquired_total(self) -> float:
        return self.bought + self.granted + self.from_derivative

    def as_dict(self) -> dict:
        d = asdict(self)
        d["flags"] = "|".join(self.flags)
        d["graded"] = "|".join(f"{lvl}:{txt}" for lvl, txt in self.graded)
        return d


def _titles(by_title: dict, keep: int = 2) -> str:
    """The largest uncounted securities, as the filer named them.

    TRIMMED, NOT REMOVED. The full dump ran to 6,416 distinct strings across
    the index and was unreadable -- but it is the only way to check whether
    `operating_partnership` classified a row correctly, and that flag comes
    from a title match, which is the one technique worth distrusting.

    Two is enough: the largest decides the classification, and the second
    shows when a CEO holds units and pay at once.
    """
    ordered = sorted(by_title.items(), key=lambda kv: -kv[1])
    out = " | ".join(f"{t} = {v:,.0f}" for t, v in ordered[:keep])
    if len(ordered) > keep:
        out += f" | +{len(ordered) - keep} more"
    return out


def _flows(rec: "Ownership", led) -> None:
    fl = led.flows
    rec.bought = fl.bought
    rec.granted = fl.granted
    rec.from_derivative = fl.from_derivative
    rec.sold = fl.sold
    rec.surrendered = fl.surrendered
    rec.held_at_start = fl.opening
    rec.founded_share = fl.founded_share
    rec.bought_share = fl.bought_share
    rec.codes = fl.tally()
    if rec.shares is not None:
        rec.flow_residual, share = fl.reconcile(rec.shares)
        rec.flows_reconcile = share is not None and share < 1.0


def _days(a: str, b: str) -> int | None:
    from datetime import date
    try:
        ya, ma, da = (int(x) for x in a.split("-"))
        yb, mb, db = (int(x) for x in b.split("-"))
        return abs((date(ya, ma, da) - date(yb, mb, db)).days)
    except Exception:  # noqa: BLE001
        return None


def cover_in_todays_basis(shares, as_of: str, splits=None):
    """The cover page's count carried through every split after its date, so
    it is in the same shares as the holding; unchanged with no split table."""
    if not shares or not splits or not as_of:
        return shares
    return shares * splits.factor_since(as_of)


def build(client, cik: int, company: str = "", ticker: str = "",
          owner_name: str | None = None, exclusions=None,
          on_progress=None) -> Ownership:
    rec = Ownership(cik=int(cik), company=company)

    def flag(level: str, text: str) -> None:
        rec.graded.append((level, text))
        rec.flags.append(text)

    if not owner_name:
        cert = peo_from_certification(client, cik)
        if not cert:
            rec.error = "no Section 302 certification found; cannot name the CEO"
            return rec
        owner_name, rec.ceo_source = cert.name, f"{cert.form} {cert.filing_date}"
    rec.ceo = owner_name

    splits = fetch_splits(client, ticker, SETTINGS.polygon_api_key)
    if splits.events:
        # only a company the feed says has split pays for its cover series;
        # the covers are what corroborate the feed (splits.corroborate)
        from .series import denominator_series
        try:
            first = min(e.date for e in splits.events)
            since = f"{int(first[:4]) - 2}-01-01"
            covers = denominator_series(client, cik, since=since)
            splits.disown_before_first_cover(covers)   # a predecessor's event on the same ticker is not this registrant's
            splits.corroborate(covers)
        except Exception as exc:  # noqa: BLE001 - no covers to judge by: the feed stands, and the note says so
            splits.note = splits.note or f"could not corroborate the splits against the cover pages: {exc}"
    rec.splits = splits.describe()
    if not splits.ok:
        rec.split_note = splits.note

    # THE DENOMINATOR FIRST, for its class count. The ledger needs to know
    # whether this company has one class before it can decide whether the
    # security title means anything.
    out = shares_outstanding(client, cik)
    led = build_ledger(client, cik, owner_name=owner_name, splits=splits,
                       share_classes=out.classes if out.ok else 0,
                       class_members=out.per_class,
                       exclude=exclusions.for_issuer(cik) if exclusions else (),
                       on_progress=on_progress)

    # A SUCCESSOR FILES UNDER ITS PREDECESSOR'S CIK. Only reached when the
    # normal path found nothing, so it cannot disturb a company that works.
    if not led.lines and not led.owner_cik:
        pre = find_predecessor(client, cik, owner_name)
        if pre.cik:
            rec.filed_under = pre.cik
            flag(NOTE, f"insider history is under CIK {pre.cik} ({pre.name}); "
                       f"verified by finding {pre.matched_owner} there")
            out = shares_outstanding(client, pre.cik)
            led = build_ledger(client, pre.cik, owner_name=owner_name,
                               splits=splits,
                               share_classes=out.classes if out.ok else 0,
                               class_members=out.per_class,
                               exclude=(exclusions.for_issuer(pre.cik)
                                        if exclusions else ()),
                               on_progress=on_progress)

    # OWNING NOTHING IS AN ANSWER. Verizon's Daniel Schulman has filed 32
    # times and holds no common stock -- he was a director before becoming
    # chief executive, and directors are paid in deferred stock units, which
    # are derivatives rather than shares. A.O. Smith's Stephen Shafer is the
    # same shape.
    #
    # Treating that as an error dropped both companies from the panel, when
    # for a site about how much chief executives own, "nothing at all" is one
    # of the more interesting rows on it. There will always be a few: every
    # newly appointed CEO starts here.
    #
    # A failure to READ and a genuine zero must not look alike, so this
    # requires that the person was located AND filed something.
    if not led.lines:
        if led.owner_cik and led.filings_read > 0:
            rec.owner_cik = led.owner_cik
            rec.owner_name = led.owner_name
            rec.is_officer = led.officer
            rec.shares = 0.0
            rec.lines = 0
            rec.options = led.options
            rec.option_titles = _titles(led.option_titles)
            rec.partnership_units = led.partnership_units
            rec.operating_partnership = bool(led.partnership_units)
            _flows(rec, led)
            rec.filings_read = led.filings_read
            rec.settled = led.settled
            rec.shares_as_of = led.last_filing
            rec.form4_url = led.last_url
            rec.remarks = led.last_remarks
        else:
            # FOREIGN-REGIME FALLBACK. A 20-F/40-F issuer's insiders are
            # exempt from Section 16 (Rule 3a12-3(b)), so an empty ledger
            # here is the regime, not the person. But a >5% CEO still
            # files Schedule 13D/G about the company -- Lütke's 13G/A
            # states 80,997,982 SHOP shares, 6.3% -- so before giving up,
            # read those. Only reached when Section 16 found nothing, so
            # it cannot disturb a company the normal path serves.
            try:
                subs = client.submissions(cik)
            except Exception:  # noqa: BLE001
                subs = {}
            if is_foreign_reporter(subs):
                stake = stake_from_schedule13(client, cik, owner_name)
                if stake:
                    rec.shares = stake.shares
                    rec.shares_as_of = stake.filing_date
                    rec.form4_url = stake.url
                    rec.stake_source = f"{stake.form} {stake.filing_date}"
                    rec.confidence = "low"
                    flag("problem",
                         f"foreign-regime issuer: stake from {stake.form} "
                         f"dated {stake.filing_date}; no U.S. transaction "
                         f"filings exist")
                    if stake.percent is not None:
                        flag("note", f"schedule reports {stake.percent}% of class")
                    return rec
                rec.error = ("foreign-regime issuer (20-F/40-F): insiders "
                             "exempt from Section 16; no Schedule 13D/G "
                             "stake found for this person")
                return rec
            rec.error = led.note or "no Section 16 holdings found"
            return rec

    rec.owner_cik = led.owner_cik
    rec.owner_name = led.owner_name
    rec.is_officer = led.officer
    # A shared surname is common at family-controlled companies, so a
    # runner-up is expected. Only a NARROW win is worth a flag.
    # THE OFFICER CHECK IS ONLY HALF A SAFEGUARD WITHOUT THIS. It ranks an
    # officer above a namesake vehicle -- but when nothing competes, a lone
    # trust matches the name perfectly, wins by a wide margin, and passes
    # every other test. The certification names a principal executive
    # officer, so a match that is not flagged as an officer is the wrong
    # person until someone says otherwise.
    if led.owner_cik and not led.officer:
        flag(PROBLEM, f"the matched insider ({led.owner_name}) is not flagged "
                      f"as an officer on any filing; this may be a trust or "
                      f"entity named after the chief executive")
    if led.partial_match:
        flag(CAUTION, f"matched on shared name parts ({led.partial_match:.2f}) "
                      f"plus a plain chief-executive title, not on the name "
                      f"itself: certification says {rec.ceo}, EDGAR says "
                      f"{led.owner_name}")
    if led.tied:
        flag(CAUTION, f"{len(led.tied)+1} CIKs matched the name equally: "
                      + "; ".join(led.tied))
    if led.match_score and (led.match_score < 0.9 or led.margin < 0.15):
        flag(CAUTION, f"insider matched at {led.match_score:.2f}"
                      + (f", next best {led.runner_up:.2f}" if led.runner_up else ""))
    for _d, _f, why in splits.disowned:
        flag(CAUTION, f"a split in the feed was not applied: {why}")
    for _d, _f, why in splits.doubts:
        flag(CAUTION, f"a split the cover pages do not corroborate: {why}")
    # A CLASS THE COMPANY RETIRED IS CLOSED (ledger.retired_classes, 2026-09-16):
    # the cover pages say when a class stopped existing; a group of that
    # class stated before then is not counted, and the page says so. Read
    # only when the walk discovered a lettered class under a one-class cover.
    led.retired = {}
    if led.single_class and any(title_letter(t) and title_letter(t)[1] for t in led.discovered_classes):
        try:
            from .series import from_cover_pages
            led.retired = retired_classes(from_cover_pages(client, cik, since="2016-01-01"), remaining=led.dominant)
        except Exception:  # noqa: BLE001 - no covers to read: nothing is retired
            led.retired = {}
    for _k, g, cut in closed_groups(led.groups, led.retired):
        flag(CAUTION, f"a class the company retired is not counted: {g.security} last stated {g.filed or g.as_of} "
                      f"({g.shares:,.0f} shares); the cover pages stop listing the class from {cut}")
    rec.shares = led.total
    rec.shares_as_of = led.last_filing
    rec.lines = len(led.lines)
    rec.options = led.options
    rec.option_titles = _titles(led.option_titles)
    rec.partnership_units = led.partnership_units
    rec.operating_partnership = bool(led.partnership_units)
    _flows(rec, led)
    rec.excluded_shares = sum(v[0] for v in led.excluded.values())
    rec.excluded_detail = " | ".join(f"{lab} = {sh:,.0f}: {why}"
                                     for lab, (sh, why, _) in led.excluded.items())
    rec.single_class = led.single_class
    rec.classes = "|".join(led.classes)
    rec.unnamed_class = " | ".join(
        f"{t} = {v:,.0f}" for t, v in
        sorted(led.unnamed_class.items(), key=lambda kv: -kv[1])[:3])
    rec.converted = "|".join(sorted(set(led.converted)))
    # A SUPPLEMENT THE WALK INJECTED (fle/exclusions.py): the row says so,
    # keeps the tables' own figure beside the total, and carries the receipt.
    if led.supplemented and rec.shares is not None:
        added = sum(sh for sh, _ in led.supplemented.values())
        rec.shares_tabled = rec.shares - added
        rec.stake_source = "manual"
        for sec, (sh, note) in led.supplemented.items():
            rec.graded.append(("caution",
                f"includes {int(sh):,} shares of {sec} the filings disclose in a remark rather than a table; "
                f"{int(rec.shares_tabled):,} in the tables. {note}"))
    # A CLASS CARRIED THROUGH A SPLIT IS SAID (2026-09-15): the number is
    # right by the split table, and a person should know which filing it
    # rests on, because no Form 4 has restated it
    from .ledger import carried_through_split
    for sec, asof, f in carried_through_split(led.groups, led.splits):
        rec.graded.append(("caution",
            f"{sec} is carried from the filing of {asof} and restated {f:g}x through the split(s) since; "
            f"no filing has restated the class itself"))
    rec.filings_read = led.filings_read
    rec.settled = led.settled
    rec.form4_url = led.last_url
    rec.remarks = led.last_remarks

    if led.excluded:
        flag(NOTE, f"{rec.excluded_shares:,.0f} shares excluded from the "
                   f"curated list: " + " | ".join(
                       f"{lab} ({src})" for lab, (_, _, src) in
                       led.excluded.items()))
    if getattr(led, "discovered_classes", None):
        names = ", ".join(sorted(led.discovered_classes)[:3])
        flag("problem",
             f"class(es) counted from the person's filings but absent from "
             f"the cover page: {names}; the denominator may not include them")
    if led.unnamed_class:
        total = sum(led.unnamed_class.values())
        flag(CAUTION, f"{len(led.unnamed_class)} security title(s) name a class "
                      f"the cover page does not list, holding up to "
                      f"{total:,.0f} shares; excluded, because the denominator "
                      f"has no room for them: {rec.unnamed_class[:90]}")
    if rec.operating_partnership:
        flag(NOTE, f"{rec.partnership_units:,.0f} in an operating partnership "
                   f"-- already issued and exchangeable into this issuer's "
                   f"stock, but not part of it")
    if rec.lines == 0:
        if led.options:
            # NAME THE SECURITIES, DO NOT GUESS THE STRUCTURE. This asserted
            # "typically an exchangeable interest in an operating
            # partnership" for anyone holding nothing -- true of Schwarzman's
            # Blackstone Holdings units, false of Schulman, whose Verizon
            # holding is director DEFERRED STOCK UNITS and has nothing to do
            # with a partnership.
            #
            # The filings say what these are. Repeating that is accurate for
            # both, and for whatever the next shape turns out to be.
            what = "; ".join(t for t, _ in sorted(led.option_titles.items(),
                                                  key=lambda kv: -kv[1])[:3])
            flag(CAUTION, f"holds no common stock, but {led.options:,.0f} of: "
                          f"{what or 'units or options'} -- not counted, "
                          f"because it is not issued stock of this issuer")
        else:
            # No common stock and nothing uncounted either: they own none of
            # the company, and that is simply the answer.
            flag(NOTE, "holds no common stock")

    if out.ok:
        # THE DENOMINATOR IS RESTATED THROUGH THE SAME SPLITS (2026-09-15).
        # The holding is now in today's shares (ledger.groups_total), so the
        # cover page must be too: a cover page filed before a split is
        # carried through it, as the walk has done since Nvidia's 10-for-1
        # (a Form 4 the week after the split, the cover three months later:
        # 35.3% for a man who owns 3.5%). Both sides of the split on both
        # sides of the fraction, or neither: never one.
        rec.outstanding = cover_in_todays_basis(out.shares, out.counted or out.as_of, splits)
        rec.outstanding_as_of = out.as_of
        rec.share_classes = out.classes
        rec.cover_url = out.url
        rec.pct = rec.shares / rec.outstanding * 100
        if rec.outstanding != out.shares:
            flag(CAUTION, f"shares outstanding restated {rec.outstanding / out.shares:g}x through the split(s) "
                          f"since the cover page of {out.as_of} ({out.shares:,.0f} as filed)")
        rec.gap_days = _days(rec.shares_as_of, rec.outstanding_as_of)
        # A DENOMINATOR SMALLER THAN THE NUMERATOR IS NOT A DENOMINATOR.
        # Nothing else in the pipeline would have caught Fox: the numerator
        # was right, the arithmetic was right, and the answer was
        # 8,790,139,900%.
        if rec.shares and rec.outstanding and rec.outstanding < rec.shares:
            flag(PROBLEM, f"shares outstanding ({rec.outstanding:,.0f}) is less "
                          f"than the holding ({rec.shares:,.0f}); the "
                          f"denominator is wrong")
        moved, how = jumped(out.history)
        if moved:
            # A rise is an issuance or conversion, a fall is buybacks --
            # and either can also be a tag read wrongly.
            flag(CAUTION, f"denominator moved {how}")
        if out.classes > 1:
            # Correct behaviour for a dual-class filer, not a defect.
            flag(NOTE, f"denominator sums {out.classes} share classes")
    else:
        flag(PROBLEM, out.note or "no cover-page share count")

    # A ledger is always internally consistent, including when it has missed
    # a line -- so these ask whether it is complete, not whether it adds up.
    if not led.settled:
        flag(PROBLEM, "walk did not settle; the total is a floor")
    if led.note:
        # Zuckerberg genuinely holds nothing directly, so this is a
        # pointer worth following, not proof of a defect.
        flag(CAUTION, led.note)
    if led.blind:
        # Could hold anything; the code cannot know it is nothing.
        flag(PROBLEM, f"{len(led.blind)} line(s) only ever footnoted, so "
                      f"missing from the total")
    if rec.converted:
        # 1:1 for Meta's Class B; 1:1500 for Berkshire's Class A. Summing
        # without checking is wrong by that factor.
        flag(CAUTION, f"convertible class counted ({rec.converted}); "
                      "confirm the ratio is 1:1")
    # THE SAME SHAPE, LESS EXTREMELY. A CEO with a little common stock and a
    # great deal in Table II is the same structure, and the percentage is
    # just as misleading without the caveat.
    if rec.shares and rec.options and rec.options > rec.shares * 3:
        what = "; ".join(t for t, _ in sorted(led.option_titles.items(),
                                              key=lambda kv: -kv[1])[:2])
        flag(CAUTION, f"{rec.options:,.0f} of {what or 'units or options'} "
                      f"against {rec.shares:,.0f} shares; most of this "
                      f"interest is not counted")

    # Worth saying out loud, because it is the finding the product exists
    # for and a reader should not have to derive it from two columns.
    if rec.shares and not rec.flows_reconcile:
        # THE CAUTION SAYS WHAT IT KNOWS AND STOPS (2026-09-15). It used to
        # blame a split by default; Castle Biosciences has never split and
        # carried that sentence, and Carvana's split was the stake being
        # wrong, not the flows. A residual means the flow columns do not
        # reconcile to the holding and must not be summed; why is for the
        # record to show, not for this line to guess.
        flag(CAUTION, f"the flows leave {rec.flow_residual:,.0f} unexplained "
                      f"against a holding of {rec.shares:,.0f}: the flow columns "
                      f"do not reconcile to the holding and must not be summed "
                      f"for this row")
    if rec.founded_share is not None and rec.founded_share >= 25:
        flag(NOTE, f"{rec.founded_share:.0f}% of their stake was already held "
                   f"when they became an insider")
    if rec.bought_share is not None and rec.acquired_total > 0:
        if rec.bought_share >= 50:
            flag(NOTE, f"bought {rec.bought_share:.0f}% of everything they have "
                       f"ever acquired")
        elif rec.bought == 0:
            flag(NOTE, "has never bought a share on the open market")

    # A gap is mostly benign: transactions must be filed within two business
    # days, so an old numerator means no transactions rather than stale data.
    # The denominator is quarterly, so a few months is normal. Past a year,
    # enough shares can have been issued to move the ratio.
    if rec.gap_days is not None and rec.gap_days > 365:
        flag(CAUTION, f"numerator and denominator {rec.gap_days} days apart")
    elif rec.gap_days is not None and rec.gap_days > 150:
        flag(NOTE, f"numerator and denominator {rec.gap_days} days apart")

    worst = {lvl for lvl, _ in rec.graded}
    rec.confidence = ("none" if rec.pct is None else
                      "low" if PROBLEM in worst else
                      "medium" if CAUTION in worst else "high")
    return rec
