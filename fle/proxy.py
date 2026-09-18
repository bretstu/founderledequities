"""THE PROXY CHECK (2026-09-18): the fifth question the grade asks, and the
only one that measures accuracy against the company's own statement.

Once a year the company files a proxy (DEF 14A) with a beneficial-ownership
table: each officer's shares "as of" a record date, prepared by the
company's counsel with the disclaimers already applied. That table is a
human judgement of economic ownership, published by the issuer; the data
vendors roll it forward with Form 4 deltas, which is why they agree with
each other to the share. This reads the table's row for the chief
executive and compares it to the history's row on the same date -- never
to today, so the Form 4s since the record date cannot raise a false alarm.

THE VERDICT NEVER CHANGES A NUMBER. It writes a sentence:
  pass   within 1%, or the difference is the proxy's own "options
         exercisable within 60 days" (a definitional add the proxy makes)
  warn   the difference equals one line we count (Meta: the Chan
         Zuckerberg Biohub's 1,231,037): a candidate for the exclusions
         register, with the proxy as its source; or within 5% otherwise
  fail   beyond 5% and no line explains it
  none   no proxy, no row found, no history on the date: nothing to say
A line becomes an exclusion only when a person adds it to
universe/exclusions.csv with the proxy footnote cited. The register decides;
the check points.

WHAT IS READ AND WHAT IS NOT. The table is HTML: cells, a header, a row
with the person's surname. The record date is the fixed phrase "as of
<Month D, YYYY>" nearest the table. The options add is the fixed formula
"<N> shares ... within 60 days" in a footnote that names the person. Those
are pattern matches on legal boilerplate, not prose reading; anything
outside them is "none", never a guess.
"""
import csv
import html
import os
import re
from dataclasses import dataclass
from html.parser import HTMLParser

from .founders import surnames

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
DATE_RE = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})", re.I)
AS_OF_RE = re.compile(r"as of\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(\d{4})", re.I)
NUM_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{3})+|\d{4,})(?![\d,]*%)")
OPTIONS_RE = re.compile(r"(\d{1,3}(?:,\d{3})+|\d{4,})\s+shares[^.;]{0,160}?(?:within\s+60\s+days|currently exercisable|exercisable within)", re.I)
PCT_RE = re.compile(r"\d+(?:\.\d+)?\s*%")


def iso(m) -> str:
    return f"{int(m.group(3)):04d}-{MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"


class _Tables(HTMLParser):
    """Every table as rows of cell texts, with the character offset of each
    table in the document's text, so the record date can be found near it."""

    def __init__(self):
        super().__init__()
        self.tables, self._row, self._cell, self._in_cell, self._text = [], None, [], False, []
        self._pos = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append({"rows": [], "at": len("".join(self._text))})
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._in_cell, self._cell = True, []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._row is not None and self._in_cell:
            self._row.append(re.sub(r"\s+", " ", html.unescape("".join(self._cell))).strip())
            self._in_cell = False
            self._text.append(" ")   # cells do not run together in the text
        elif tag == "tr" and self._row is not None and self.tables:
            if any(c for c in self._row):
                self.tables[-1]["rows"].append(self._row)
            self._row = None
        elif tag == "table":
            pass

    def handle_data(self, data):
        # kept whitespace-normalised as it arrives, so table offsets and the
        # text searched for dates and footnotes agree
        self._text.append(re.sub(r"\s+", " ", html.unescape(data)))
        if self._in_cell:
            self._cell.append(data)

    @property
    def text(self):
        return "".join(self._text)


@dataclass
class ProxyRead:
    proxy_date: str = ""          # the filing date of the proxy
    record_date: str = ""         # "as of" the table
    shares: float | None = None   # the person's beneficially owned shares, all classes in the row
    options: float | None = None  # the footnote's "within 60 days" add, when named for the person
    row: str = ""                 # the row as read, for the record
    note: str = ""                # why nothing was read, when nothing was


def _share_columns(header: list) -> list:
    """Which cells of a row are share counts, by the header: 'shares' or
    'number' or 'common' but not percent/option/acquire; a 'total' column,
    where the header has one, is used alone (some tables list owned,
    acquirable and total, which would otherwise be summed)."""
    h = [c.lower() for c in header]
    totals = [i for i, c in enumerate(h) if "total" in c and "%" not in c and "percent" not in c]
    if totals:
        return totals
    cols = [i for i, c in enumerate(h)
            if any(w in c for w in ("shares", "number", "common", "stock", "units"))
            and not any(w in c for w in ("%", "percent", "option", "acquir", "exercis", "within", "class of"))]
    return cols


def read_row(tables: list, names: list) -> tuple:
    """-> (table, header, row) for the ownership table's row naming the person."""
    best = None
    for t in tables:
        rows = t["rows"]
        if len(rows) < 2:
            continue
        head_i = None
        for i, r in enumerate(rows[:6]):
            joined = " ".join(r).lower()
            if "beneficial" in joined or ("shares" in joined and "percent" in joined) or ("number" in joined and "%" in joined):
                head_i = i
        if head_i is None:
            continue
        for r in rows[head_i + 1:]:
            first = " ".join(r[:2]).lower()
            if any(n.lower() in first for n in names) and any(NUM_RE.search(c) for c in r):
                cand = (t, rows[head_i], r)
                if best is None:
                    best = cand
                break
    return best or (None, None, None)


def read_proxy(html_doc: str, ceo: str, proxy_date: str = "") -> ProxyRead:
    p = _Tables()
    try:
        p.feed(html_doc)
    except Exception:  # noqa: BLE001
        return ProxyRead(proxy_date=proxy_date, note="the document could not be parsed")
    names = surnames(ceo)
    t, header, row = read_row(p.tables, names)
    if row is None:
        return ProxyRead(proxy_date=proxy_date, note="no ownership row names the chief executive")
    # the share counts in the row
    cols = _share_columns(header)
    nums = []
    for i, c in enumerate(row):
        if cols and i not in cols:
            continue
        if PCT_RE.search(c) and not NUM_RE.search(c.split("%")[0].replace(".", "x")):
            continue
        for m in NUM_RE.finditer(c):
            v = float(m.group(1).replace(",", ""))
            if v >= 100:
                nums.append(v)
                break   # one count per cell
    if not nums:
        # no header guidance: the first large number in the row
        for c in row:
            m = NUM_RE.search(c)
            if m and float(m.group(1).replace(",", "")) >= 100:
                nums = [float(m.group(1).replace(",", ""))]
                break
    if not nums:
        return ProxyRead(proxy_date=proxy_date, row=" | ".join(row), note="the row carries no share count")
    shares = float(sum(nums))
    # the record date: the "as of <date>" nearest the table
    text = p.text
    at = t["at"] if t else 0
    window = text[max(0, at - 6000): at + 6000]
    dates = [(abs(m.start() - min(6000, at)), iso(m)) for m in AS_OF_RE.finditer(window)]
    record = min(dates)[1] if dates else ""
    if not record:
        m = re.search(r"record date[^.]{0,80}?" + DATE_RE.pattern, text, re.I)
        record = iso(re.search(DATE_RE, m.group(0))) if m else ""
    # the options add: a footnote naming the person, with the 60-day formula
    options = None
    # sentences: abbreviations and decimals must not end one ("Mr. Huang", "3.3%")
    seg = re.sub(r"\b(Mr|Ms|Mrs|Dr|Jr|Sr|Inc|Co|Ltd|No)\.", r"\1", text[at: at + 40000])
    seg = re.sub(r"(\d)\.(\d)", r"\1\2", seg)
    for n in names:
        for m in re.finditer(r"[^.]{0,300}\b" + re.escape(n) + r"\b[^.]{0,400}\.", seg, re.I):
            om = OPTIONS_RE.search(m.group(0))
            if om:
                options = float(om.group(1).replace(",", ""))
                break
        if options:
            break
    return ProxyRead(proxy_date=proxy_date, record_date=record or proxy_date, shares=shares, options=options, row=" | ".join(row))


def newest_proxy(client, cik: int) -> dict | None:
    subs = client.submissions(cik)
    cands = [f for f in subs.get("_filings", []) if (f.get("form") or "").upper() == "DEF 14A"]
    if not cands:
        return None
    return max(cands, key=lambda f: f.get("filingDate") or "")


def fetch_proxy(client, cik: int) -> tuple:
    """-> (html, filing dict) of the newest proxy, or ('', None)."""
    f = newest_proxy(client, cik)
    if not f:
        return "", None
    name = (f.get("primaryDocument") or "").split("/")[-1]
    if not name:
        return "", f
    url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
           f"{(f.get('accessionNumber') or '').replace('-', '')}/{name}")
    try:
        return client.get(url), f
    except Exception:  # noqa: BLE001
        return "", f


def ours_on(history_rows: list, date: str) -> tuple:
    """-> (shares, date) the history's newest Form 4 row on or before the date."""
    rows = [h for h in history_rows if (h.get("form") or "").startswith(("3", "4", "5")) and (h.get("date") or "") <= date and h.get("shares")]
    if not rows:
        return None, ""
    r = max(rows, key=lambda h: h["date"])
    return float(r["shares"]), r["date"]


def verdict(read: ProxyRead, ours: float | None, lines: list) -> tuple:
    """-> (level, sentence). lines: [(label, shares)] we count, for naming
    the one the proxy leaves out."""
    if read.shares is None:
        return "none", read.note or "no proxy row to compare"
    if ours is None:
        return "none", f"the proxy states {read.shares:,.0f} as of {read.record_date}; no filing of ours on that date"
    d = read.shares - ours
    tol = max(ours, 1.0)
    when = f"as of {read.record_date}"
    # A LINE THAT EXPLAINS THE DIFFERENCE EXACTLY COMES FIRST, even under the
    # 1% line: Meta's Biohub is 0.36% of Zuckerberg's holding and is the
    # finding this check exists for. Rounding is not a line: the difference
    # must be at least 0.01% of the holding and the line at least 100 shares.
    if abs(d) >= 0.0001 * tol:
        for label, n in lines:
            if n and n >= 100 and abs(-d - n) <= max(0.005 * n, 2.0):
                return "warn", f"the proxy leaves out a line we count: {label} ({n:,.0f} shares); {read.shares:,.0f} against our {ours:,.0f} {when}; a candidate for the exclusions register"
        if read.options:
            for label, n in lines:
                if n and n >= 100 and abs(-(d - read.options) - n) <= max(0.005 * n, 2.0):
                    return "warn", f"after its options ({read.options:,.0f}), the proxy leaves out a line we count: {label} ({n:,.0f} shares); {when}; a candidate for the exclusions register"
    if read.options and abs(d - read.options) <= max(0.005 * read.options, 2.0):
        return "pass", f"the proxy matches after its options within 60 days ({read.options:,.0f}): {read.shares:,.0f} against our {ours:,.0f} {when}"
    if abs(d) <= 0.01 * tol:
        return "pass", f"the proxy matches: {read.shares:,.0f} against our {ours:,.0f} {when}"
    if read.options and abs(d - read.options) <= 0.01 * tol:
        return "pass", f"the proxy matches after its options within 60 days ({read.options:,.0f}): {read.shares:,.0f} against our {ours:,.0f} {when}"
    pct = d / tol * 100
    if abs(pct) <= 5:
        return "warn", f"the proxy differs by {pct:+.1f}%: {read.shares:,.0f} against our {ours:,.0f} {when}"
    return "fail", f"the proxy differs by {pct:+.1f}%: {read.shares:,.0f} against our {ours:,.0f} {when}"


CHECK_COLUMNS = ["ticker", "cik", "ceo", "proxy_date", "record_date", "proxy_shares", "proxy_options",
                 "ours", "ours_date", "level", "sentence", "row", "url"]


def load_checks(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    return {r["ticker"]: r for r in csv.DictReader(open(path, encoding="utf-8-sig"))}


def write_checks(path: str, rows: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CHECK_COLUMNS)
        w.writeheader()
        for tk in sorted(rows):
            w.writerow({c: rows[tk].get(c, "") for c in CHECK_COLUMNS})
