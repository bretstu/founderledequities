"""Running the whole universe, and writing something a human can check.

THE PANEL IS THE VERIFICATION SHEET. v1 kept them apart -- a panel CSV of
answers, and a separate worksheet built from it -- which meant the answers
shipped first and the checking came later, if at all. Here every row carries
the links needed to verify it: the Form 4 the numerator was last stated on,
and the filing the denominator came from. Checking a row means opening two
documents and comparing two numbers.

RESUMABLE, because five hundred companies is long enough that something will
interrupt it. Each finished row is appended to a JSONL checkpoint as it
completes; re-running skips what is already there. Nothing is held in memory
until the end, so an interrupted run loses at most one company.

NO SAMPLING. v1 had --sample and --seed, and they mostly produced runs whose
results could not be compared to each other. Run everything, or name the CIKs
you want.
"""
from __future__ import annotations

import csv
import re
import json
import os
from dataclasses import asdict

from .ownership import Ownership, build

COLUMNS = [
    # WHO, AND THE ANSWER. `ceo` is the name the certification gives;
    # `owner_name` is the name on the filings we read. Side by side they are
    # the identity check, and a reader spots "Brian Armstrong" against
    # "Brian Armstrong Living Trust" faster than any rule.
    "cik", "ticker", "company", "ceo", "owner_cik", "owner_name",
    "is_officer",
    "pct", "shares", "outstanding", "shares_as_of", "outstanding_as_of",

    # WHETHER TO TRUST IT. `problems` mean data is known missing and force
    # the row to low; `cautions` mean a judgment was made. `error` is a row
    # that produced no figure at all.
    "confidence", "problems", "cautions", "error",

    # HOW TO CHECK IT BY HAND. Two links: the filing the numerator came
    # from, and the one the denominator came from.
    "form4_url", "cover_url",
    # A REMARK IS A STRUCTURED FACT ABOUT AN UNSTRUCTURED ONE: the newest
    # filing's <remarks>, verbatim, for a person to read; and when a cited
    # override adds shares the tables leave out, the tabled figure beside it.
    "remarks", "shares_tabled",
    # WHERE THE FIGURE CAME FROM when it is not a plain Section 16 sum:
    # "SC 13G/A 2024-02-13" for a dated schedule stake, "manual" for a
    # curated addition. The page reads it as src13; it was never written.
    "stake_source",

    # HOW THE STAKE WAS ACQUIRED. Lifetime flows, split-adjusted, never a
    # position -- `codes` carries the full tally so the buckets need not.
    "held_at_start", "bought", "granted", "from_derivative", "bought_share",
    "codes",

    # WHAT IS NOT IN THE FIGURE. Options and units are excluded on purpose,
    # and at an up-C that exclusion is most of the person's interest -- so
    # the row says what was left out rather than only that something was.
    "options", "option_titles", "partnership_units", "operating_partnership",

    # Whether the security title was read at all. One class means it was not.
    "single_class", "classes", "unnamed_class",
    "excluded_shares", "excluded_detail",
]


def _load(path: str) -> dict:
    """Rows already done, by CIK."""
    done = {}
    if not os.path.exists(path):
        return done
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                done[int(row["cik"])] = row
            except Exception:  # noqa: BLE001
                continue          # a truncated last line is not fatal
    return done


def _append(path: str, row: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


# THE FILINGS THAT CAN MOVE A ROW. Forms 3/4/5 move the numerator; the
# periodic reports move the denominator (and name the chief executive);
# 20-F/40-F are the foreign equivalents; 13D/13G are the fallback stake for
# filers exempt from Section 16. A new 8-K or prospectus cannot change the
# answer and does not trigger a recompute.
FINGERPRINT_FORMS = ("3", "4", "5", "3/A", "4/A", "5/A",
                     "10-K", "10-Q", "10-K/A", "10-Q/A",
                     "20-F", "40-F", "20-F/A", "40-F/A",
                     "SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A")
_SECTION16 = ("3", "4", "5", "3/A", "4/A", "5/A")


def _newest(subs: dict, forms) -> str:
    best = ("", "")
    for f in subs.get("_filings", []):
        if f.get("form") in forms:
            k = (f.get("filingDate") or "", f.get("accessionNumber") or "")
            if k > best:
                best = k
    return f"{best[0]} {best[1]}".strip()


def feed_fingerprint(client, cik: int, owner_cik=None) -> str:
    """The newest filing that could change this company's row, on the
    issuer's feed and on the executive's own. Two small requests; both
    feeds are read by the recompute anyway, so a company that does get
    recomputed pays nothing extra."""
    fp = _newest(client.submissions(int(cik)), FINGERPRINT_FORMS)
    if owner_cik:
        try:
            own = client.submissions(int(str(owner_cik).lstrip("0") or 0))
            fp += " | " + _newest(own, _SECTION16)
        except Exception:  # noqa: BLE001 - an unreadable owner feed forces a recompute
            fp += " | ?"
    return fp


# THE ROW'S SCHEMA. A row carried from the checkpoint was computed by some
# earlier version of the walk; if that version did not produce a field the
# current one relies on, the row is not a faithful copy of what a recompute
# would give, and it is walked again once. The SpaceX row, carried across
# the night the `remarks` field was added, had no remark to test the curated
# addition against and the addition was reported lapsed; this is what makes
# such a row recompute instead.
SCHEMA_FIELDS = ("remarks", "direct_classes")


def _reusable(row: dict) -> bool:
    """A prior row worth carrying: it produced a figure, settled, carries
    the fingerprint that says what it was computed from, and was computed
    by a walk that produced every field the current one relies on."""
    return bool(row.get("fingerprint")) and not row.get("error") \
        and bool(row.get("settled")) \
        and all(f in row for f in SCHEMA_FIELDS)


def _digits_present(text: str, n: float) -> bool:
    """Is the figure asserted in the text? Commas, spaces and thin spaces
    between digits are ignored; the match must be a whole number, not a
    substring of a longer one. String matching, never interpretation."""
    if not text:
        return False
    flat = re.sub(r"(?<=\d)[,\s\u202f\u00a0](?=\d)", "", text)
    return re.search(rf"(?<!\d){int(n)}(?!\d)", flat) is not None


def apply_additions(row: dict, adds: list) -> None:
    """THE PIPELINE READS TABLES; A PERSON READS REMARKS. An addition in
    universe/exclusions.csv (an entry with `shares`) records shares a filer
    states, in a remark, are held of record but left out of the tables.
    This adds them after the walk, labels the source `manual`, keeps the
    tables' figure in `shares_tabled`, and writes the receipt into the
    row's cautions so the page can show "held" and "of it, in the tables".

    THREE GUARDS, ALL STRUCTURAL, so a hand-recorded number can never
    outlive its source, and never double-counts:
      1. the tables win: if the walk now finds that class held DIRECTLY in
         a table (a vesting tranche, a change of filing position), the
         addition suspends and the row says so;
      2. the figure must still be asserted: the newest filing's remark
         must contain the recorded number (commas or not); a changed
         number -- vesting, a typo, anything -- suspends it;
      3. no remark, no addition: the row says to read the filing.
    Every suspension is a caution a person reads. None reads the sentence."""
    if not adds or row.get("shares") in (None, ""):
        return
    try:
        base = float(row["shares"])
    except (TypeError, ValueError):
        return
    caut = row.get("cautions") or ""
    remark = (row.get("remarks") or "").strip()
    direct = set((row.get("direct_classes") or "").split("|")) - {""}
    live, notes = [], []
    for a in adds:
        sec = (a.security or "").split("(")[0].strip().lower()
        if sec and sec in direct:
            notes.append(f"addition of {int(a.shares):,} shares suspended: the tables now report "
                         f"{a.security} held directly -- read the filing and settle universe/exclusions.csv")
        elif not remark:
            notes.append(f"addition of {int(a.shares):,} shares lapsed: the newest filing carries no remark "
                         f"-- read it and settle universe/exclusions.csv")
        elif not _digits_present(remark, a.shares):
            notes.append(f"addition of {int(a.shares):,} shares suspended: the newest filing's remark no longer "
                         f"states that figure -- read it and settle universe/exclusions.csv")
        else:
            live.append(a)
    if live:
        total = sum(float(a.shares) for a in live)
        row["shares"] = base + total
        row["shares_tabled"] = base
        if row.get("outstanding") not in (None, ""):
            try:
                row["pct"] = round(100.0 * row["shares"] / float(row["outstanding"]), 4)
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        row["stake_source"] = "manual"
        for a in live:
            notes.append(f"includes {int(a.shares):,} shares of {a.security or 'stock'} the filings disclose "
                         f"in a remark rather than a table; {int(base):,} in the tables. Source: {a.source}")
    for n in notes:
        caut = f"{caut}|{n}" if caut else n
    row["cautions"] = caut


def run_panel(client, members, checkpoint: str, redo: str = "none",
              on_row=None, on_filing=None, exclusions=None,
              workers: int = 1, prior: dict | None = None) -> list[dict]:
    """-> every row, finished or resumed.

    `exclusions` (fle.exclusions.Exclusions) carries both directions of the
    curated file: what the walk removes, and the additions applied to every
    row after it (see apply_additions).

    `redo` is "none" (skip anything done), "failed" (retry errors and rows
    that did not settle), or "all".

    `prior` is last run's finished rows, by CIK. RECOMPUTE ONLY WHAT
    CHANGED: a company whose feeds show no new filing that could move its
    row (see FINGERPRINT_FORMS) keeps last run's row, fingerprint and all.
    Reading the two feeds is the whole cost -- some 4,300 small requests for
    the universe, a quarter of an hour -- against recomputing 2,135 rows.
    Errors and unsettled rows are never carried; they are retried.
    """
    done = _load(checkpoint)
    if redo == "all":
        done = {}
        if os.path.exists(checkpoint):
            os.remove(checkpoint)
    prior = prior or {}

    import threading
    from concurrent.futures import ThreadPoolExecutor
    from .edgar import STOP, Stopped

    lock = threading.Lock()
    todo, rows_by_cik = [], {}
    for i, m in enumerate(members, 1):
        already = done.get(m.cik)
        if already and redo == "failed":
            stale = already.get("error") or not already.get("settled")
            if not stale:
                rows_by_cik[m.cik] = already
                if on_row:
                    on_row(i, len(members), already, True)
                continue
        elif already:
            rows_by_cik[m.cik] = already
            if on_row:
                on_row(i, len(members), already, True)
            continue
        todo.append((i, m))

    n_done = len(rows_by_cik)
    carried = 0

    def one(item):
        """Identify one company. The client is shared -- its rate limiter
        is a lock, so N threads together still respect the SEC's pace --
        and the checkpoint is appended under a lock, one full line at a
        time, exactly as the sequential loop did."""
        nonlocal n_done, carried
        i, m = item
        old = prior.get(m.cik)
        fp = None
        if old is not None and _reusable(old):
            try:
                fp = feed_fingerprint(client, m.cik, old.get("owner_cik"))
            except Stopped:
                return None
            except Exception:  # noqa: BLE001 - a feed that will not read means recompute
                fp = None
            if fp is not None and fp == old.get("fingerprint"):
                with lock:
                    _append(checkpoint, old)
                    rows_by_cik[m.cik] = old
                    n_done += 1
                    carried += 1
                    if on_row:
                        on_row(n_done, len(members), old, True)
                return None
        try:
            # per-filing progress is per-thread noise when interleaved;
            # only the single-threaded run narrates at that grain
            tick = ((lambda a, b, _m=m, _i=i: on_filing(_i, len(members), _m, a, b))
                    if (on_filing and workers == 1) else None)
            rec = build(client, m.cik, company=m.company, ticker=m.ticker,
                        exclusions=exclusions, on_progress=tick)
        except Stopped:
            return None          # interrupted: not an answer, not an error
        except Exception as exc:  # noqa: BLE001
            if STOP.is_set():
                return None      # the interrupt surfaced as some other error
            rec = Ownership(cik=m.cik, company=m.company,
                            error=f"{type(exc).__name__}: {exc}")
        row = rec.as_dict()
        # Split out so a sheet can be sorted by what actually needs a human.
        row["problems"] = "|".join(t for l, t in rec.graded if l == "problem")
        row["cautions"] = "|".join(t for l, t in rec.graded if l == "caution")
        row.update(ticker=m.ticker,
                   checked_shares="", checked_by="", note="")
        if row.get("remarks"):
            # structural: the element is there; what it says is for a person
            row["cautions"] = (row["cautions"] + "|" if row["cautions"] else "") + \
                "the newest filing carries a remark; read it (remarks column)"

        row.setdefault("form4_url", "")
        row.setdefault("cover_url", "")
        # the fingerprint is taken from the same feeds the recompute just
        # read (served from the hours-old cache), so it describes exactly
        # what this row was computed from -- never a filing that landed
        # between the compute and the stamp
        try:
            row["fingerprint"] = feed_fingerprint(client, m.cik, row.get("owner_cik"))
        except Exception:  # noqa: BLE001
            row["fingerprint"] = ""
        with lock:
            _append(checkpoint, row)
            rows_by_cik[m.cik] = row
            n_done += 1
            if on_row:
                on_row(n_done, len(members), row, False)
        return None

    if workers <= 1:
        for item in todo:
            one(item)
    elif todo:
        from concurrent.futures import wait as _wait
        ex = ThreadPoolExecutor(max_workers=workers)
        futs = [ex.submit(one, item) for item in todo]
        try:
            # Poll rather than block: a main thread parked in an
            # uninterruptible wait never sees Ctrl+C. One second of
            # latency is the price of a stop that always lands.
            pending = set(futs)
            while pending:
                done, pending = _wait(pending, timeout=1.0)
                for f in done:
                    f.result()
        except KeyboardInterrupt:
            # STOP MEANS NOW. Cancel everything queued, tell every waiting
            # worker to abandon its request, and let the pool drain the
            # handful in flight -- seconds, not the rest of the universe.
            STOP.set()
            for f in futs:
                f.cancel()
            ex.shutdown(wait=True, cancel_futures=True)
            raise
        ex.shutdown(wait=True)

    rows = [rows_by_cik[m.cik] for m in members if m.cik in rows_by_cik]
    # A CITED CORRECTION APPLIES TO EVERY ROW, RECOMPUTED OR CARRIED, ONCE.
    # A row carried from the checkpoint already carries its correction
    # (shares_tabled is set); a fresh walk does not. Idempotent by that mark.
    for row in rows:
        if exclusions and row.get("shares_tabled") in (None, ""):
            apply_additions(row, exclusions.additions_for(row.get("ticker") or ""))
    if prior:
        print(f"  {carried} carried over unchanged, "
              f"{len(rows) - carried - len(done)} recomputed")
    return rows


def write_csv(rows: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        # A genuine 0% sorts with the data, below every real holding but
        # above the rows that produced nothing at all.
        def _rank(r):
            pct = r.get("pct")
            return -pct if isinstance(pct, (int, float)) else 1e9

        def flat(v):
            # A newline anywhere in a row makes a spreadsheet render it as a
            # multi-line cell. Filers wrap long titles, and a footnote can
            # arrive with one too -- so the writer flattens rather than
            # trusting every field to have been cleaned upstream.
            return " ".join(str(v).split()) if isinstance(v, str) else v

        for r in sorted(rows, key=_rank):
            w.writerow({k: flat(r.get(k, "")) for k in COLUMNS})


def summarise(rows: list[dict]) -> dict:
    got = [r for r in rows if r.get("pct") not in (None, "")]
    by_conf: dict = {}
    for r in rows:
        by_conf[r.get("confidence") or "none"] = by_conf.get(
            r.get("confidence") or "none", 0) + 1
    flags: dict = {}
    for r in rows:
        for f in (r.get("flags") or "").split("|"):
            if f:
                key = f.split(";")[0].split("(")[0].strip()[:52]
                flags[key] = flags.get(key, 0) + 1
    return {
        "total": len(rows),
        "with_a_figure": len(got),
        "errors": sum(1 for r in rows if r.get("error")),
        "unsettled": sum(1 for r in rows if not r.get("settled")),
        "confidence": by_conf,
        "flags": sorted(flags.items(), key=lambda kv: -kv[1]),
    }
