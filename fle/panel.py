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


def run_panel(client, members, checkpoint: str, redo: str = "none",
              on_row=None, on_filing=None, exclusions=None,
              workers: int = 1) -> list[dict]:
    """-> every row, finished or resumed.

    `redo` is "none" (skip anything done), "failed" (retry errors and rows
    that did not settle), or "all".
    """
    done = _load(checkpoint)
    if redo == "all":
        done = {}
        if os.path.exists(checkpoint):
            os.remove(checkpoint)

    import threading
    from concurrent.futures import ThreadPoolExecutor
    from .edgar import STOP, Stopped

    lock = threading.Lock()
    todo, rows_by_cik = [], {}
    for i, m in enumerate(members, 1):
        prior = done.get(m.cik)
        if prior and redo == "failed":
            stale = prior.get("error") or not prior.get("settled")
            if not stale:
                rows_by_cik[m.cik] = prior
                if on_row:
                    on_row(i, len(members), prior, True)
                continue
        elif prior:
            rows_by_cik[m.cik] = prior
            if on_row:
                on_row(i, len(members), prior, True)
            continue
        todo.append((i, m))

    n_done = len(rows_by_cik)

    def one(item):
        """Identify one company. The client is shared -- its rate limiter
        is a lock, so N threads together still respect the SEC's pace --
        and the checkpoint is appended under a lock, one full line at a
        time, exactly as the sequential loop did."""
        nonlocal n_done
        i, m = item
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
        row.setdefault("form4_url", "")
        row.setdefault("cover_url", "")
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
