"""THE PARTNERSHIP REGISTER (2026-09-15): companies whose chief executive's
ownership is held as partnership units rather than shares, and what the
site does about each.

    universe/partnerships.csv
    ticker,action,structure,company,ceo,cik,cover_classes,paired_class,units_reported,reason,source,as_of

An UP-C or UPREIT puts a public corporation on top of an operating
partnership; the founders keep units in the partnership, exchangeable for
the public stock, reported in Table II of Form 4, which the site does not
count. The site's rule (shares held over shares outstanding) gives one of
three answers for such a company, decided by the filer's reporting style:
right (a paired voting share per unit sits on the cover and in the
founder's Table I: Carvana), overstated (the paired class is off the cover:
MoonLake), or a fraction of the truth (no paired class: Blackstone, 0.00%
for a founder who holds a fifth). Counting units correctly needs the
person's units, a per-company denominator source and a register of both;
for a few dozen companies that is more machinery than the number is worth,
and a page that says why it is excluded is more honest than a wrong one.

So the register records a decision per company, from the filings:
  keep     the paired class is on the cover, the founder holds it, and his
           units equal it: the ordinary rule is the proxy's number. The
           page carries a note. Nothing else changes.
  exclude  the founder's economics are units the site does not count. The
           company leaves the universe before the panel walks (read_universe
           drops it), so the panel, history, tape, screens, drafts, letter
           and watcher never see it, and it has no page: its address answers
           with the site's 404 like any company outside the universe. (A page
           explaining the exclusion was tried and removed the same day:
           nothing on the site links to it.)
THE FACTS ARE STRUCTURED FIELDS, NEVER FOOTNOTES: the security title,
underlying security, conversion price and expiration date of each Table
II row; the cover's class tags; the title and amount of each Table I row.
The one judgment a person makes is the register row, from one reading of
the filing the row cites.
Every row cites the filing that establishes it and carries an as-of date;
ops/upc_census.py --facts prints the facts for a candidate so a row can be
written, and re-checks the rows so a structure that collapsed (units
exchanged once and for all) or a new one is a line to review, never a
silent change. MLPs are not registered: the traded security is the unit
and the chief executive's units are in Table I, counted as they should be.
"""
import csv
import os

REGISTER = os.path.join("universe", "partnerships.csv")
COLUMNS = ["ticker", "action", "structure", "company", "ceo", "cik", "cover_classes", "paired_class",
           "units_reported", "reason", "source", "as_of"]


def path_for(universe_path: str) -> str:
    """The register lives beside the universe file."""
    return os.path.join(os.path.dirname(os.path.abspath(universe_path)), "partnerships.csv")


def read_register(path: str) -> dict:
    """-> {TICKER: row}; {} when there is no register."""
    if not path or not os.path.exists(path):
        return {}
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            tk = (row.get("ticker") or "").strip().upper()
            act = (row.get("action") or "").strip().lower()
            if tk and act in ("keep", "exclude"):
                out[tk] = dict(row, ticker=tk, action=act)
    return out


def excluded(path: str) -> dict:
    return {tk: r for tk, r in read_register(path).items() if r["action"] == "exclude"}


def kept(path: str) -> dict:
    return {tk: r for tk, r in read_register(path).items() if r["action"] == "keep"}


def note_for(row: dict) -> str:
    """The sentence a page carries."""
    if row["action"] == "keep":
        return (f"Ownership is held through paired {row.get('paired_class') or 'voting'} shares, one per unit of the operating "
                f"partnership, exchangeable into the public stock and counted here one for one; the cover page counts them too.")
    return (f"This company is structured as a partnership under a public corporation. {row.get('ceo') or 'Its chief executive'}'s "
            f"ownership is held as partnership units exchangeable into the stock, which the filings report in a form this site "
            f"does not count, so no stake is shown. The proxy statement states it as-converted.")
