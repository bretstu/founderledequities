"""One company's history walk, packaged for a worker process.

WHY A SEPARATE PROCESS PER BATCH OF COMPANIES. The denominator stage reads
the full 10-K and 10-Q documents -- inline XBRL, five to thirty megabytes
each, forty of them per company -- and scans them for the cover-page share
count. Each document is released when the function returns, but Python's
allocator keeps the high-water mark: after a few hundred companies the
process sits at gigabytes it will never use again. The nightly peaked at
8G for 500 companies; 2,100 would not fit the machine. No amount of
streaming rows to disk changes that, because the rows were never the
problem.

The fix is to let the operating system take the memory back: walk
companies in short-lived worker processes, each replaced after a fixed
number of companies. Memory is bounded by ONE worker's high-water mark
times the number of workers, regardless of universe size. And since the
walk is network-bound, two or three workers finish sooner than one.

THE RATE LIMIT IS SHARED. SEC allows ten requests a second per address.
Each worker's client is throttled to its share (the pipeline's 8/s divided
by the worker count), so N workers together never exceed what one did.

Everything a worker needs travels in a plain dict; everything it returns is
a plain dict of plain rows. Nothing that cannot be pickled crosses the
boundary, and the parent never holds more than one company's rows at a time.
"""
from __future__ import annotations

import os

_CLIENT = None
_EXCL = None


def _init(user_agent: str | None, rate_per_worker: float, exclusions: str | None,
          cache_dir: str | None) -> None:
    """Runs once in each worker process: one client, one exclusions table."""
    global _CLIENT, _EXCL
    from .config import SETTINGS
    from .edgar import EdgarClient
    from .exclusions import read_exclusions
    _CLIENT = EdgarClient(user_agent=user_agent, cache_dir=cache_dir)
    _CLIENT._limiter._min_interval = 1.0 / max(rate_per_worker, 0.5)
    _EXCL = read_exclusions(exclusions)


def walk_company(job: dict) -> dict:
    """job: cik, ticker, since, splits(bool). Returns rows + verdict, or
    an error string. Identical logic to the in-process walk it replaces."""
    from .config import SETTINGS
    from .history import build_history, mark_restated
    from .identity import peo_from_certification
    from .ledger import build_ledger
    from .outstanding import shares_outstanding
    from .series import denominator_series
    from .splits import fetch_splits

    client, excl = _CLIENT, _EXCL
    cik, tk = int(job["cik"]), job["ticker"]
    try:
        cert = peo_from_certification(client, cik)
        if not cert:
            return {"ticker": tk, "rows": [], "skipped": "no certification"}
        out = shares_outstanding(client, cik)
        led = build_ledger(client, cik, owner_name=cert.name,
                           share_classes=out.classes if out.ok else 0,
                           class_members=out.per_class,
                           exclude=excl.for_issuer(cik))
        if not led.owner_cik:
            return {"ticker": tk, "rows": [], "skipped": "no owner matched"}
        series = denominator_series(client, cik, since=job["since"])
        if not series.classes and out.per_class:
            series.classes = {"0000": out.per_class}
        sp = (fetch_splits(client, tk, SETTINGS.polygon_api_key)
              if job.get("splits") else None)
        hist = build_history(client, cik, led.owner_cik, led.mine,
                             series=series, splits=sp,
                             exclude=excl.for_issuer(cik), since=job["since"])
        mark_restated(hist.snapshots)
        last = hist.snapshots[-1].shares if hist.snapshots else None
        ok = (last is not None
              and abs(last - led.total) <= max(1.0, led.total * 0.001))
        rows = []
        for s_ in hist.snapshots:
            rows.append({
                "cik": cik, "ticker": tk, "ceo": cert.name,
                "owner_cik": led.owner_cik,
                "date": s_.date, "form": s_.form, "accession": s_.accession,
                "shares": int(s_.shares),
                "shares_split_adjusted": int(s_.adjusted),
                "outstanding": int(s_.outstanding) if s_.outstanding else "",
                "pct": round(s_.pct, 4) if s_.pct is not None else "",
                "traded": int(s_.traded) if s_.traded else "",
                "traded_value": (round(s_.traded_value, 2)
                                 if s_.traded_value else ""),
                "unpriced_rows": s_.unpriced or "",
                "unexplained": (int(s_.unexplained)
                                if abs(s_.unexplained) >= 1 else ""),
                "codes": s_.codes, "groups": s_.groups,
                "classes": s_.classes,
                "restated": "TRUE" if s_.restated else "",
                "matches_panel": "TRUE" if ok else "",
            })
        return {"ticker": tk, "rows": rows, "ok": ok}
    except Exception as exc:  # noqa: BLE001 -- one company never stops the walk
        return {"ticker": tk, "rows": [], "error": f"{type(exc).__name__}: {exc}"[:200]}


def run_pool(jobs: list, workers: int, user_agent: str | None,
             exclusions: str | None, cache_dir: str | None,
             tasks_per_child: int = 25, on_result=None):
    """Yield walk_company results as they complete, from a pool whose
    workers are recycled every `tasks_per_child` companies."""
    import multiprocessing as mp
    if workers <= 1:
        _init(user_agent, 8.0, exclusions, cache_dir)
        for j in jobs:
            r = walk_company(j)
            if on_result:
                on_result(r)
            yield r
        return
    ctx = mp.get_context("spawn")
    rate = 8.0 / workers
    with ctx.Pool(processes=workers, initializer=_init,
                  initargs=(user_agent, rate, exclusions, cache_dir),
                  maxtasksperchild=tasks_per_child) as pool:
        for r in pool.imap_unordered(walk_company, jobs, chunksize=1):
            if on_result:
                on_result(r)
            yield r
