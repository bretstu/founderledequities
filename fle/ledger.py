"""What a chief executive holds, from their newest filing.

THE CLASS IS THE REPORTING UNIT, AND THE COMPANY DEFINES IT.

The SEC's General Instructions say a Form 4 must "report total beneficial
ownership following the reported transaction(s) for each class of securities
IN WHICH A TRANSACTION WAS REPORTED", on "a separate line for each class of
securities beneficially owned directly or indirectly."

So the unit is (class x direct-or-indirect), and a filing covers only the
classes that moved -- which is why an untouched holding is legitimately
absent and has to be carried from an earlier filing.

We were taking securityTitle AS the class. It is free text, and filers put
other things in it: "Common Sotck" at Live Nation, four spellings of the par
value at Brown & Brown, "Class A Common Stock-Trust" and "IRA" at Amphenol,
plan names at Pentair. Each became a group nothing would ever update, and
Amphenol was overstated by 2,257,657.

WHEN A COMPANY HAS ONE CLASS, EVERY TITLE IS THAT CLASS. Not a guess -- there
is nothing else the shares could be. Ninety per cent of the index has one
class, and that covers 70 of the 79 companies holding more groups than their
class count allows.

WHEN IT HAS SEVERAL, THE COMPANY NAMES THEM AND THE TITLE IS MATCHED TO ONE.
The cover page tags its count once per class against a member -- Ford's are
`CommonStockMember` and `CommonClassBMember` -- so the classes are the
company's own list, not ours.

A title is matched to that list by its class LETTER, taken as a standalone
single-letter token: "Class B Common Stock" gives B, "Common Stock" gives
none and belongs to the member with no letter. Reading a lone token rather
than the word "Class" also catches Meta's "Clas A Common Stock", one row in
9,284 and exactly the 184,659 Meta was off by.

Across the 48 multi-class companies this matches 89 of the 97 titles that
are ever counted. The rest are excluded and flagged: a class the cover page
does not name is not in the denominator, and putting shares on top that are
missing from the bottom is the error v1 made with options.

ONE RULE:

    key on (security, direct-or-indirect)
    take the NEWEST filing that reports that group
    sum its rows

That is the whole calculation. Checked against every company we have an
independent figure for:

    Musk / Tesla         1,123,324,786   direct from 16 June, trust from 17th
    Armstrong / Coinbase    25,640,144   both Class B trusts in one filing
    Zuckerberg / Meta      342,463,325   eight Class B vehicles in one filing
    Dorsey / Block          48,844,566   five vehicles, all "See Footnote"
    Rapino / Live Nation     4,188,167   one row, and it is the answer

WHAT THIS REPLACES, AND WHY IT IS GONE.

The previous design carried each holding VEHICLE across filings, which meant
identifying vehicles -- and Form 4 gives them no identifier, only free text.
Everything built on top of that was scaffolding for a problem that does not
need solving:

  vehicle identity        Form 4 has none; natureOfOwnership is prose
  footnote keying         ids drift between filings, text can be reworded;
                          both were tried, both gave Block a wrong answer
  the closed-line rule    guessed when a silent vehicle had gone; it dropped
                          420 million of Zuckerberg's correctly and 1.5
                          million of Rapino's wrongly, and nothing in the
                          filings said which
  silence counting        an attempt to make that guess safer
  duplicate detection     needed only because vehicles were being split
  the Form 3 inventory    a complete list of lines, needed only to carry them

None of it survives. A filing states a complete position for each group it
reports, so nothing has to be carried and nothing has to be identified.

WHAT IT ASSUMES, AND WHERE THAT COULD FAIL.

That a filing reporting a group reports ALL of it. True for every company
checked. It would fail for a filer who lists only the vehicle that
transacted while holding several in the same group -- and then the answer is
too low, visibly, rather than wrong in an unknown direction.

Direct and indirect stay apart because Musk's two lines are the same security
and only that structured field separates them.
"""
import copy
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .flows import Flows
from .names import names_match, is_plain_ceo_title, token_overlap

SECTION16 = ("3", "4", "5", "3/A", "4/A", "5/A")

# The label for a company with one class. Not a title read from a
# filing -- a stand-in, so nothing downstream mistakes it for one.
SINGLE_CLASS = "Common Stock (the company's only class)"

# us-gaap:CommonClassAMember -> ("class", "A").  CommonStockMember -> ("", "").
# The KIND matters as well as the letter: "Series A" and "Class A" are
# different securities, and Dell holds both. Matching on the letter alone put
# Series A into Class A.
# THE DESIGNATOR IS THE LETTER AND ITS NUMBER. Symbotic has no Class V;
# it has V-1 and V-3, and matching on the bare letter collided them into
# one group -- "taken whole from the newest filing" then kept whichever
# line reported last (2.7M) while 401M of the founder's V-3 vanished.
CLASS_MEMBER = re.compile(r"(Class|Series)([A-Z][0-9]*)(?:Member)?", re.I)
KIND = re.compile(r"\b(class|series)\b", re.I)
# A standalone single letter in a security title is its class.
TOKEN = re.compile(r"[a-z0-9]+", re.I)


def class_letters(members) -> dict:
    """-> {(kind, letter): the label to key on}. ("", "") has no designator."""
    out = {}
    for m in members:
        g = CLASS_MEMBER.search(m.split(":")[-1])
        kind = g.group(1).lower() if g else ""
        letter = g.group(2).upper() if g else ""
        label_letter = (letter[0] + "-" + letter[1:]) if len(letter) > 1 else letter
        out[(kind, letter)] = (f"{kind.title()} {label_letter} Common Stock"
                               if letter else "Common Stock")
    return out


_GLUED = re.compile(r"\b(class|series)([A-Z])\b", re.I)


def unglue(title: str) -> str:
    """"ClassA Common" -> "Class A Common" (2026-09-17, Boston Beer): a 2004
    filing glued the designator to its letter, and the title read as no
    class at all. The history kept it as its own line for twenty years
    (684,656 shares never restated under that spelling); the ledger did not
    count it. Read as the letter it names, it is the Class A line, and the
    2023 statement replaces it in both walks."""
    return _GLUED.sub(lambda m: f"{m.group(1)} {m.group(2)}", title or "")


def title_letter(title: str) -> tuple | None:
    """-> (kind, letter) the title names, ("", "") for none, None if unclear.

    The letter is a lone token rather than the word after "Class", which is
    why "Clas A Common Stock" still reads as A.
    """
    title = unglue(title)
    # "V-1" / "V1" is one designator, not a letter near a stray digit
    numbered = re.findall(r"\b([A-Z])[-\u2011]?([0-9])\b", title or "")
    if len(numbered) == 1:
        k = KIND.search(title or "")
        return (k.group(1).lower() if k else "class",
                numbered[0][0].upper() + numbered[0][1])
    if len(numbered) > 1:
        return None
    singles = [t for t in TOKEN.findall(title or "")
               if len(t) == 1 and t.isalpha()]
    if len(singles) > 1:
        return None
    if not singles:
        return ("", "")
    k = KIND.search(title or "")
    # A misspelt designator ("Clas A") leaves the kind unknown; "class" is the
    # only one that ever appears without a letter beside it, so assume it.
    return (k.group(1).lower() if k else "class", singles[0].upper())


def dominant_letter(client, cik: int, docs: list) -> tuple | None:
    """The class letter this person's own Table I share rows use most, across
    every filing in `docs`; ties go to the newest filing's letter. None when
    the filings never name a letter. Read once, before the walk, so the
    ledger and the history assign every title the same way."""
    counts: dict = {}
    first: dict = {}
    for i, f in enumerate(sorted(docs, key=lambda f: f.get("filingDate") or "", reverse=True)):
        root = _parse(client, cik, f)
        if root is None:
            continue
        for tag in ("nonDerivativeTransaction", "nonDerivativeHolding"):
            for node in root.iter(tag):
                t = _t(node, "securityTitle")
                if not t or not is_share_class(t):
                    continue
                got = title_letter(t)
                if got is not None and got[1]:
                    counts[got] = counts.get(got, 0) + 1
                    first.setdefault(got, i)
    if not counts:
        return None
    return max(counts, key=lambda g: (counts[g], -first[g]))


def letters_seen(client, cik: int, docs: list) -> set:
    """Every class letter this person's Table I share rows have ever named,
    across `docs`. More than one under a one-class cover is the shape the
    retirement rule exists for (a class the company since retired), and the
    only case in which the cover pages are read for it."""
    out = set()
    for f in docs:
        root = _parse(client, cik, f)
        if root is None:
            continue
        for tag in ("nonDerivativeTransaction", "nonDerivativeHolding", "derivativeTransaction", "derivativeHolding"):
            for node in root.iter(tag):
                t = _t(node, "securityTitle")
                if t and is_share_class(t):
                    got = title_letter(t)
                    if got is not None and got[1]:
                        out.add(got)
    return out


def single_class_letter(letters: dict, dominant: tuple | None):
    """THE COMPANY'S ONE CLASS, DECIDED ONCE (2026-09-16, Bloom): the cover's
    lettered class when it names one, else the letter the person's own rows
    use most. Decided before the walk and never revised, because the letter
    rule compares every title to it; the first version read it from the
    live class map, which the discovered-class branch grows as it goes, so
    after a Class B was discovered a Class A row was judged "another letter"
    and keyed apart from the single class it belongs to, and a later Class B
    row folded into the single class. Rows of one class keyed two ways."""
    return next((g for g in (letters or {}) if g[1]), None) or dominant


def names_another_letter(title: str, the_class: tuple | None) -> bool:
    """WITH ONE CLASS, EVERY TITLE IS IT -- UNLESS THE TITLE SAYS OTHERWISE
    (2026-09-15, MoonLake). The cover page of an Up-C names one class, the
    Class A shares the market holds; the founder's exchange filing carries
    a Class A row (196,316 acquired, 3,074,893 after) and a Class C row (the
    paired voting shares surrendered, 0 after). Both rows were assigned to
    the one class, the later row won, and the walk published 0 shares for
    a 3.9% holder for three months.

    A title that names a class letter other than THE class (single_class_letter)
    is another class, discovered as it is when the cover names several. A
    title with no letter ("Common Stock") is always the single class, so
    the spelling difference between a cover that says "Class A" and a
    filing that says "Common Stock" never splits a holding."""
    if not is_share_class(title):
        return False
    got = title_letter(title)
    if got is None or not got[1]:
        return False
    return the_class is not None and got != the_class


def match_class(title: str, letters: dict) -> str | None:
    """The company's own label for the class this title names, or None."""
    if not letters:
        return title
    got = title_letter(title)
    return letters.get(got) if got is not None else None

# Tested in this order: both of these name a share class and neither is one.
NOT_A_SHARE = re.compile(
    r"option|warrant|right to (buy|purchase)|restricted stock unit|\bRSUs?\b|"
    r"\bunits?\b|phantom|appreciation|deferred|performance share|preferred",
    re.I)
IS_A_SHARE = re.compile(r"common stock|ordinary shares|class [a-z]\b", re.I)


# EQUITY IN THE PARTNERSHIP UNDERNEATH, not pay. An up-C or UPREIT puts a
# public shell on top of an operating partnership and leaves the founders
# holding UNITS in the partnership, exchangeable one for one into the public
# stock. Blackstone's "Blackstone Holdings Partnership units", Ares'
# "Operating Group units", and the REIT family -- "OP Units", "LTIP Units",
# "Long-Term Incentive Units" at Boston Properties, Prologis, Simon, Digital
# Realty and Kimco.
#
# Those are already issued and already the person's; a restricted stock unit
# is a promise that can be forfeited. Both sit in Table II, so a total cannot
# tell them apart -- and that difference decides whether excluding it is
# obviously right or merely arguable.
#
# Compensation is tested FIRST, because "Performance Share Units" and
# "Long-Term Incentive Units" both end in the same word.
# REQUIRE A PARTNERSHIP MARKER, do not merely exclude pay. Matching any
# word "unit" and subtracting compensation caught "Restricted Units" at
# Honeywell, Hartford and UPS, "Dividend Equivalent Unit" at Synchrony,
# "Growth Units" at Palantir and "SEP Unit" at Huntington Ingalls -- eleven
# false positives out of twenty-seven, because the exclusion list can only
# ever name the pay shapes somebody has already seen.
#
# Naming what a partnership interest IS fails in the safe direction instead:
# an unrecognised one is missed and flagged as ordinary, rather than an RSU
# being labelled ownership.
PARTNERSHIP_MARKER = re.compile(
    r"operating (partnership|group)"          # Ares Operating Group units
    r"|\bOP units?\b"                          # Simon
    r"|\bLTIP\b"                               # the REITs
    r"|long[- ]term incentive units?\b"        # the same, spelled out
    r"|holdings\s+(partnership\s+)?units?\b"   # Blackstone, KKR Holdings
    r"|\bcommon units?\b"                      # TKO
    r"|\bclass\s+[A-Z]\s+units?\b"             # Carvana
    r"|\bLP\s+units?\b"
    r"|\bgroup\s+units?\b"                     # Hagerty Group Units (2026-09-24)
    r"|\bLLC\s+units?\b"                       # "LLC Units", the plainest Up-C title
    r"|\bmembership\s+(interests?|units?)\b"   # an LLC's own word for its units
    r"|\bpartnership\s+units?\b",             # spelled out
    re.I)


# A STOCK UNIT IS A UNIT OF STOCK, never of a partnership -- and that holds
# whatever else the title says. Paccar grants "Stock Units (LTIP)", which the
# LTIP token caught; Vivmark, a REIT, holds "LTIP Units", which is a genuine
# operating-partnership interest.
#
# Identical vocabulary, opposite meanings, separated only by which word is
# the noun. Not another exclusion list: one structural observation that
# happens also to cover "Restricted Stock Units", "Performance Stock Units"
# and "Other Stock Units".
STOCK_UNIT = re.compile(r"\bstock\s+units?\b", re.I)


def is_partnership_unit(title: str) -> bool:
    """Is this equity in an operating partnership rather than compensation?"""
    t = title or ""
    if STOCK_UNIT.search(t):
        return False
    return bool(PARTNERSHIP_MARKER.search(t))











def is_share_class(title: str) -> bool:
    """Is this Table II row a convertible share class, or an option?"""
    t = unglue(title or "")
    return bool(IS_A_SHARE.search(t)) and not NOT_A_SHARE.search(t)


_LEADING_BY = re.compile(r"^\s*by\s+", re.I)
# A footnote reference some filing agents write into the nature text itself:
# "The Ehrsam 2014 Irrevocable Trust(9)". REMOVED from the key, never keyed
# on -- the id is a pointer to prose, and it changes between filings while
# the vehicle does not. Only a bracketed marker is stripped, so that names
# a filer numbers on purpose -- "GRAT No. 3" -- keep their number.
_FOOTNOTE_MARK = re.compile(r"\s*[\(\[]\s*\d{1,3}\s*[\)\]]\s*$")


def vehicle_key(direct: str | None, nature: str | None) -> tuple:
    """How a vehicle is recognised as the same vehicle in another document.

    NOT a similarity test. The name is canonicalised -- case folded, a
    leading "By" dropped, punctuation and spacing removed -- and then
    matched EXACTLY. It closes the gap between a filer writing "By Chan
    Zuckerberg Holdings LLC" one week and "By Chan Zuckerberg Holdings,
    LLC" the next, which added a phantom 34,344,500 shares to Meta for two
    months; and between "By The Ehrsam 2014 Irrevocable Trust" and "The
    Ehrsam 2014 Irrevocable Trust", which did the same to Coinbase four
    times over.

    It stays deliberately blunt, so that entities a filer distinguishes are
    still distinguished: "CZI Holdings, LLC" and "CZI Holdings I, LLC"
    remain two vehicles, as do "Chan Zuckerberg Holdings, LLC" and "Chan
    Zuckerberg Holdings II, LLC". Balances play no part -- two trusts that
    merely happen to hold the same number of shares are never joined by
    this, only by the arithmetic of a running balance.
    """
    text = (nature or "").strip()
    while True:
        stripped = _FOOTNOTE_MARK.sub("", text)
        if stripped == text:
            break
        text = stripped
    text = _LEADING_BY.sub("", text)
    return (direct, re.sub(r"[^a-z0-9]+", "", text.lower()))


# A NATURE TEXT THAT NAMES NOTHING. "See footnote", "See note 3", "Per
# footnotes", "(2)", or nothing at all on an INDIRECT line: a pointer to
# prose, not a name. Only for these does the running balance decide which
# rows belong together. A NAMED vehicle keeps the text rule, because one
# named vehicle whose balances do not chain (Musk's SpaceX catch-up Form 4
# drops 25M between rows it never explains) is still one vehicle, and the
# arithmetic alone cannot tell that from two anonymous ones.
#
# THE DIRECT LINE IS A NAME. It has no nature text by construction and
# there is exactly one of it, so "D" with no text is not anonymous. Its
# running balances routinely miss by a share or two (Pope's 281,359 then
# 281,360; Westhoven's 259,070 then 259,069: fractional withholding and
# ESPP rounded row by row), and the first version of this rule, which read
# the empty text as a pointer, started a phantom vehicle at every rounding
# gap -- Portland General's chief executive at 1% of the company. Direct
# rows keep the text rule, always.
#
# Misclassifying a pointer as a name falls back to the old behaviour; the
# reverse cannot happen, since a name does not begin with "see".
# The spellings filers actually use: "See footnote", "See Footnotes", "Se
# footnote" (Prince's, one filing), "SEE FTN" and then "FN" (Krimbill's,
# two months apart), "Per footnote 3", "(2)", nothing. A text whose first
# word is see/se/per/refer, or that is nothing but a footnote token, names
# nothing. Missing a spelling here makes a NAMED vehicle of a pointer, and a
# named vehicle standing beside its anonymous twin counts twice.
_ANONYMOUS = re.compile(
    r"^\W*(see|se|per|refer)\b"
    r"|^\W*(f\.?n\.?|ftn\.?|ftnt\.?|footnotes?|foot\s*notes?|notes?)(\W*\d+)?\W*$"
    r"|^\W*\d*\W*$", re.I)


def is_anonymous(nature: str | None, direct: str | None = "I") -> bool:
    if (direct or "D").upper()[:1] == "D":
        return False
    return bool(_ANONYMOUS.match(nature or ""))


def base_of(key: tuple) -> tuple:
    """The text a segment key was made from: ('I', 'seefootnote#3') -> ('I', 'seefootnote')."""
    return (key[0], key[1].split("#", 1)[0])


def apply_exclusions(here: dict, exclude, record: dict | None = None) -> None:
    """Remove from `here` (group key -> Group) what the register says is not
    the person's: a whole class-and-direction (a row with no vehicle), or one
    vehicle of it (a row naming the line). `record`, when given, gets
    label -> (shares removed, reason, source) for the page.

    An anonymous vehicle ("See footnote") is matched by its base text only
    when the group has exactly one such line, since the register cannot say
    which of several pointers it means; otherwise the row is left to a hand
    decision and nothing is removed."""
    rows = [e for e in exclude if not getattr(e, "is_addition", False)]
    if not rows:
        return
    for key in list(here):
        g = here[key]
        whole = next((e for e in rows if not getattr(e, "vehicle", "") and e.matches(g.security, g.direct)), None)
        if whole:
            if record is not None:
                record.setdefault(g.label(), (g.shares, whole.reason, whole.source))
            del here[key]
            continue
        for e in rows:
            if not getattr(e, "vehicle", "") or not e.same_class(g.security):
                continue      # a vehicle row: the class and the text; the direction is not consulted
            want = vehicle_key(g.direct, e.vehicle)[1]
            hits = [v for v in g.vehicles() if v[1].split("#", 1)[0] == want]
            if not hits:
                continue
            if is_anonymous(e.vehicle, g.direct) and len(hits) > 1:
                continue      # which pointer? the register cannot say; a person can
            before = g.shares
            for v in hits:
                g.last_txn.pop(v, None)
                if v in g.hold_by_vehicle:
                    g.holdings -= g.hold_by_vehicle.pop(v) or 0.0
                g.passed.pop(v, None)
                g.opening.pop(v, None)
            g.shares = sum(g.last_txn.values()) + g.holdings
            removed = before - g.shares      # what actually left the position, counted once
            if record is not None and removed:
                # one vehicle, one entry, whichever column the filer used for it on a given filing (AAOI, Vornado)
                record.setdefault(f"{g.security} · {e.vehicle}", (removed, e.reason, e.source))
        if not g.vehicles() and g.shares <= 0.5:
            del here[key]


def vehicle_keys(rows: list, ends: dict | None = None) -> list:
    """One key per row of ONE document: the nature text, and where several
    anonymous vehicles share it, the running balance tells them apart.

    A Form 4 gives a vehicle no identifier, only the nature text, and some
    lawyers write "See footnote" on every line. Keyed on the text alone,
    four of Lacerte's trusts became one vehicle and only the last balance
    survived: his 4 September 2026 filing sold 257,243 across five lines,
    every running balance closing where the filing says, and the walk
    settled 2,310,751 against the filing's 2,535,853. Dorsey and Foroughi
    file the same way.

    The document already says which rows belong together, in numbers. A
    transaction row's balance before it is its balance after less what it
    moved. A row that opens where a segment closed is that vehicle
    continuing (Makahakama: 99,593 -> 87,828, then a row opening at
    87,828 -> 60,854); a row that CLOSES where a segment opened precedes it
    (the same trust listed in the wrong order); a row that does neither
    (205,000, after a close of 60,854) is another vehicle and gets its own
    key. A row whose text differs but chains joins that segment: the "See
    foornote" typo continues "See footnote".

    HOLDING LINES ARE KEPT APART TOO. Summed under one key they were right
    as a total and useless as a list: when the next filing was one
    anonymous trust buying 42,248 (before 142,001, after 184,249), the walk
    had a pile, not a list, could not find the 142,001 in it, and dropped
    every other trust. Each anonymous holding line is its own segment, so
    a later document can match a transaction to the holding it continues
    by arithmetic. A holding line that restates a transaction segment of
    this same document (same balance) joins it rather than adding; two
    holding lines at the same balance stay apart (Lacerte's two 135,000
    family trusts), because a holding is not evidence of a move.

    Named vehicles and the direct line keep the text rule (see _ANONYMOUS
    for why). Footnoted balances (NaN) keep the plain key too. Footnote ids
    are deliberately not used: two lines can share one, and the numbers
    already decide.

    `ends`, if given, is filled with each anonymous segment's closing
    balance: where its chain ends, which is not the last row listed when
    the filer listed the days out of order.
    """
    keys = []
    segs: dict = {}            # key -> {"open", "close", "sec", "direct", "txn"}
    count: dict = {}           # base key -> segments opened
    tol = 1.0

    def fresh(base):
        n = count.get(base, 0) + 1
        count[base] = n
        return base if n == 1 else (base[0], f"{base[1]}#{n}")

    for r in rows:
        base = vehicle_key(r.direct, r.nature)
        if r.shares != r.shares or not is_anonymous(r.nature, r.direct):
            keys.append(base)
            continue
        sec = r.security.strip().lower()
        mine = [k for k, sg in segs.items() if sg["sec"] == sec and sg["direct"] == r.direct]
        if r.code:
            signed = (r.moved if r.acquired else -r.moved) or 0.0
            opening = r.shares - signed
            hit = None
            if not signed:
                # no amount stated: nothing to test; the text's newest
                # segment, which is what the text-only rule always did
                same = [k for k in mine if base_of(k) == base]
                hit = same[-1] if same else None
            else:
                hit = next((k for k in mine if abs(segs[k]["close"] - opening) <= tol), None)
                if hit is None:
                    # this row PRECEDES a segment: it closes where one opened
                    hit = next((k for k in mine if abs(segs[k]["open"] - r.shares) <= tol
                                and segs[k]["txn"]), None)
                    if hit is not None:
                        segs[hit]["open"] = opening
                        segs[hit]["txn"] = True
                        keys.append(hit)
                        if ends is not None:
                            ends[hit] = segs[hit]["close"]
                        continue
            # NOT JOINED BY A SHARED CLOSE. Harrison writes the day's final
            # balance on every row (four rows on 11 January 2022, all closing
            # at 390,620, openings chaining to nothing: one trust), and a
            # rule that read an unchained row closing where another segment
            # closed as that position restated fixed him. It also merged two
            # of Sharma's trusts, two of Foroughi's and two of Vashist's,
            # each of which moved once and happened to end at the same
            # balance; the arithmetic cannot tell the two shapes apart, and
            # three filers lost for one gained. Harrison's rows stay four
            # vehicles, and his residue says so.
            if hit is None:
                hit = fresh(base)
                segs[hit] = {"open": opening, "close": r.shares, "sec": sec, "direct": r.direct, "txn": True}
            else:
                segs[hit]["close"] = r.shares
                segs[hit]["txn"] = True
            keys.append(hit)
            if ends is not None:
                ends[hit] = segs[hit]["close"]
        else:
            # a holding: restates a transaction segment closing at this
            # balance (once), else its own segment
            hit = next((k for k in mine if segs[k]["txn"] and not segs[k].get("restated")
                        and abs(segs[k]["close"] - r.shares) <= tol), None)
            if hit is not None:
                segs[hit]["restated"] = True
            else:
                hit = fresh(base)
                segs[hit] = {"open": r.shares, "close": r.shares, "sec": sec, "direct": r.direct, "txn": False}
            keys.append(hit)
    return keys


# (Deleted: one regex for stripping footnote markers
# from vehicle names. They were the last remnants of v1's attempt to
# identify vehicles ACROSS filings, were never called by this design, and
# left the false impression that footnotes key something. They do not.)











def _t(node, tag: str) -> str | None:
    """Form 4 wraps most values in <value>; a few are bare."""
    if node is None:
        return None
    el = node.find(tag)
    if el is None:
        for el in node.iter(tag):
            break
        else:
            return None
    v = el.find("value")
    text = (v.text if v is not None else el.text) or ""
    # COLLAPSE INTERNAL WHITESPACE. Filers wrap long values across lines, and
    # the newline survives into the CSV: "Non-qualified\nStock Option (Right
    # to Buy)" renders as a three-line cell in a spreadsheet, and
    # "By Chan Zuckerberg\nInitiative, LLC" did the same to a holder name.
    # A line break inside a title is typesetting, never meaning.
    return " ".join(text.split()) or None


def _num(node, tag: str) -> float | None:
    raw = _t(node, tag)
    if raw is None:
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


@dataclass
class Line:
    security: str
    direct: str                      # "D" or "I"
    nature: str | None
    notes: str = ""
    code: str = ""                   # the transaction code, when there is one
    moved: float = 0.0               # shares this transaction moved
    price: float | None = None       # transactionPricePerShare, when reported
    acquired: bool = True            # was this an acquisition or a disposal
    shares: float = 0.0
    as_of: str = ""
    accession: str = ""
    form: str = ""
    table: str = "I"


    def label(self) -> str:
        where = "direct" if self.direct == "D" else (self.nature or "indirect")
        return f"{self.security} · {where}"



def displace_amended(filings: list) -> list:
    """A Form 4/A is not a second filing; it is the filing, again.

    The amendment restates the entire report -- Musk's 5/A for 2022 carries
    all seven gifts and the full running balance -- so counting the original
    beside it counts the period twice. His gifts came out at 24,141,440
    against a real 12,570,841: the original's 11,570,599 plus the
    amendment's complete restatement.

    One deliberate limit: when a period holds SEVERAL originals of the same
    form -- Musk filed two Forms 4 for 21 December 2021 -- an amendment
    cannot say which one it corrects (the form names only the original's
    DATE, which both share). Displacing both would destroy a filing that was
    never amended, so the ambiguous case keeps everything and lets the
    period's chain sort the balances; only the traded total is left
    imperfect, and the reconciliation column says so.
    """
    period = lambda f: (f.get("reportDate") or f.get("filingDate") or "")
    newest_amendment: dict = {}
    original_count: dict = {}
    for f in filings:
        form = (f.get("form") or "").upper()
        k = (form[:-2] if form.endswith("/A") else form, period(f))
        if form.endswith("/A"):
            cur = newest_amendment.get(k)
            if cur is None or ((f.get("filingDate") or "", f.get("accessionNumber") or "")
                               > (cur.get("filingDate") or "", cur.get("accessionNumber") or "")):
                newest_amendment[k] = f
        else:
            original_count[k] = original_count.get(k, 0) + 1

    out = []
    for f in filings:
        form = (f.get("form") or "").upper()
        if form.endswith("/A"):
            k = (form[:-2], period(f))
            if newest_amendment.get(k) is not f:
                continue                 # superseded by a newer amendment
        else:
            k = (form, period(f))
            if k in newest_amendment and original_count.get(k, 0) == 1:
                continue                 # displaced by its amendment
        out.append(f)
    return out


def _doc_url(cik: int, acc: str, primary: str) -> str:
    """The ownership XML, named by the submissions feed.

    v1 asked EDGAR for each filing's index to find this -- a second request
    per filing for information already in hand. EDGAR sometimes points at the
    stylesheet-rendered copy under xslF345X../; stripping the prefix gives the
    raw XML.
    """
    name = (primary or "").split("/")[-1]
    return (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{acc.replace('-', '')}/{name}")


class _Unread(Exception):
    """A filing that could not be FETCHED, as opposed to one that was read
    and did not parse. The chooser counts these: a search that could not
    read its filings must not conclude that the person is absent."""


_DATE = re.compile(r"<transactionDate>\s*<value>\s*(\d{4}-\d{2}-\d{2})")


def period_end(client, cik: int, f: dict, memo: dict | None = None) -> str:
    """The moment a filing SPEAKS FOR: the newest transaction it reports, or
    its period of report when it reports none.

    THE FEED'S reportDate IS A FORM 4's EARLIEST TRANSACTION. Ordering by
    it put SpaceX's catch-up Form 4 -- filed 17 June 2026, reporting
    2 February through 15 June, the IPO-day conversions of six series of
    preferred among them -- BEFORE the Form 3 of 11 June, so the Form 3's
    pre-conversion balances were taken as the newest word and 316 million
    shares that converted on 15 June never counted. The walk stood at
    33.76% on a stake that was 36.2%. Any catch-up Form 4 spanning the
    Form 3 date sorts wrong under that key; sorting by the LATEST
    transaction in the document puts each filing at the moment it
    describes.

    Read with a regex over the raw document rather than a parse -- the
    documents are on disk, the walk parses them once later, and this must
    stay cheap enough to run over every filing a person has. Capped at the
    filing date: a filing cannot report a trade after it was filed.

    `memo` is one walk's own dictionary, so a filing is read once per walk
    and nothing outlives it."""
    acc = f.get("accessionNumber") or ""
    base = f.get("reportDate") or f.get("filingDate") or ""
    if memo is not None and acc in memo:
        return memo[acc]
    if f.get("_parts"):
        end = max(period_end(client, cik, p, memo) for p in f["_parts"])
        if memo is not None:
            memo[acc] = end
        return end
    filed = f.get("filingDate") or "9999-12-31"
    end = base
    try:
        raw = client.get(_doc_url(cik, acc, f.get("primaryDocument", "")))
        for d in _DATE.findall(raw):
            if d <= filed and d > end:
                end = d
    except Exception:  # noqa: BLE001 -- unreadable: the feed's date stands
        pass
    if memo is not None:
        memo[acc] = end
    return end


# A FORM 4 HOLDS 30 ROWS PER TABLE. Foroughi's 20 to 22 August 2025 sale
# ran to seven documents, each non-derivative table exactly 30 rows, filed
# on one day under consecutive accession numbers, each continuing where
# the previous stopped to the share (HDF 2020 LLC ends one at 8,329 and
# opens the next at 8,329). One filing, in parts. The cap is why parts
# exist; it is not the test for them (see _continues): Zuckerberg's lawyers
# split a day's filing by vehicle, and those parts are not full.
ROWS_PER_TABLE = 30


def _continues(prev_root, next_root) -> bool:
    """Whether `next_root` picks up where `prev_root` stopped.

    A continuation opens where the previous part closed: Foroughi's HDF
    2020 LLC at 8,329 then 8,329. A RESTATEMENT re-opens at the original
    openings (Zuckerberg's paired filings, full tables under consecutive
    numbers on one day) and fails; concatenated, it counted every trade
    and holding twice, 825M of residue on a record that had 667K.

    Named vehicles are paired by key and every shared key must chain.
    Anonymous ones cannot be paired by key across two documents, so they
    are paired by balance: some anonymous segment of the next part must
    open where some anonymous segment of the previous part closed, under
    the same security and direct. A next part that shares nothing with
    the previous is not joined: nothing proves it.

    WHAT WAS TRIED AND WITHDRAWN. Letting a holding prove a seam (the next
    part restating a vehicle at the previous part's close), testing seams
    against the batch merged so far, and letting a holding be a balance
    the next part opens at, each joined more of Zuckerberg's daily parts
    and each raised residue elsewhere (RNG, UMBF, a panel figure at IMAX)
    faster than it lowered it here. Parts split by vehicle rather than by
    the cap merge the way same-day filings always have.
    """
    def segs(root):
        rows = _rows(root, "4", "", "")
        ends: dict = {}
        keys = vehicle_keys(rows, ends)
        opens, closes, anon = {}, {}, set()
        for r, k in zip(rows, keys):
            if not r.code or r.shares != r.shares:
                continue
            sec = r.security.strip().lower()
            signed = (r.moved if r.acquired else -r.moved) or 0.0
            full = (sec, k)
            opens.setdefault(full, r.shares - signed)
            closes[full] = ends.get(k, r.shares)
            if is_anonymous(r.nature, r.direct):
                anon.add(full)
        return opens, closes, anon
    p_open, p_close, p_anon = segs(prev_root)
    n_open, n_close, n_anon = segs(next_root)
    shared = [k for k in n_open if k in p_close and k not in n_anon and k not in p_anon]
    if shared and not all(abs(n_open[k] - p_close[k]) <= 1.0 for k in shared):
        return False
    anon_next = [(k[0], k[1][0], v) for k, v in n_open.items() if k in n_anon]
    anon_prev = [(k[0], k[1][0], v) for k, v in p_close.items() if k in p_anon]
    anon_hit = any(abs(o - c) <= 1.0 for s1, d1, o in anon_next for s2, d2, c in anon_prev if s1 == s2 and d1 == d2)
    if anon_next and anon_prev and not anon_hit:
        return False
    return bool(shared or anon_hit)


def _table_rows(root) -> int:
    n = 0
    for table, tags in (("nonDerivativeTable", ("nonDerivativeTransaction", "nonDerivativeHolding")),
                        ("derivativeTable", ("derivativeTransaction", "derivativeHolding"))):
        t = root.find(table)
        if t is not None:
            n = max(n, sum(len(t.findall(tag)) for tag in tags))
    return n


def batch_continuations(client, cik: int, filings: list) -> list:
    """Fold a filing's continuation documents into one document.

    A Form 4 that hits the 30-row cap spills into the next document.
    Dated by its own newest transaction, each part landed in its own
    period: Foroughi's seven parts fell across 20, 21 and 22 August, and a
    trust that sat in one part was "silent" in the period of another,
    benched, and put back a day later, minus 5.3M then plus 5.2M on a
    record that had lost nothing. Musk's November 2021 days ran to five
    documents each, and the bench carries a special case for them.

    The signal is structural: an original Form 4 whose non-derivative or
    derivative table is full, followed on the same filing day by the same
    person's next accession number about the same company, whose rows
    provably continue it (_continues). The pair is one document; the rows
    read in accession order and the running balances chain across the
    seam. A document that is not full (a restatement, a filing split by
    vehicle rather than by the cap, an unrelated second filing) is left
    alone and merges the way same-day filings always have. The batch
    reports for the day its newest part speaks for. Idempotent.
    """
    def seq(acc):
        pre, _, num = (acc or "").rpartition("-")
        return pre, (int(num) if num.isdigit() else None)
    out, i = [], 0
    fs = sorted(filings, key=lambda f: (f.get("filingDate") or "", f.get("accessionNumber") or ""))
    while i < len(fs):
        f = fs[i]
        parts = [f]
        if f.get("form") == "4" and "_parts" not in f:
            root = _parse(client, cik, f)
            while root is not None and _table_rows(root) >= ROWS_PER_TABLE and i + 1 < len(fs):
                nxt = fs[i + 1]
                pre, n = seq(f.get("accessionNumber"))
                pre2, n2 = seq(nxt.get("accessionNumber"))
                if not (nxt.get("form") == "4" and "_parts" not in nxt and pre2 == pre
                        and n is not None and n2 == n + 1
                        and nxt.get("filingDate") == f.get("filingDate")):
                    break
                nxt_root = _parse(client, cik, nxt)
                if nxt_root is None or not _continues(root, nxt_root):
                    break
                parts.append(nxt)
                i += 1
                f = nxt
                root = nxt_root
        if len(parts) > 1:
            head = dict(parts[0])
            head["_parts"] = parts
            head["reportDate"] = max((p.get("reportDate") or "") for p in parts) or head.get("reportDate")
            out.append(head)
        else:
            out.append(parts[0])
        i += 1
    return out


def _parse(client, cik: int, f: dict, unread: list | None = None):
    """The document, or the parts of a batched filing merged into one
    (batch_continuations): the first part's root with every later part's
    table entries appended in accession order, so the rows read as filed."""
    parts = f.get("_parts")
    if parts:
        roots = [_parse(client, cik, p, unread) for p in parts]
        if any(r is None for r in roots):
            return None
        merged = copy.deepcopy(roots[0])

        def hold_key(n):
            t = lambda q: (n.findtext(q + "/value") or n.findtext(q) or "").strip()
            return (n.tag, t("securityTitle").lower(), t("ownershipNature/directOrIndirectOwnership"),
                    t("ownershipNature/natureOfOwnership").lower(), t("postTransactionAmounts/sharesOwnedFollowingTransaction"))
        seen: dict = {}
        for n in list(merged.iter("nonDerivativeHolding")) + list(merged.iter("derivativeHolding")):
            k = hold_key(n)
            seen[k] = seen.get(k, 0) + 1
        tables = {"nonDerivativeTransaction": "nonDerivativeTable", "nonDerivativeHolding": "nonDerivativeTable",
                  "derivativeTransaction": "derivativeTable", "derivativeHolding": "derivativeTable"}
        for r in roots[1:]:
            here: dict = {}
            # rows are read wherever they sit (as _rows reads them) and
            # appended under the matching table of the merged document
            for child in list(r.iter()):
                if child.tag not in tables:
                    continue
                if child.tag.endswith("Holding"):
                    # a holding a later part repeats from an earlier one is
                    # that holding restated, not a second one; two genuine
                    # trusts at one balance restated together are still two
                    # (counted per part)
                    k = hold_key(child)
                    here[k] = here.get(k, 0) + 1
                    if here[k] <= seen.get(k, 0):
                        continue
                dst = merged.find(tables[child.tag])
                if dst is None:
                    dst = ET.SubElement(merged, tables[child.tag])
                dst.append(copy.deepcopy(child))
            for k, c in here.items():
                seen[k] = max(seen.get(k, 0), c)
        return merged
    url = _doc_url(cik, f.get("accessionNumber", ""), f.get("primaryDocument", ""))
    try:
        raw = client.get(url)
    except Exception as exc:  # noqa: BLE001 -- fetch failed: throttle, outage
        if unread is not None:
            unread.append(f"{f.get('accessionNumber')}: {exc}")
        return None
    try:
        return ET.fromstring(raw)
    except Exception:  # noqa: BLE001 -- read fine, not XML: genuinely skip
        return None


def issuer_of(root) -> str:
    """The CIK a Form 4 is ABOUT, which is not always whose feed it is in.

    A company that is itself an insider elsewhere carries those filings in
    its own submissions feed. Blackstone Inc is an insider of the funds it
    controls, so CIK 1393818's Section 16 list contains Form 4s about BREIT
    and BXMT -- and their securities were counted as Blackstone's: "Common
    Shares of Beneficial Interest", "Institutional Class II Common Shares".

    117 Form 3s for one person at one company was the tell. Every filing
    states its issuer; we simply never read it.
    """
    for iss in root.iter("issuer"):
        cik = _t(iss, "issuerCik")
        if cik:
            return cik.lstrip("0")
    return ""


def _owners(root) -> list[tuple[str, str, str, bool]]:
    """-> (cik, name, title, is_officer) for each reporting owner.

    The officer flag is the only thing separating a chief executive from a
    vehicle named after him. "Brian Armstrong Living Trust" files in its own
    right, holds Coinbase stock, and scores a PERFECT 1.00 against "Brian
    Armstrong" because "Living Trust" reads as two more name tokens.

    A trust is a ten per cent owner. A chief executive is an officer. That
    distinction is a checkbox in the schema, not an inference from the name --
    which matters because the alternative, looking for words like "trust" or
    "LLC", would fail on the next vehicle named something else.
    """
    out = []
    for ro in root.iter("reportingOwner"):
        rel = ro.find("reportingOwnerRelationship")
        is_officer = False
        title = ""
        if rel is not None:
            title = _t(rel, "officerTitle") or ""
            # Either signal counts. Filers are inconsistent: a chief executive
            # who is also chairman is sometimes ticked director-only with the
            # title still filled in, and a missing tick would then hand the
            # match to a trust named after them. Both fields live in the same
            # element, and a trust has neither.
            is_officer = ((_t(rel, "isOfficer") or "").lower() in ("1", "true")
                          or bool(title.strip()))
        out.append(((_t(ro, "rptOwnerCik") or "").lstrip("0"),
                    _t(ro, "rptOwnerName") or "", title, is_officer))
    return out



def supplement_rows(root, rows: list, form: str, when: str, acc: str, entries) -> list:
    """SHARES THE FILER STATES IN A REMARK, AS ONE MORE TABLE LINE.

    Musk's SpaceX Forms 3 and 4 say, in their remarks, that 1,302,072,285
    restricted Class B shares held of record by him are not in the tables.
    A person recorded that figure in universe/exclusions.csv with the filing
    as source. Here, a filing by that owner whose remark still states the
    figure, and whose tables do not already report the class held directly,
    gets the line the filer left out: the class, direct, that many shares.
    Every downstream stage then treats it as it would a real line. No prose
    is read: the rule matches a recorded digit string."""
    adds = [e for e in (entries or ()) if getattr(e, "is_addition", False)]
    if not adds:
        return []
    from .exclusions import figure_stated
    owner = (root.findtext("reportingOwner/reportingOwnerId/rptOwnerCik") or "").strip().lstrip("0")
    remark = (root.findtext("remarks") or "")
    out = []
    for a in adds:
        if a.owner_cik and owner != a.owner_cik.lstrip("0"):
            continue
        if not figure_stated(remark, a.shares):
            continue
        title = (a.security or "").split("(")[0].strip()
        tl = title_letter(title)
        if any(r.direct == "D" and (title_letter(r.security) == tl if tl else
                                     r.security.strip().lower() == title.lower()) for r in rows):
            continue   # the tables report it now; they win
        out.append(Line(security=title, direct="D", nature=None,
                        notes=f"supplement: stated in the filing's remark, recorded from {a.source}",
                        shares=float(a.shares), as_of=when, accession=acc, form=form, table="I"))
    return out


def settlements_only_in_table_ii(root, rows: list, when: str, acc: str, form: str = "4") -> list[Line]:
    """A SETTLEMENT REPORTED ONLY IN TABLE II (2026-09-17, Vaxcyte). Some
    filers show an RSU vesting as the derivative disposed (code M, the
    underlying common stock and its share count named) and in Table I only
    the withholding; the balance carries the vested shares, so the holding
    is right, but the flows and the tape see "-6,289 withheld" on a day the
    holding rose 126,926. Where Table II disposes a derivative under M, C
    or X into a share class and Table I reports no acquisition under that
    code on that day, the underlying shares are the acquisition, as a line
    Table I should have carried. Where Table I does report it, nothing is
    added: the compliant filing is not double-counted."""
    out = []
    have = {(r.code, (r.as_of or when)[:10]) for r in rows if r.table == "I" and r.acquired and r.code in ("M", "C", "X")}
    for node in root.iter("derivativeTransaction"):
        code = (_t(node, "transactionCoding/transactionCode") or "").strip().upper()[:1]
        if code not in ("M", "C", "X"):
            continue
        if (_t(node, "transactionAmounts/transactionAcquiredDisposedCode") or "").strip().upper() != "D":
            continue
        under = _t(node, "underlyingSecurity/underlyingSecurityTitle") or ""
        if not is_share_class(under):
            continue
        try:
            n = float(_t(node, "underlyingSecurity/underlyingSecurityShares") or "")
        except ValueError:
            continue
        if not n or n != n:
            continue
        day = (_t(node, "transactionDate") or when)[:10]
        if (code, day) in have:
            continue
        direct = (_t(node, "ownershipNature/directOrIndirectOwnership") or "D").strip().upper()[:1] or "D"
        nature = _t(node, "ownershipNature/natureOfOwnership") or None
        out.append(Line(security=under.strip(), direct=direct, nature=nature, notes="settled in Table II only",
                        code=code, moved=n, price=None, acquired=True, shares=0.0,   # no balance of its own: the position is history's
                        as_of=day, accession=acc, form=form, table="I"))
    return out


# UNITS REPORTED AS COMMON STOCK (2026-09-29). Two filers of the same RSU
# grant write it two ways: most as a derivative in Table II, titled as
# units, where the title keeps it out of the stake until it vests; some as
# "Common Stock" in Table I on the grant date, with only the footnote saying
# the shares are units. The structured fields cannot tell that grant from a
# restricted stock award (both code A, both unpriced, both common by title),
# so the footnote is read, by pattern: unit language, and neither the words
# of a stock award nor of a settlement (shares received when units vested
# are shares). The count is recorded and said on the page; it changes no
# figure, because a vest from Table I files no row, and estimating the
# unvested remainder would be the one thing the site never does.
UNIT_WORDS = re.compile(r"restricted\s+stock\s+units?|\bRSUs?\b|performance\s+(?:stock|share)\s+units?|\bPSUs?\b|deferred\s+stock\s+units?|\bDSUs?\b", re.I)
AWARD_WORDS = re.compile(r"shares?\s+of\s+restricted\s+stock|restricted\s+shares?|restricted\s+stock\s+award", re.I)
SETTLE_WORDS = re.compile(r"upon\s+(?:the\s+)?(?:vesting|settlement)|received\s+upon|issued\s+upon|settle(?:d|ment)\s+of|converted\s+into|net\s+settle|in\s+settlement", re.I)


def units_as_common(notes: str) -> bool:
    """A Table I acquisition whose footnote calls the shares units, and
    neither a stock award nor the settlement of units already granted."""
    return bool(notes) and bool(UNIT_WORDS.search(notes)) and not AWARD_WORDS.search(notes) and not SETTLE_WORDS.search(notes)


def _footnotes(root) -> dict:
    return {x.get("id"): " ".join((x.text or "").split()) for x in root.findall("footnotes/footnote")}


def _rows(root, form: str, when: str, acc: str) -> list[Line]:
    """Table I in document order, then Table II's share classes."""
    out = []
    notes = _footnotes(root)
    for tag, table in (("nonDerivativeTransaction", "I"),
                       ("nonDerivativeHolding", "I"),
                       ("derivativeTransaction", "II"),
                       ("derivativeHolding", "II")):
        for node in root.iter(tag):
            title = _t(node, "securityTitle")
            if not title:
                continue
            if table == "II" and not is_share_class(title):
                continue
            own = node.find("ownershipNature")
            shares = _num(node.find("postTransactionAmounts"),
                          "sharesOwnedFollowingTransaction")
            if table == "II" and (form.startswith("3") or shares is None):
                # A FORM 3 STATES A TABLE II SHARE CLASS BY ITS UNDERLYING COUNT
                # (2026-09-21, Boost Run). The initial statement's schema has
                # no balance field on a Table II holding: the count is the
                # underlying security's, and a share class converts one for
                # one, so that count is the holding. Form 4s carry a balance
                # and it is read above; a filing of any type that omits it
                # is read the same way rather than as nothing.
                shares = _num(node.find("underlyingSecurity"), "underlyingSecurityShares") if shares is None else shares
            amounts = node.find("transactionAmounts")
            ad = (_t(amounts, "transactionAcquiredDisposedCode") or "A").upper()[:1]
            out.append(Line(
                title, (_t(own, "directOrIndirectOwnership") or "D").upper()[:1],
                _t(own, "natureOfOwnership"),
                " ".join(notes.get(y.get("id"), "") for y in node.iter("footnoteId")),   # the row's own footnotes, whole
                (_t(node.find("transactionCoding"), "transactionCode") or ""),
                _num(amounts, "transactionShares") or 0.0,
                # THE PRICE THE TRADE ACTUALLY EXECUTED AT, not a market
                # close. Form 4 reports it per row, so a sale is worth what
                # the filer says it was worth. It is ABSENT by design on
                # grants and gifts -- nothing changed hands -- and a zero is
                # therefore not a price but a statement that there was none.
                _num(amounts, "transactionPricePerShare") or None,
                ad == "A",
                shares if shares is not None else float("nan"),
                _t(node, "transactionDate") or when, acc, form, table))
    _trust_the_balances(out)
    return out


def _trust_the_balances(rows: list) -> None:
    """Where a filing's own running balance contradicts its A/D flag, the
    balance wins.

    Armstrong's 13 July 2023 form converts 2,143 Class A and marks the row
    acquired, but the balance goes 15,099 -> 12,956: the shares left. Taken
    at the flag's word the day traded 4,286 too many -- twice the row --
    and the reconciliation blamed the difference on nothing.

    Only an exact contradiction is corrected: the balance must move by the
    row's own amount, in the opposite direction. Anything less clear is
    left alone and shows up in the reconciliation column, which is what it
    is for.
    """
    last: dict = {}
    for r in rows:
        if r.shares != r.shares:            # a footnoted balance; no evidence
            continue
        key = (r.table, r.security.strip().lower(), r.direct,
               (r.nature or "").strip().lower())
        prev = last.get(key)
        last[key] = r.shares
        if not r.code or prev is None or not r.moved:
            continue
        change = r.shares - prev
        signed = r.moved if r.acquired else -r.moved
        if abs(change + signed) < 0.5 and abs(change - signed) >= 0.5:
            r.acquired = not r.acquired


def _options(root) -> tuple[float, dict, dict]:
    """-> (total, {title: amount}, {unit title: amount}).

    The total alone cannot answer the question it raises. Schwarzman holds
    235,686,046 of SOMETHING at Blackstone, and whether that is a stock
    option, an exchangeable partnership unit or a mis-titled share class
    changes the right answer completely -- so the titles come back too.
    """
    # THE LAST BALANCE PER SECURITY, not a sum of every row -- the same rule
    # Table I follows. Summing rows made Blackstone's 226,799,998 of
    # partnership units report as 235,686,046, because a filing that carries
    # both a transaction and a holding for one security has two rows and each
    # states the balance AFTER it. Adding them counts the position twice.
    by_title: dict = {}
    partnership: dict = {}
    for tag in ("derivativeTransaction", "derivativeHolding"):
        for node in root.iter(tag):
            title = _t(node, "securityTitle") or "(untitled)"
            if is_share_class(title):
                continue
            v = _num(node.find("postTransactionAmounts"),
                     "sharesOwnedFollowingTransaction")
            if v is None:
                # A FORM 3'S TABLE II HAS NO BALANCE FIELD (2026-09-24, Hagerty):
                # the same schema gap the share classes had (Boost Run), on
                # the other reader. The initial statement states a unit or
                # an option by the underlying security's count; an LLC unit
                # exchanges one for one, so that count is the holding.
                v = _num(node.find("underlyingSecurity"), "underlyingSecurityShares")
            if v is None:
                continue
            price = _t(node, "conversionOrExercisePrice")
            key = f"{title}  [strike {price}]" if price else title
            by_title[key] = v                    # document order: last wins
            if is_partnership_unit(title):
                partnership[key] = v
    return sum(by_title.values()), by_title, partnership




@dataclass
class Group:
    """One (security, direct-or-indirect) position, from one filing."""
    security: str
    direct: str                   # "D" or "I"
    shares: float = 0.0
    # {vehicle -> that vehicle's newest transaction balance}. Keyed by the
    # nature text as ONE document writes it; never carried between documents.
    last_txn: dict = field(default_factory=dict)
    holdings: float = 0.0         # every restated position, added
    # {vehicle -> its restated balance}, so two Forms 4 filed on the SAME
    # DAY can be merged vehicle by vehicle. See _merge_same_day.
    hold_by_vehicle: dict = field(default_factory=dict)
    filed: str = ""               # the PERIOD this group was stated for
    moved_here: bool = False      # this filing reported a transaction in this class
    opening: dict = field(default_factory=dict)   # vehicle -> balance BEFORE
                                                  # this document's first row
    anon: set = field(default_factory=set)        # base keys whose text names nothing
    passed: dict = field(default_factory=dict)    # vehicle -> every balance its chain closed at here
    rows: int = 0
    as_of: str = ""
    accession: str = ""
    table: str = "I"

    def vehicles(self) -> dict:
        """Every vehicle this filing states a balance for.

        A transaction supersedes a restated holding for the same vehicle;
        inside one document they describe the same position.
        """
        out = dict(self.hold_by_vehicle)
        out.update(self.last_txn)
        return out

    def covers(self, vehicle) -> bool:
        """Whether this document's holdings restate `vehicle`.

        A NAMED vehicle is restated by a holding line with its own key. An
        ANONYMOUS one ("See footnote") is restated by any anonymous holding
        line of the same text, because the filing cannot say which trust
        each line is: Dorsey's Form 5 lists his five trusts as five "See
        Footnote" lines, and it means all five. Segments a transaction
        filing told apart by their balances are the same trusts, so the
        restatement covers them too. Without this, a holdings-only filing
        overwrote the base key with the five-trust sum and left #2 standing
        beside it, counted twice: 48,844,566 became 84,608,558 in the
        record while the panel held.
        """
        if vehicle in self.hold_by_vehicle:
            return True
        base = base_of(vehicle)
        return base in self.anon and any(base_of(k) == base for k in self.hold_by_vehicle)

    def is_anon(self, vehicle) -> bool:
        return base_of(vehicle) in self.anon

    @property
    def key(self):
        return (self.security.lower(), self.direct)

    def label(self) -> str:
        where = "direct" if self.direct == "D" else "indirect"
        return f"{self.security} · {where}"


def retired_classes(series, remaining=None) -> dict:
    """A CLASS THE COMPANY RETIRED IS CLOSED (2026-09-16, Bloom, Lithia,
    ACV Auctions). Under a one-class cover a title naming another letter is
    its own group (the letter rule, MoonLake and Archer), and that group is
    carried from its last statement like any class. When the company then
    abolishes the class by charter and the holder files nothing (the shares
    convert by themselves), the group is carried forever: Sridhar's Class B
    of 2021, DeBoer's Class B of 2010, Chamoun's Class B stated two days
    after the conversion by a filing prepared before it. The company's own
    cover pages say when the class stopped existing.

    Read from the cover summary the series keeps year by year
    (Series.cover_years): a letter some cover NAMED is retired at the first
    later cover that (a) names classes and not that letter, or (b) carries
    ONE count with no names, the company having one class now, unless the
    letter is `remaining`, the class the walk keys as the single class (the
    cover's letter, or the person's dominant one). -> {(kind, letter): the
    counted date of that cover}. A class no cover ever named is not retired
    (MoonLake's shape: the cover omitted it); a class the newest cover still
    lists is not retired. Without a cover summary, the named class lists
    alone decide."""
    cy = getattr(series, "cover_years", None) or {}
    if cy:
        years = sorted(cy)
        out = {}
        for i, y in enumerate(years):
            for key in class_letters(cy[y]["named"]):
                if not key[1] or key in out or key == remaining:
                    continue
                for yy in years[i + 1:]:
                    c = cy[yy]
                    gone = (c["named"] and key not in class_letters(c["named"])) or (not c["named"] and c["count"] == 1)
                    if gone:
                        out[key] = c["counted"] or f"{yy}-01-01"
                        break
        newest = years[-1]
        if cy[newest]["named"]:
            for key in class_letters(cy[newest]["named"]):
                out.pop(key, None)       # still listed by the newest cover: not retired
        return out
    classes = getattr(series, "classes", None) or {}
    named = {y: m for y, m in classes.items() if y != "0000" and any(":" in str(k) for k in m)}
    if len(named) < 2:
        return {}
    years = sorted(named)
    newest = set(class_letters(named[years[-1]]))
    points = sorted(getattr(series, "points", []) or [], key=lambda p: p.as_of)
    out = {}
    for i, y in enumerate(years[:-1]):
        for key in class_letters(named[y]):
            if key in newest or key in out or not key[1]:
                continue
            later = [yy for yy in years[i + 1:] if key not in class_letters(named[yy])]
            if not later:
                continue
            first_without = later[0]
            p = next((p for p in points if ((getattr(p, "counted", "") or p.as_of) or "")[:4] == first_without), None)
            out[key] = (getattr(p, "counted", "") or p.as_of) if p else f"{first_without}-01-01"
    return out


def closed_groups(groups, retired: dict, when: str = "") -> list:
    """The groups a retirement closes at `when` (today when empty): keyed by
    a retired letter, stated before the first cover without the class."""
    if not retired:
        return []
    out = []
    for key, g in groups.items():
        got = title_letter(g.security or "")
        if got is None or got not in retired:
            continue
        cut = retired[got]
        stated = g.filed or g.as_of or ""
        if stated and stated < cut and (not when or when >= cut):
            out.append((key, g, cut))
    return out


def groups_total(groups, splits=None, when: str = "", retired: dict | None = None) -> float:
    """EVERY GROUP IN ONE BASIS (2026-09-15, Carvana). A group's shares are
    in the basis of the filing that settled it, and a class nobody has
    touched is carried from that filing as it was written. Garcia's Class B
    was stated once, in August 2023 (27,666,483 shares), and never again,
    because nothing happened to it; his Class A was restated by the first
    Form 4 after the 5-for-1 split of 7 May 2026. Summing the two as filed
    added post-split Class A to pre-split Class B and published 3.31% for a
    man who owns 13.4%, at medium confidence, for three months.

    So each group is carried through every split after its own filing into
    the basis of `when` (today when `when` is empty): the split table is
    the evidence, the same one the flows and the history's adjusted column
    already use, and the reconciliation still checks it."""
    closed = {k for k, _g, _c in closed_groups(groups, retired or {}, when)}
    if not splits:
        return sum(g.shares for k, g in groups.items() if k not in closed)
    here = splits.factor_since(when) if when else 1.0
    total = 0.0
    for k, g in groups.items():
        if k in closed:
            continue
        # THE BASIS IS THE DOCUMENT THAT STATED THE SHARES (g.filed, its
        # period), not the group's last transaction date (g.as_of), which the
        # ledger carries across documents and can predate a split the
        # document itself is written after
        basis = g.filed or g.as_of or when
        total += splits.adjust(g.shares, basis) / (here or 1.0)
    return total


def carried_through_split(groups, splits=None) -> list:
    """The groups a split moved without a filing: (security, as_of, factor)."""
    if not splits:
        return []
    out = []
    for g in groups.values():
        f = splits.factor_since(g.filed or g.as_of or "")
        if f != 1.0:
            out.append((g.security, g.filed or g.as_of, f))
    return out


@dataclass
class Ledger:
    owner_cik: str = ""
    owner_name: str = ""
    groups: dict = field(default_factory=dict)
    splits: object = None          # the split table the walk was given; the total is in today's basis
    options: float = 0.0
    option_titles: dict = field(default_factory=dict)
    partnership_units: float = 0.0
    unit_titles: dict = field(default_factory=dict)   # {unit title: amount}, the newest statement of each (2026-09-24)
    units_in_table1: float = 0.0     # RSUs/PSUs this filer reported as common stock on grant (2026-09-29); counted, and said
    units_grants: int = 0
    units_first: str = ""
    converted: list = field(default_factory=list)
    flows: Flows = field(default_factory=Flows)

    filings_read: int = 0
    forms_seen: dict = field(default_factory=dict)
    matched: int = 0
    issuer_s16: int = 0
    searched: int = 0
    other_issuers: int = 0
    issuers_seen: dict = field(default_factory=dict)
    footnoted: list = field(default_factory=list)
    match_score: float = 0.0
    runner_up: float = 0.0
    margin: float = 0.0
    officer: bool = False
    partial_match: float = 0.0
    tied: list = field(default_factory=list)
    first_filing: str = ""
    last_filing: str = ""
    last_url: str = ""
    last_remarks: str = ""    # the newest filing's <remarks>, verbatim; empty when it has none
    source: str = ""
    settled: bool = False
    note: str = ""
    trace: list = field(default_factory=list)
    form3_date: str = ""          # the initial statement, read for the flows
    opening_source: str = ""      # "Form 3", or "oldest filing read" when there is none (2026-09-17)
    oldest_before: float | None = None   # the position before the oldest filing's own transactions
    oldest_date: str = ""
    # The person's filings for this issuer. Exposed so a history walk reads
    # exactly the documents the ledger read -- if the two ever disagree on
    # which filings count, they will disagree on the answer.
    mine: list = field(default_factory=list)
    single_class: bool = False    # the title was not used at all
    retired: dict = field(default_factory=dict)   # {(kind, letter): first cover without it} (retired_classes)
    dominant: tuple | None = None                 # the class letter the walk keys as the single class
    classes: list = field(default_factory=list)   # letters the company names
    unnamed_class: dict = field(default_factory=dict)  # title -> most it held
    discovered_classes: set = field(default_factory=set)  # counted, absent from cover
    # label -> (shares, reason, source), from the curated list
    excluded: dict = field(default_factory=dict)
    supplemented: dict = field(default_factory=dict)   # {security: (shares, note)} lines the walk injected

    @property
    def total(self) -> float:
        return groups_total(self.groups, self.splits, retired=getattr(self, "retired", None))

    @property
    def lines(self) -> dict:              # kept for the CSV's `lines` count
        return self.groups


def _merge_same_day(into: Group, other: Group, newest_first: bool) -> None:
    """Fold one same-day filing's vehicles into another's.

    Walking newest-first, a vehicle already recorded came from the newer
    document and wins; walking oldest-first, the newer one arrives second
    and must overwrite.
    """
    have = into.vehicles()
    for vehicle, shares in other.vehicles().items():
        if newest_first and vehicle in have:
            continue
        into.hold_by_vehicle[vehicle] = shares
        into.last_txn.pop(vehicle, None)
    into.holdings = sum(into.hold_by_vehicle.values())
    into.shares = sum(into.vehicles().values())
    into.rows += other.rows


def build_ledger(client, issuer_cik: int, owner_name: str | None = None,
                 owner_cik: str | None = None, max_filings: int | None = None,
                 max_search: int | None = 500, fast: bool = False,
                 silences: int = 25, trace: bool = False, splits=None,
                 share_classes: int = 0, class_members=None, exclude=(),
                 on_progress=None) -> Ledger:
    """The newest filing that reports each group, summed. That is all."""
    led = Ledger(splits=splits)
    subs = client.submissions(issuer_cik)
    # Ordered by the period each filing REPORTS ON, not by the day it was
    # posted. An amendment carries the period of the report it corrects, so
    # a correction to last year's annual form filed this March is not the
    # newest statement of the position -- it is a late correction to an old
    # one, and treating it as current puts a stale balance at the front of
    # the queue. See _period in history.py for where this first bit.
    ordered = sorted((f for f in displace_amended(
                          [f for f in subs.get("_filings", [])
                           if f.get("form") in SECTION16])),
                     key=lambda f: (f.get("reportDate")
                                    or f.get("filingDate") or ""),
                     reverse=True)
    led.issuer_s16 = len(ordered)
    if not ordered:
        led.note = "this issuer has no Section 16 filings"
        return led

    def theirs(cik_str: str):
        try:
            own = client.submissions(int(str(cik_str).lstrip("0")))
        except Exception:  # noqa: BLE001
            return None
        accs = {f.get("accessionNumber") for f in own.get("_filings", [])}
        return [f for f in ordered if f.get("accessionNumber") in accs]

    mine = theirs(owner_cik) if owner_cik else None
    unread_count = 0
    if mine is None and owner_name:
        # Form 3s first -- one per insider, so a short list covering everyone.
        # Then everything else, newest first, for a Form 3 that predates
        # electronic filing. `max_search` bounds only the second pass, and
        # only to stop a CEO who has never filed from sweeping the lot.
        threes = [f for f in ordered if (f.get("form") or "").startswith("3")]
        rest = [f for f in ordered if not (f.get("form") or "").startswith("3")]
        led.searched = len(threes)

        # COLLECT EVERY CANDIDATE, THEN DECIDE. The scan-and-pick loop this
        # replaces settled on whoever crossed the line first -- and at
        # W. R. Berkley, where father (chairman, CEO until 2015) and son
        # (CEO since) normalise to the SAME name, "first" was the father,
        # whose decade-old filings carry CEO titles too. What tells them
        # apart is not whether a person EVER filed as chief executive but
        # what their NEWEST filing says: the certification is dated today,
        # and today's chief executive files today under today's title.
        CEO_TITLE = re.compile(r"\bCEO\b|CHIEF EXEC|PRINCIPAL EXEC", re.I)
        cands: dict = {}
        unread: list = []
        for f in threes + (rest if not max_search else rest[:max_search]):
            root = _parse(client, issuer_cik, f, unread)
            if root is None:
                continue
            when = f.get("filingDate") or ""
            settled_early = False
            for cik_, name_, _title, is_officer in _owners(root):
                sc = names_match(owner_name, name_)
                if sc < 0.7:
                    continue
                d = cands.setdefault(cik_, {"name": name_, "score": 0.0,
                                            "officer": False,
                                            "newest": "", "title": ""})
                d["score"] = max(d["score"], sc)
                d["officer"] = d["officer"] or is_officer
                if when >= d["newest"]:
                    d["newest"], d["title"], d["name"] = when, _title or "", name_
                # An exact-name OFFICER whose title on a RECENT filing is
                # the chief executive's cannot be beaten -- stop. All three
                # conditions matter: at 1.0 alone this once stopped on a
                # namesake trust; without the title it would stop on the
                # father; without recency, on the father's 2014 filings.
                if (sc >= 1.0 and is_officer and CEO_TITLE.search(_title or "")
                        and when >= "2024"):
                    settled_early = True
            if settled_early:
                break

        unread_count = len(unread)

        def rank(d):
            # An officer outranks a namesake vehicle outright: the
            # certification names the person who signs as principal
            # executive officer, and a trust never does. The newest-title
            # nudge is small enough to never overturn a better name.
            return (d["score"] + (1.0 if d["officer"] else 0.0)
                    + (0.05 if CEO_TITLE.search(d["title"] or "") else 0.0))

        best = (0.0, None, "")
        runner = 0.0
        tied: list = []
        for cik_, d in cands.items():
            sc = rank(d)
            if sc > best[0]:
                runner, best, tied = best[0], (sc, cik_, d["name"]), []
            elif sc == best[0] and cik_ != best[1]:
                # Two CIKs ranking equally. One person with two EDGAR
                # identifiers, or namesakes nothing in the filings can
                # tell apart -- it cannot be settled by score.
                tied.append((cik_, d["name"]))
                runner = sc
            elif sc > runner:
                runner = sc
        if not best[1]:
            # A LAST RESORT, and only when nothing matched on name at all.
            #
            # Cognizant's certification says "Ravi Kumar S"; EDGAR holds
            # "Singisetti Ravi Kumar" -- his legal surname, absent from the
            # working name, so the score is 0.00 and the search fails outright.
            #
            # Two facts rescue it together, and neither alone would do:
            # two of three name parts are shared, AND the title is exactly
            # "Chief Executive Officer" with no business unit attached. The
            # former CEO on the same list shares no name parts; every other
            # officer with a plain title shares none either.
            #
            # Requiring both is what keeps this from becoming v1's title
            # heuristic, which handed Microsoft to "CEO Microsoft Commercial".
            partial = (0.0, None, "")
            for f in threes + (rest if not max_search else rest[:max_search]):
                root = _parse(client, issuer_cik, f)
                if root is None:
                    continue
                for cik_, name_, title_, _o in _owners(root):
                    if not is_plain_ceo_title(title_):
                        continue
                    ov = token_overlap(owner_name, name_)
                    if ov >= 0.5 and ov > partial[0]:
                        partial = (ov, cik_, name_)
            if partial[1]:
                led.partial_match = partial[0]
                best = (1.0 + partial[0], partial[1], partial[2])

        if best[1]:
            _, owner_cik, led.owner_name = best
            # Two different numbers, and conflating them re-created the
            # warning the officer flag was meant to end: ranking scores carry
            # +1 for an officer, so Armstrong beat his trust 2.00 to 1.00 --
            # decisive -- while the DISPLAYED scores were 1.00 and 1.00, and
            # the margin computed from those looked like a coin flip.
            led.margin = best[0] - runner          # on the ranking scores
            led.officer = best[0] > 1.0
            led.match_score = best[0] - 1.0 if best[0] > 1.0 else best[0]
            led.runner_up = runner - 1.0 if runner > 1.0 else runner
            mine = theirs(owner_cik)
            if tied:
                # Break it on filing count: the primary identifier is the one
                # they actually file under. Recorded either way, because a
                # tie is the one case where the wrong person is a coin flip.
                led.tied = [f"{n} (CIK {c})" for c, n in tied]
                for cik_, name_ in tied:
                    alt = theirs(cik_)
                    if alt and len(alt) > len(mine or []):
                        owner_cik, led.owner_name, mine = cik_, name_, alt
    if mine is None:
        if unread_count:
            # THE THIRD HOME OF THE SAME BUG. Under SEC's throttle (or an
            # interrupt, back when it was catchable) every filing "parsed
            # to nothing", the loop skipped them all, and three sitting
            # CEOs -- Thaysen, Gelfond, Jonas -- were recorded as absent
            # from their own companies' filings. A search that could not
            # read is not a search; say so, retryably.
            raise RuntimeError(
                f"owner search could not read {unread_count} of the "
                f"filings it needed (SEC throttling?); refusing to "
                f"conclude the person is absent")
        led.note = (f"could not find this person among the issuer's "
                    f"{led.issuer_s16} Section 16 filings "
                    f"({led.searched} Form 3s searched); "
                    f"try --max-search 0 to sweep everything")
        return led

    mine = batch_continuations(client, issuer_cik, list(mine))
    led.mine = list(mine)
    led.owner_cik = (owner_cik or "").lstrip("0")
    led.owner_name = led.owner_name or (owner_name or "")
    led.matched = len(mine)

    # ------------------------------------------------------------------
    # The company's own cover page says how many classes exist. With one,
    # the security title is never read at all; with several, its class letter
    # is matched against the company's list.
    led.single_class = share_classes == 1
    letters = class_letters(class_members or {})
    # The company's own labels, not the (kind, letter) keys, because these
    # are written to a CSV and joined with "|".
    led.classes = sorted(letters.values())

    # ------------------------------------------------------------------
    # THE WALK. Newest first -- by the moment each filing speaks for, not
    # the feed's earliest-transaction date (see period_end). The first
    # filing to report a group settles it; every older mention of that
    # group is history, not a correction.
    ends: dict = {}
    mine = sorted(mine, key=lambda f: (period_end(client, issuer_cik, f, ends),
                                       f.get("filingDate") or "",
                                       f.get("accessionNumber") or ""),
                  reverse=True)
    todo = mine if max_filings is None else mine[:max_filings]
    dominant = dominant_letter(client, issuer_cik, todo) if share_classes == 1 else None
    led.dominant = dominant
    the_class = single_class_letter(letters, dominant)   # decided once, before the walk (Bloom)
    for i, f in enumerate(todo):
        if on_progress:
            on_progress(led.filings_read + 1, len(todo))
        root = _parse(client, issuer_cik, f)
        if root is None:
            continue

        # A filing in their feed that names another company. Rapino is a
        # director of Sirius XM and chief executive of Live Nation; both sit
        # in his feed and only one is about Live Nation.
        got = issuer_of(root)
        if got and got != str(int(issuer_cik)):
            led.other_issuers += 1
            led.issuers_seen[got] = led.issuers_seen.get(got, 0) + 1
            continue

        when = period_end(client, issuer_cik, f, ends)
        form = f.get("form") or ""
        acc = f.get("accessionNumber") or ""
        led.filings_read += 1
        led.forms_seen[form] = led.forms_seen.get(form, 0) + 1
        led.last_filing = led.last_filing or when
        if not led.last_url:
            led.last_url = _doc_url(issuer_cik, acc, f.get("primaryDocument", ""))
            # A REMARK IS A STRUCTURED FACT ABOUT AN UNSTRUCTURED ONE. The
            # element either exists or it does not; what it says is prose
            # the pipeline never interprets. Its presence goes on the row so
            # a person reads it once (Musk's SpaceX filings disclose 1.30B
            # restricted shares only here); its text rides along for the
            # override file to cite.
            led.last_remarks = (root.findtext("remarks") or "").strip()
        led.first_filing = when

        rows = _rows(root, form, when, acc)
        extra = supplement_rows(root, rows, form, when, acc, exclude)
        if extra:
            rows = rows + extra
            for x in extra:
                led.supplemented.setdefault(x.security, (x.shares, x.notes))

        # Flows are a different question -- every transaction ever, not a
        # position -- so they read every filing, not just the settling one.
        net_here = 0.0     # this filing's own movement, for the opening-from-the-oldest-filing below
        for r in rows + settlements_only_in_table_ii(root, rows, when, f.get("accessionNumber") or "", form):
            if not r.code:
                continue
            if r.table == "I" and r.code == "A" and r.acquired and r.moved == r.moved and units_as_common(r.notes):
                led.units_in_table1 += r.moved
                led.units_grants += 1
                led.units_first = min(led.units_first or when, when)
            if r.table == "II" and not is_share_class(r.security):
                continue
            led.flows.add(r.code, r.acquired, r.moved,
                          r.as_of, r.security, r.direct, splits)
            if r.moved == r.moved and r.moved:
                net_here += r.moved if r.acquired else -r.moved

        if trace:
            for r in rows:
                led.trace.append((when, form, r.table, r.security, r.direct,
                                  r.nature or "", r.shares, r.code,
                                  r.moved if r.acquired else -r.moved))

        # WITHIN A FILING: THE LAST TRANSACTION, PLUS EVERY HOLDING.
        #
        # A TRANSACTION row states the balance AFTER it, so several of them
        # on one position are sequential states and only the last is current.
        # Musk exercises to 727,704,534 and has 17,531,857 withheld to
        # 710,172,677 -- one position, two rows; adding them doubles him.
        #
        # A HOLDING row has no transaction code. It is a standalone position
        # the filer is restating, so several of them are several positions
        # and they add. Dorsey's five vehicles are all holdings.
        #
        # The transaction code tells them apart, and it is a structured field.
        here: dict = {}
        ends: dict = {}
        keys = vehicle_keys(rows, ends)
        for r, vehicle in zip(rows, keys):
            if r.shares != r.shares:
                led.footnoted.append((when, r.security.lower(), r.label()))
                continue
            if r.table == "II" and not is_share_class(r.security):
                continue
            # THE CLASS, NOT THE TITLE. With one class every title is it;
            # with several the title is matched to the company's own list.
            if share_classes == 1 and not names_another_letter(r.security, the_class):
                title = SINGLE_CLASS
            else:
                title = match_class(r.security, letters)
                if title is None and is_share_class(r.security):
                    # A CLASS THE PERSON'S OWN FILINGS NAME IS A CLASS THAT
                    # EXISTS. Founders' super-voting stock is routinely
                    # unregistered and absent from the cover page, and
                    # dropping those lines served Klaviyo's 25% founder as
                    # 0.000% and the Shoen family's 43% of U-Haul as 5% --
                    # the very stakes this site exists to show. The filer's
                    # own title becomes the label, the class joins the map
                    # so later lines land with it, and the row says what
                    # happened: the denominator may not include this class.
                    got = title_letter(r.security)
                    if got is not None:
                        title = r.security.strip()
                        letters[got] = title
                        led.discovered_classes.add(title)
                if title is None:
                    # Unclear titles and non-class securities: still not
                    # counted, still recorded.
                    # The NEWEST balance, not the largest ever. The walk is
                    # newest-first, so the first mention is the current one.
                    # Taking a maximum reported Block as excluding 61,382,506
                    # when its pre-IPO common stock has been at zero since
                    # 2015, making a harmless exclusion look alarming.
                    led.unnamed_class.setdefault(r.security, r.shares)
                    continue
            # THE CLASS IS THE GROUP -- INCLUDING ITS DIRECT AND INDIRECT
            # LINES.
            #
            # Keying on (class x direct/indirect) let the two halves of one
            # class go stale independently. Musk moved his Tesla position
            # into a revocable trust; the filing stated the trust line and
            # said nothing about the direct one, which was already zero. We
            # carried the old direct balance for twenty-one months and
            # published 822,733,738 shares for a man holding 411,062,076.
            #
            # The instruction this design already quotes says a filing
            # reporting a transaction in a class must state total beneficial
            # ownership in that class, on separate lines for direct and
            # indirect. Separate LINES, one TOTAL. So the class is the unit,
            # and the ownership form is part of the vehicle instead.
            key = title.lower()
            g = here.get(key)
            if g is None:
                # Keywords, not positions. Adding two fields to Group
                # silently shifted these: `rows` received the accession
                # string and the walk died on `g.rows += 1`. The tests used
                # the right arity and never touched this line.
                g = Group(security=title, direct=r.direct,
                          as_of=r.as_of, accession=acc, table=r.table)
                here[key] = g
            # SEQUENTIAL STATES OF ONE POSITION, OR SEPARATE POSITIONS?
            #
            # Musk exercises to 727,704,534 and has 17,531,857 withheld to
            # 710,172,677 -- one position, two rows, only the last current.
            # Zuckerberg converts 36,000 out of CZI Holdings leaving
            # 354,099,234, and 6,250 out of his 2006 Trust leaving 5,595,706.
            # Two positions, and they add.
            #
            # The rows look identical. What separates them is the VEHICLE, and
            # `natureOfOwnership` names it -- within THIS document, where one
            # drafter spells it one way. It is never used across documents,
            # which is where the spelling drifts and where keying on it split
            # Amphenol into thirteen groups.
            #
            # Taking the last transaction per GROUP rather than per vehicle
            # turned 361,603,542 of Zuckerberg's Class B into 7,504,308.
            # And where several vehicles share one text ("See footnote"),
            # the running balance tells them apart: see vehicle_keys.
            if is_anonymous(r.nature, r.direct):
                g.anon.add(base_of(vehicle))
            if r.code:
                if vehicle not in g.passed:
                    signed = (r.moved if r.acquired else -r.moved) or 0.0
                    g.passed[vehicle] = [r.shares - signed]      # the chain's opening
                g.last_txn[vehicle] = ends.get(vehicle, r.shares)   # where the chain ends
                g.passed[vehicle].append(r.shares)
                g.as_of = r.as_of
                g.moved_here = True      # a transaction in THIS class
            elif vehicle in g.last_txn and any(abs(b - r.shares) < 0.5 for b in g.passed.get(vehicle, ())):
                # A HOLDING AT A BALANCE THE SAME KEY'S CHAIN PASSED THROUGH
                # in this document, its opening included, is that chain
                # stated at that point, not a second position. Gelfond lists
                # "common shares (opening balance)" at 765,002 beside a chain
                # that exercises and sells back to 765,002 and then sells
                # 100,000 (his footnote: "common share balances following
                # these transactions will be 665,002"); the walk published
                # 1,430,004. Lipps lists 213,884 "updating the corrected
                # amount" beside a withholding from 213,884 to 208,982.
                # Zuckerberg's p2 restates CZI at day one's close inside a
                # two-day batch. The rows of a document are read
                # transactions first, holdings after, so the close alone is
                # not enough: the whole path is. Anonymous rows were matched
                # by vehicle_keys; named rows are matched here.
                #
                # EXACTLY, NOT WITHIN A SHARE. Schmitz has two GRATs, both
                # "By GRAT", at 274,137 and 274,138; one gifts and closes at
                # 274,137, the other stands at 274,138, and a tolerance of a
                # share read the second as the first restated. Chaining
                # tolerates rounding; a restatement is the same number.
                #
                # THE CASE THIS READS WRONG. Ergen, 30 May 2019: two GRATs
                # of 5,000,000 under the text "I", one a holding, the other
                # established that day by a G from zero to 5,000,000. Same
                # key, same balance; only the footnotes tell them apart, and
                # the walk does not read footnotes. The holding is dropped
                # and the day's residue says so. A NAMED key still carries
                # two positions that add when the holding is at no balance
                # the chain touched (Ergen's GRAT transacts while the rest
                # stands under "I").
                pass
            else:
                g.holdings += r.shares
                g.hold_by_vehicle[vehicle] = (
                    g.hold_by_vehicle.get(vehicle, 0.0) + r.shares)
            g.rows += 1
        for g in here.values():
            g.shares = sum(g.last_txn.values()) + g.holdings
        # THE POSITION BEFORE THIS FILING'S OWN TRANSACTIONS (2026-09-17). The
        # walk runs newest first, so the last filing through here is the
        # oldest read; what it stated, less what it moved, is the position
        # the flows start from when there is no Form 3 to read (a founder
        # whose initial statement predates EDGAR's XML, or the window).
        led.oldest_before = sum(g.shares for g in here.values()) - net_here
        led.oldest_date = when

        # A HOLDING THE COMPANY ITSELF SAYS IS NOT THEIRS. Curated, sourced,
        # and one class at one issuer -- see fle/exclusions.py for why there
        # is no rule for this. A row may name ONE VEHICLE (2026-09-19): the
        # foundation, the other family's trust, the child's trust someone
        # else holds; the rest of the class stands.
        apply_exclusions(here, exclude, led.excluded)
        for key, g in here.items():
            g.filed = when
            # A FILING THAT STATES A CLASS STATES IT WHOLE, HOLDINGS-ONLY OR NOT
            # (2026-09-18, decided twice). Form 4's instruction says a
            # holdings-only filing makes no claim about the whole class, and
            # for a day this walk honoured that: a holdings-only statement was
            # laid over the last whole one, its vehicles winning and the rest
            # standing. Two real filings said otherwise. Plank's 26 Aug 2026
            # filing restated Class B through the five LLCs the shares had
            # been moved INTO, and never the direct line they came OUT OF;
            # "the rest stands" kept that line, and he held 63,960,624 of a
            # class with 34,450,000 in existence. Dudum's 12 Nov 2025 filing
            # did the same with a GRAT and the trust that received its
            # shares. Filers use holdings-only filings to restate a class
            # after moving shares between their own vehicles, and the source
            # is not restated. Taken whole, both read to the share against
            # an outside source. The cost is Huang's quiet January 2021 kind
            # (one trust listed, nothing else), which understates VISIBLY --
            # the chain and statement checks flag it -- where the overlay
            # overstated silently. Understate visibly; never overstate
            # silently. The same-day pairing below handles the case Huang's
            # actually was. The per-class cap (ownership.build) now catches
            # any class counted above its cover count by any route.
            if key not in led.groups:
                led.groups[key] = g
                if g.table == "II":
                    led.converted.append(g.security)
            elif led.groups[key].filed == when:
                # TWO FORMS 4 ON ONE DAY CAN BE COMPLEMENTARY.
                #
                # Huang filed two on 6 January 2021 and said so: "This is 1
                # of 2 Form 4s being filed for the same Reporting Person".
                # The first carries his direct holding and three vehicles;
                # the second carries three DIFFERENT vehicles and reports no
                # transaction at all. Together they state 21,440,882 -- his
                # position to the share. Letting either one own the group
                # discards the other's vehicles.
                #
                # Merging per vehicle also settles the opposite case:
                # Zuckerberg's second same-day filing RESTATES the vehicles
                # of the first, so the same keys simply overwrite and the
                # total is unchanged.
                _merge_same_day(led.groups[key], g, newest_first=True)

        # TABLE II: the options are a snapshot from the newest filing that has
        # any; the PARTNERSHIP UNITS ARE A HOLDING and carry forward (2026-09-24,
        # Hagerty): a Form 3 stated 50,978,823 units of The Hagerty Group and no
        # later Form 4 restated them, so a newest-filing snapshot read zero.
        # Newest first, so the newest statement of each unit title wins.
        total_ii, titles_ii, units_ii = _options(root)
        if not led.options and total_ii:
            led.options, led.option_titles = total_ii, titles_ii
        # THE NEWEST FILING THAT STATES ANY UNITS STATES THEM WHOLE. Carrying
        # every title forward added Blue Owl's old Owl Rock titles to its
        # current ones (7.7M read as 144M); a filer who restates the units
        # restates all of them, so the first statement seen newest-first is
        # the holding, and only a person whose newer filings never mention
        # units (Hagerty, a Form 3 and Form 4s about other things) reaches back.
        if not led.unit_titles and units_ii:
            led.unit_titles = dict(units_ii)
            led.partnership_units = sum(led.unit_titles.values())

    # THE FORM 3, FOR THE FLOWS ONLY. The position no longer needs it -- a
    # filing states each group whole, so nothing is carried and there is
    # nothing to seed. But a FOUNDING STAKE appears in no transaction: it is
    # simply there on the initial statement, and without it "3.2% bought"
    # measures Musk against his grants alone and calls a founder a hired
    # executive.
    #
    # One extra request, and only for the flow columns. It cannot touch the
    # holding.
    for cand in reversed(mine):
        if not (cand.get("form") or "").startswith("3"):
            continue
        root = _parse(client, issuer_cik, cand)
        if root is None:
            continue
        got = issuer_of(root)
        if got and got != str(int(issuer_cik)):
            continue
        when = cand.get("filingDate") or ""
        opening = 0.0
        for r in _rows(root, cand.get("form") or "3", when, ""):
            if r.shares != r.shares:
                continue
            if r.table == "II" and not is_share_class(r.security):
                continue
            opening += (splits.adjust(r.shares, when) if splits else r.shares)
        led.flows.opening = opening
        led.form3_date = when
        led.opening_source = "Form 3"
        break
    # NO FORM 3 TO READ: THE OLDEST FILING IS THE CHAIN'S START (2026-09-17).
    # Caporella's initial statement at National Beverage is decades before
    # EDGAR's XML; Sabel's Venture Global position arrived in a filing the
    # walk read whole. The flows then started from zero and reported the
    # whole holding as unexplained: a fact about the window, not the number.
    # The position stated by the oldest filing read, less that filing's own
    # transactions, is the opening; every transaction from that filing on
    # is a flow. (In that filing's units: the flows adjust for splits from
    # the same date.)
    if not led.form3_date and led.oldest_date and led.oldest_before is not None:
        ob = max(led.oldest_before, 0.0)
        led.flows.opening = splits.adjust(ob, led.oldest_date) if splits else ob
        led.form3_date = led.oldest_date
        led.opening_source = "oldest filing read"

    led.settled = bool(led.groups)
    led.source = (f"read {led.filings_read} of their filings; each group is "
                  f"taken whole from the newest filing reporting it")
    if not led.groups:
        led.note = led.note or "no Section 16 holdings found"

    # A group that only ever had a footnoted balance is missing entirely.
    led.blind = sorted({lab for _, key, lab in led.footnoted
                        if key not in led.groups})
    return led
