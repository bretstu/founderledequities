"""Shares outstanding, from the cover page of the latest 10-K or 10-Q.

`dei:EntityCommonStockSharesOutstanding` is a required cover-page tag, filed
quarterly as XBRL. It is exact, dated, and needs no parsing: Tesla's July
10-Q reports 3,949,547,394 and the API returns 3,949,547,394.

That replaces the proxy's record-date count, which had to be read out of
prose, corroborated across candidates, and floored against the group total to
reject junk. None of that is needed here.

MULTI-CLASS BREAKS THE API ENTIRELY, which is why this module has two paths.
A dual-class filer tags the fact once PER CLASS, each against a class-specific
context -- and the SEC's XBRL APIs report only facts WITHOUT dimensional
qualifiers. So for Coinbase, Meta, Alphabet and Dell the concept endpoint
returns NoSuchKey and companyfacts has no `dei` section at all. Every
single-class company in the first test run worked; every multi-class one
returned nothing.

Berkshire was the instructive exception: it answered 941,481, which is the
Class A count alone, and we took it for the whole company. A missing
denominator is loud; a wrong one is not.

So when the API has nothing, the facts are read from the filing itself. An
inline XBRL document carries each one as an <ix:nonFraction> element tagged
`dei:EntityCommonStockSharesOutstanding`, one per class, each with its own
contextRef. Summing distinct contexts gives the total.

The whole reported series is returned alongside, because a denominator that
jumps is either a real issuance or a misread tag, and those look identical
without the history beside them. Tesla went from 3.33bn to 3.95bn in ten
months -- genuine, and traceable to one option exercise, but only checkable
because the series was there.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

CONCEPT = ("https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}"
           "/dei/EntityCommonStockSharesOutstanding.json")


@dataclass
class Outstanding:
    shares: float | None = None
    as_of: str = ""
    form: str = ""
    accession: str = ""
    classes: int = 1
    # {class member -> shares}, when the cover page dimensioned them. The
    # company naming its own classes, which is what a Form 4 title has to be
    # matched against.
    per_class: dict = field(default_factory=dict)
    history: list = field(default_factory=list)
    note: str = ""
    url: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.shares and self.shares > 0)


IX_FACT = re.compile(
    r'<ix:nonfraction[^>]*?name="dei:EntityCommonStockSharesOutstanding"[^>]*>'
    r'(.*?)</ix:nonfraction>', re.I | re.S)
CONTEXT = re.compile(r'contextref="([^"]+)"', re.I)
SCALE = re.compile(r'scale="(-?\d+)"', re.I)
SIGN = re.compile(r'sign="-"', re.I)
TAGS = re.compile(r"<[^>]+>")


# The namespace prefix is a choice each filer makes -- `xbrli:context`,
# plain `context`, or something else entirely -- so it is not required here.
# Insisting on `xbrli:` found nothing in Meta's 10-Q and the class names came
# back empty with no error.
CONTEXT_BLOCK = re.compile(
    r'<(?:[\w.-]+:)?context[^>]*\bid="([^"]+)"(.*?)</(?:[\w.-]+:)?context>',
    re.I | re.S)
MEMBER = re.compile(
    r'<(?:[\w.-]+:)?explicitMember[^>]*>([^<]+)</(?:[\w.-]+:)?explicitMember>',
    re.I)


def class_names(html: str) -> dict[str, str]:
    """context id -> the share class it is dimensioned on.

    A dual-class cover page tags the count once per class, each against a
    context carrying an explicit member like `us-gaap:CommonClassAMember`.
    That member is the company naming its own classes, which is what a Form 4
    title has to be matched against -- "Clas A Common Stock" is Class A
    because Class A is one of the two things it could be.

    The context ids themselves are opaque, so the member is read from the
    context definition rather than guessed from the reference.
    """
    out = {}
    for cid, body in CONTEXT_BLOCK.findall(html or ""):
        members = [m.strip() for m in MEMBER.findall(body)]
        if members:
            out[cid] = members[-1]
    return out


def _facts_from_document(html: str, notes: list | None = None) -> dict[str, float]:
    """Every cover-page share count in an inline XBRL document, by context.

    One element per share class. `scale` is a power of ten the displayed
    figure was divided by, so a cover reading "3,949.5" with scale="6" means
    3,949,500,000 -- ignoring it understates by a factor of a million.
    """
    out: dict[str, float] = {}
    for m in IX_FACT.finditer(html or ""):
        whole = m.group(0)
        ctx = CONTEXT.search(whole)
        raw = TAGS.sub("", m.group(1)).replace(",", "").replace("\xa0", "").strip()
        if not raw:
            continue
        try:
            val = float(raw)
        except ValueError:
            continue
        scale = SCALE.search(whole)
        if scale:
            scaled = val * 10 ** int(scale.group(1))
            # THE PRINTED FIGURE OUTRANKS A SCALE THAT MAKES IT ABSURD.
            # JBS's cover reads "776,086,920 Class A common shares" and its
            # inline tag says scale="3" -- a filer error that would make
            # one class 776 billion shares. No listed company has 50
            # billion shares of anything (NVIDIA, the largest, has 24B
            # total), so when the scaled value crosses that line and the
            # printed number alone does not, trust the printed number and
            # say so. If BOTH are absurd, keep the raw value: the caution
            # machinery downstream will grade it.
            if scaled >= 50e9 > val:
                if notes is not None:
                    notes.append(
                        f"cover tag carries scale={scale.group(1)} making "
                        f"{scaled:,.0f} shares; used the printed figure")
            else:
                val = scaled
        if SIGN.search(whole):
            val = -val
        if val > 0:
            # One fact per context; a repeat is the same number restated.
            out[ctx.group(1) if ctx else f"_{len(out)}"] = val
    return out


def from_latest_filing(client, cik: int) -> Outstanding:
    """Read the cover-page facts out of the newest 10-K or 10-Q."""
    try:
        subs = client.submissions(int(cik))
    except Exception as exc:  # noqa: BLE001
        return Outstanding(note=f"could not list filings: {exc}")
    periodic = [f for f in subs.get("_filings", [])
                if f.get("form") in ("10-K", "10-Q", "10-K/A", "10-Q/A")]
    periodic.sort(key=lambda f: (f.get("filingDate") or ""), reverse=True)

    for f in periodic[:3]:
        acc = (f.get("accessionNumber") or "").replace("-", "")
        doc = (f.get("primaryDocument") or "").split("/")[-1]
        if not acc or not doc:
            continue
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{doc}"
        try:
            raw_html = client.get(url)
            scale_notes: list = []
            facts = _facts_from_document(raw_html, scale_notes)
        except Exception:  # noqa: BLE001
            continue
        if not facts:
            continue
        names = class_names(raw_html)
        return Outstanding(
            shares=sum(facts.values()),
            as_of=f.get("reportDate") or f.get("filingDate") or "",
            form=f.get("form") or "", accession=f.get("accessionNumber") or "",
            classes=len(facts),
            per_class={names.get(ctx, ctx): v for ctx, v in facts.items()},
            url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/",
            note="; ".join(scale_notes) + ("; " if scale_notes else "") + (f"read from the {f.get('form')} cover page; the XBRL API has "
                  f"no un-dimensioned fact for this filer"
                  + (f", summed across {len(facts)} share classes"
                     if len(facts) > 1 else "")),
        )
    return Outstanding(note="no cover-page share count found in recent filings")


def _is_stale(client, cik: int, newest: str, months: int = 8) -> bool:
    """Is the API's newest value older than the issuer's recent reporting?

    Compared against the issuer's own filing dates rather than today, so a
    company that has genuinely stopped filing is not condemned for it.
    """
    if not newest:
        return True
    try:
        subs = client.submissions(int(cik))
    except Exception:  # noqa: BLE001
        return False
    dates = [f.get("filingDate") or "" for f in subs.get("_filings", [])
             if f.get("form") in ("10-K", "10-Q", "10-K/A", "10-Q/A")]
    if not dates:
        return False
    latest = max(dates)
    try:
        gap = (int(latest[:4]) - int(newest[:4])) * 12 + \
              (int(latest[5:7]) - int(newest[5:7]))
    except (ValueError, IndexError):
        return False
    return gap > months


def shares_outstanding(client, cik: int) -> Outstanding:
    """The cover-page count, summed across classes, with its history."""
    try:
        # THE CONCEPT API IS A FEED, NOT A DOCUMENT: it gains a fact every
        # 10-Q. Cached forever, the denominator never moved after the first
        # read. It ages with the submissions feeds now; and since the panel
        # recomputes a company only when a periodic filing has landed, this
        # is fetched only when it can have changed.
        from .config import SUBMISSIONS_MAX_AGE
        data = client.get_json(CONCEPT.format(cik=int(cik)),
                               max_age=SUBMISSIONS_MAX_AGE)
    except Exception:  # noqa: BLE001
        # 404 here means the filer tags per class. Read the filing instead.
        return from_latest_filing(client, cik)

    rows = [u for u in data.get("units", {}).get("shares", [])
            if isinstance(u.get("val"), (int, float)) and u["val"] > 0]
    if not rows:
        return from_latest_filing(client, cik)

    # STALE IS AS BAD AS ABSENT. Fox's concept API holds exactly one value
    # ever recorded -- 1 share, dated 2019-03-18, from the shell entity that
    # existed before the spin-off. It has been dual-class since, so every
    # later fact is dimensional and the API omits it.
    #
    # Falling back only on an EMPTY response let that single stale datum win,
    # and one share as a denominator turned an 87 million share holding into
    # 8,790,139,900%. A figure the API cannot have refreshed is not a figure.
    newest = max((u.get("end") or "") for u in rows)
    if _is_stale(client, cik, newest):
        alt = from_latest_filing(client, cik)
        if alt.ok:
            alt.note = (alt.note + "; the XBRL API's newest value was "
                        f"{newest}, too old to use").strip("; ")
            return alt

    # `end` is the as-of date printed on the cover; `filed` breaks ties when a
    # company amends. Both matter: an amended 10-K restates the same date.
    rows.sort(key=lambda u: (u.get("end") or "", u.get("filed") or ""))
    latest_end = rows[-1].get("end") or ""

    # Every fact sharing the latest cover date -- one per share class.
    current = [u for u in rows if (u.get("end") or "") == latest_end]
    by_accession: dict = {}
    for u in current:
        by_accession.setdefault(u.get("accn") or "", []).append(u)
    # If a single filing reports several, they are the classes of that filing.
    # Across filings, prefer the newest accession rather than summing an
    # amended figure on top of the original.
    chosen = max(by_accession.items(),
                 key=lambda kv: max((x.get("filed") or "") for x in kv[1]))[1]

    total = sum(float(u["val"]) for u in chosen)
    hist = [(u.get("end") or "", float(u["val"]), u.get("form") or "")
            for u in rows[-12:]]
    out = Outstanding(
        shares=total, as_of=latest_end,
        form=chosen[0].get("form") or "", accession=chosen[0].get("accn") or "",
        classes=len(chosen), history=hist,
    )
    if out.accession:
        out.url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
                   f"{out.accession.replace('-', '')}/")
    if len(chosen) > 1:
        out.note = (f"summed across {len(chosen)} share classes reported on the "
                    f"same cover page")
    return out


def jumped(hist: list, threshold: float = 0.10) -> tuple[bool, str]:
    """Did the count move more than a buyback could explain?

    A denominator is supposed to drift down slowly. A rise of any size, or a
    fall of more than a tenth, is an event -- an issuance, a split, a
    conversion, or a tag read wrongly. Saying which is a human's job; noticing
    is not.
    """
    vals = [(d, v) for d, v, _ in hist if v]
    if len(vals) < 2:
        return False, ""
    (d0, v0), (d1, v1) = vals[-2], vals[-1]
    move = (v1 - v0) / v0
    if abs(move) < threshold:
        return False, ""
    return True, (f"{move*100:+.1f}% between {d0} and {d1} "
                  f"({v0:,.0f} to {v1:,.0f})")
