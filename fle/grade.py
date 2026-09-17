"""THE GRADE: FOUR QUESTIONS, ANSWERED FROM THE RECORD (2026-09-17).

For three weeks the grade was the worst flag on the record: any "problem"
made a stake low, any "caution" medium, over thirty flag sites written at
different times for different reasons. An empty class outranked a 60,000-
share residual; a convertible class confirmed at 1:1 graded the same as a
count a year old. The flags were good; the grade thrown over them was a
coin sorter.

Confidence here means one thing: our own record is internally consistent
and current for this company. Four checks, each a question a skeptical
reader would ask, each scored pass / warn / fail from facts the pipeline
already computes; the grade is the worst answer, and the failing check's
sentence is what the tape's "?" and the company page say.

  chain        Does the arithmetic run? Every Form 4 states the balance after
               each line, so the position before plus the filing's own
               transactions must equal the position after. The ledger's
               residue per filing (history.csv `unexplained`, one split-
               adjusted basis) is that test. Over the person's filings of
               the last 12 months: pass when every filing closed or the open
               steps are under 1% of the position at the time; warn 1-10%;
               fail over 10%. Twelve months because the question is whether
               TODAY'S number sits on a record that closes, not whether 2004
               did; and filing to filing because that is what a Form 4
               asserts (the lifetime flows grade the openings, not the
               numbers: fle/flows.py stays for the letter's attributions).
  statement    Is what we hold on the record fresh and whole? Every counted
               line stated within 18 months and the newest filing restating
               every line: pass. A line 18 months to 5 years old, or a
               newest filing that named fewer lines (the partial-statement
               trade-off, cli.edge_confidence): warn. A line known only from
               a filing older than 5 years, or only from a footnote: fail.
  classes      Do the person's shares map onto the cover's count? Every held
               class named on the cover, no assumed ratio: pass. A
               convertible class counted 1:1, a retired class closed by the
               cover: warn. A class with shares the cover does not count,
               partnership units, a walk that did not settle: fail.
  denominator  Is the count the right count? A cover count within 150 days of
               today, larger than the holding: pass; 150-365 days: warn;
               older, missing, or smaller than the holding: fail. The
               numerator's age is not graded: a founder who has not filed
               in nine years has, by the rules, had nothing to file.

  identity     Not one of the four, but not dropped: a "problem" the four do
               not cover (the matched insider is not flagged as an officer)
               still fails, because it doubts whose stake this is.

What none of this measures is whether the founder owns what the filings
say. That needs an outside statement of the same fact -- the proxy's
beneficial-ownership table on its record date -- and is the fifth check,
built after these four are live.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
from collections import defaultdict

PASS, WARN, FAIL = "pass", "warn", "fail"
CHAIN_MONTHS = 12
CHAIN_WARN, CHAIN_FAIL = 1.0, 10.0          # per cent of the position at the time
LINE_WARN_DAYS, LINE_FAIL_DAYS = 548, 1826  # 18 months, 5 years
COUNT_WARN_DAYS, COUNT_FAIL_DAYS = 150, 365
CHECKS = ("chain", "statement", "classes", "denominator")

FEWER_LINES = "the newest filing names fewer lines than the one before it"


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _date(s):
    try:
        return dt.date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


def disagreement(hist_rows: list, owner_cik: str, panel_shares) -> tuple[str, str] | None:
    """THE TWO WALKS MUST AGREE (2026-09-17, Palvella): the panel's ledger and
    the history read the same filings; where the history's newest filing row
    and the panel's holding differ by more than 1%, one of them keyed a class
    or a line differently (Palvella's custom cover member kept one line of
    thirty-six in the history), and the record is not consistent with itself."""
    if panel_shares in (None, 0):
        return None
    rows = [h for h in hist_rows
            if (h.get("form") or "").startswith(("3", "4", "5"))
            and (not owner_cik or (h.get("owner_cik") or owner_cik) == owner_cik)]
    if not rows:
        return None
    last = max(rows, key=lambda h: (h.get("date") or "", h.get("accession") or ""))
    hs = _num(last.get("shares"))
    if hs is None:
        return None
    if abs(hs - panel_shares) / max(abs(panel_shares), 1.0) > 0.01:
        return FAIL, (f"the record disagrees with itself: the history reads the newest filing as {hs:,.0f} shares, "
                      f"the panel as {panel_shares:,.0f}")
    return None


def chain(hist_rows: list, owner_cik: str, today: dt.date, panel_shares=None) -> tuple[str, str]:
    """hist_rows: this ticker's history rows (dicts), any order."""
    dis = disagreement(hist_rows, owner_cik, panel_shares)
    if dis:
        return dis
    since = (today - dt.timedelta(days=30 * CHAIN_MONTHS)).isoformat()
    rows = [h for h in hist_rows
            if (h.get("date") or "") >= since
            and (h.get("form") or "").startswith(("4", "5"))
            and (not owner_cik or (h.get("owner_cik") or owner_cik) == owner_cik)]
    if not rows:
        return PASS, ""
    # A PARTIAL STATEMENT AND ITS RESTORATION ARE ONE KNOWN EVENT (2026-09-17):
    # history marks the depressed rows (mark_restated) and the first row after
    # the marked run is the reversal; neither is an open step here. Alphabet,
    # Walmart, AT&T, Aon: the January partial and the February restatement
    # read as "the stake rose N% with no transaction" until this. A drop not
    # yet restored stays open, and the statement check names it.
    rows.sort(key=lambda h: ((h.get("date") or ""), (h.get("accession") or "")))
    worst, worst_row = 0.0, None
    prev_marked = False
    for h in rows:
        marked = (h.get("restated") or "").upper() == "TRUE"
        exit_of_marked = prev_marked and not marked
        prev_marked = marked
        if marked or exit_of_marked:
            continue
        u = _num(h.get("unexplained")) or 0.0
        if abs(u) < 1:
            continue
        after = abs(_num(h.get("shares")) or 0.0)
        before = abs(after - u)
        share = abs(u) / max(before, after, 1.0) * 100
        if share > worst:
            worst, worst_row = share, h
    if worst_row is None or worst < CHAIN_WARN:
        return PASS, ""
    when = (worst_row.get("date") or "")[:10]
    what = ("rose" if (_num(worst_row.get("unexplained")) or 0) > 0 else "fell")
    text = (f"the arithmetic does not close: on {when} the stake {what} {worst:.0f}% with no transaction to "
            f"explain it (a partial statement, or a line that appeared or vanished)")
    return (FAIL if worst >= CHAIN_FAIL else WARN), text


def statement(row: dict, today: dt.date) -> tuple[str, str]:
    flags = " | ".join(x for x in (row.get("problems") or "", row.get("cautions") or "") if x)
    if "only ever footnoted" in flags:
        return FAIL, "a line of the holding is known only from a footnote"
    oldest, oldest_days = "", 0
    for d in (row.get("lines_stated") or "").split("|"):
        dd = _date(d)
        if dd is None:
            continue
        age = (today - dd).days
        if age > oldest_days:
            oldest, oldest_days = d, age
    if oldest_days > LINE_FAIL_DAYS:
        return FAIL, f"a line of the holding was last stated on {oldest}, more than five years ago"
    if FEWER_LINES in flags:
        return WARN, "the newest filing names fewer lines than the one before it, with no transaction to explain the difference; the stake may be understated until the next complete filing"
    if oldest_days > LINE_WARN_DAYS:
        return WARN, f"a line of the holding was last stated on {oldest}, more than eighteen months ago"
    return PASS, ""


def classes(row: dict) -> tuple[str, str]:
    flags = " | ".join(x for x in (row.get("problems") or "", row.get("cautions") or "") if x)
    low = flags.lower()
    if "absent from the cover page" in flags:
        return FAIL, "a class with shares that the cover page does not count; the denominator may not include them"
    if "walk did not settle" in flags:
        return FAIL, "the walk did not settle; the total is a floor"
    if (row.get("operating_partnership") or "").lower() == "true" and (_num(row.get("pct")) or 0) < 0.05:
        return FAIL, "the holding is partnership units, not common stock"
    if "not issued stock" in flags or "partnership units" in low:
        return FAIL, "part of the holding is units the site does not count"
    if "convertible class counted" in flags:
        return WARN, "a convertible class is counted at one for one"
    if "a class the company retired" in flags:
        return WARN, "a class the company retired was closed by the cover page"
    return PASS, ""


def denominator(row: dict, today: dt.date) -> tuple[str, str]:
    out, sh = _num(row.get("outstanding")), _num(row.get("shares"))
    flags = " | ".join(x for x in (row.get("problems") or "", row.get("cautions") or "") if x)
    if not out or "no cover-page share count" in flags:
        return FAIL, "no usable cover-page share count"
    if sh and sh > out:
        return FAIL, "the holding exceeds the cover page's count"
    d = _date(row.get("outstanding_as_of"))
    if d is None:
        return WARN, "the cover page's count carries no date"
    age = (today - d).days
    if age > COUNT_FAIL_DAYS:
        return FAIL, f"the cover page's count is from {row.get('outstanding_as_of')}, more than a year old"
    if age > COUNT_WARN_DAYS:
        return WARN, f"the cover page's count is from {row.get('outstanding_as_of')}, {age} days old"
    return PASS, ""


def identity(row: dict) -> tuple[str, str]:
    p = row.get("problems") or ""
    if "is not flagged as an officer" in p or "not flagged" in p:
        return FAIL, p.split("|")[0].strip()[:200]
    return PASS, ""


def grade_row(row: dict, hist_rows: list, today: dt.date | None = None) -> dict:
    """-> {'confidence', 'chain', 'statement', 'classes', 'denominator', 'reason'}"""
    today = today or dt.date.today()
    if row.get("pct") in ("", None) or _num(row.get("shares")) is None:
        return {"confidence": "none", "chain": "", "statement": "", "classes": "", "denominator": "", "reason": ""}
    results = {
        "chain": chain(hist_rows, row.get("owner_cik") or "", today, _num(row.get("shares"))),
        "statement": statement(row, today),
        "classes": classes(row),
        "denominator": denominator(row, today),
    }
    ident = identity(row)
    levels = [lvl for lvl, _ in results.values()] + [ident[0]]
    conf = "low" if FAIL in levels else "medium" if WARN in levels else "high"
    order = (FAIL, WARN)
    reason = ""
    for want in order:
        for name in CHECKS:
            lvl, text = results[name]
            if lvl == want and text:
                reason = text
                break
        if not reason and want == FAIL and ident[0] == FAIL:
            reason = ident[1]
        if reason:
            break
    out = {"confidence": conf, "reason": reason}
    for name in CHECKS:
        lvl, text = results[name]
        out[name] = lvl if lvl == PASS else f"{lvl}: {text}"
    return out


def apply_grades(panel_path: str, history_path: str, today: dt.date | None = None) -> dict:
    """Rewrite panel.csv with the four checks and the grade. The reason is
    put first among the row's problems (low) or cautions (medium) so the
    site, which shows the first flag, shows the grade's own sentence."""
    today = today or dt.date.today()
    hist = defaultdict(list)
    if os.path.exists(history_path):
        with open(history_path, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                hist[r.get("ticker") or ""].append(r)
    with open(panel_path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        cols = list(reader.fieldnames or [])
        rows = list(reader)
    for c in ("chain", "statement", "classes", "denominator"):
        if c not in cols:
            cols.append(c)
    tally = defaultdict(int)
    moved = []
    for row in rows:
        before = row.get("confidence") or ""
        g = grade_row(row, hist.get(row.get("ticker") or "", []), today)
        for c in ("chain", "statement", "classes", "denominator"):
            row[c] = g[c]
        row["confidence"] = g["confidence"]
        if g["reason"]:
            field = "problems" if g["confidence"] == "low" else "cautions"
            items = [x for x in (row.get(field) or "").split("|") if x and x != g["reason"]]
            row[field] = "|".join([g["reason"]] + items)
        tally[g["confidence"]] += 1
        if before and before != g["confidence"]:
            moved.append((row.get("ticker"), before, g["confidence"]))
    tmp = panel_path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, panel_path)
    return {"tally": dict(tally), "moved": moved}
