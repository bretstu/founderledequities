"""Command line.

Four commands, and each one shows its working. v1's failures were all silent
-- a wrong insider, a walk that stopped early, a table excluded -- and every
one was caught by a human noticing a number looked wrong. So these print the
ledger line by line rather than only the answer.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import csv
import datetime
import shutil
import sys
import time

from .config import SETTINGS
from .edgar import EdgarClient
from .identity import peo_from_certification
from .ledger import build_ledger, is_partnership_unit
from .outstanding import shares_outstanding, jumped
from .exclusions import read_exclusions
from .ownership import build
from .panel import run_panel, write_csv, summarise, COLUMNS as PANEL_COLUMNS
from .universe import (fetch_members, write_universe, read_universe,
                       default_name)

COLUMNS = ["cik", "company", "ceo", "ceo_source", "owner_cik", "shares",
           "outstanding", "pct", "shares_as_of", "outstanding_as_of",
           "gap_days", "lines", "options", "converted", "share_classes",
           "filings_read", "settled", "confidence", "flags", "error"]


_CLIENTS: list = []   # every client built this process, so a run can sum stale feeds


def _client(args) -> EdgarClient:
    c = EdgarClient(user_agent=getattr(args, "user_agent", None))
    _CLIENTS.append(c)
    return c


def _stale_feeds() -> int:
    return sum(c.stale_served for c in _CLIENTS)


def rotate_checkpoint(checkpoint: str, prior: str, universe: str) -> bool:
    """Move a FINISHED checkpoint aside as the prior; leave an unfinished one.

    Finished means it holds a row for every member of the universe. A
    checkpoint short of that is a night that died, and resuming it is what
    checkpoints are for. Returns whether a rotation happened.
    """
    from .panel import _load
    if not os.path.exists(checkpoint):
        return False
    try:
        want = {m.cik for m in read_universe(universe)}
    except OSError:
        want = set()
    have = set(_load(checkpoint))
    if want and not want <= have:
        return False                     # unfinished: resume it
    os.replace(checkpoint, prior)
    return True


def _tick(i, n):
    sys.stdout.write(f"\r  reading filing {i}/{n}...")
    sys.stdout.flush()


def _clear():
    sys.stdout.write("\r" + " " * 42 + "\r")


# ----------------------------------------------------------------- ceo

def cmd_ceo(args) -> int:
    """Who the company says its chief executive is."""
    client = _client(args)
    cert = peo_from_certification(client, int(args.cik))
    if not cert:
        print("  no Section 302 certification found")
        if args.why:
            _why_no_cert(client, int(args.cik))
        else:
            print("  run again with --why to see which stage failed")
        return 1
    print(f"  {cert.name}")
    print(f"  from {cert.form} filed {cert.filing_date}, exhibit {cert.exhibit}")
    if cert.filings_skipped:
        print(f"  WARNING: {cert.filings_skipped} newer periodic filing(s) "
              f"yielded no certification, so this name may predate a change "
              f"of chief executive. Run again with --why to see them.")
    if cert.combined_certification:
        print("  note: one exhibit covered both officers; the PEO half was used")
    if cert.other_names_in_doc:
        print(f"  also named in that document: {', '.join(cert.other_names_in_doc)}")
    return 0


def _why_no_cert(client, cik: int) -> None:
    """Show each stage, because "not found" hides four different failures.

    The reader has to (1) find recent periodic filings, (2) list the
    documents in one, (3) recognise which is Exhibit 31.1, (4) pull a name
    out of it. Any of those can be the one that broke, and the verdict alone
    says nothing about which.
    """
    from .identity import (PERIODIC_FORMS, _pick_exhibits, _read_certification,
                           extract_names_from_certification, _plain_text)

    subs = client.submissions(cik)
    filings = [f for f in subs.get("_filings", []) if f.get("form") in PERIODIC_FORMS]
    filings.sort(key=lambda f: (f.get("filingDate") or ""), reverse=True)
    print(f"\n  1. periodic filings found: {len(filings)}")
    if not filings:
        print("     nothing to read -- the issuer files no 10-K or 10-Q under this CIK")
        return

    for f in filings[:3]:
        acc, form, when = (f.get("accessionNumber", ""), f.get("form"),
                           f.get("filingDate"))
        print(f"\n  {form} {when}  {acc}")
        try:
            index = client.filing_index(cik, acc)
        except Exception as exc:  # noqa: BLE001
            print(f"     2. could not list its documents: {exc}")
            continue
        items = index.get("directory", {}).get("item", [])
        print(f"     2. {len(items)} documents in the filing")
        picked = _pick_exhibits(index)
        if not picked:
            print("     3. none recognised as Exhibit 31.1. Documents were:")
            for it in items[:14]:
                print(f"          {(it.get('name') or '')[:52]:<54}"
                      f"{(it.get('type') or '')[:14]}")
            continue
        print(f"     3. recognised as a certification: "
              f"{', '.join(n for n, _ in picked[:4])}")
        for name, _t in picked[:2]:
            try:
                raw = client.get(
                    f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                    f"{acc.replace('-', '')}/{name}")
            except Exception as exc:  # noqa: BLE001
                print(f"     4. could not read {name}: {exc}")
                continue
            text = _plain_text(raw)
            names = extract_names_from_certification(text)
            print(f"     4. {name}: {len(text)} chars of text, "
                  f"names found: {names or 'NONE'}")
            if not names:
                snippet = " ".join(text[:300].split())
                print(f"        opens: {snippet[:220]}")


# -------------------------------------------------------------- ledger

def cmd_ledger(args) -> int:
    """Every line the insider holds, and where each was last stated."""
    client = _client(args)
    cik = int(args.cik)
    name = args.owner
    if not name and not args.owner_cik:
        cert = peo_from_certification(client, cik)
        if not cert:
            print("  no Section 302 certification; pass --owner")
            return 1
        name = cert.name
        print(f"  chief executive: {name}  ({cert.form} {cert.filing_date})")

    from .splits import fetch_splits
    from .config import SETTINGS
    _splits = fetch_splits(client, args.ticker or "", SETTINGS.polygon_api_key)
    if args.ticker:
        print(f"  splits    {_splits.describe()}"
              + (f"  ({_splits.note})" if not _splits.ok else ""))
    # The class count, from the company's own cover page. cmd_ledger calls
    # build_ledger directly rather than through ownership.build, so it has to
    # fetch this itself -- without it the single-class path never runs here
    # and the command disagrees with the panel.
    from .outstanding import shares_outstanding
    _out = shares_outstanding(client, cik)
    led = build_ledger(client, cik, owner_name=name, owner_cik=args.owner_cik,
                       max_filings=args.max_filings, max_search=args.max_search,
                       fast=args.fast, trace=args.trace, splits=_splits,
                       share_classes=_out.classes if _out.ok else 0,
                       class_members=_out.per_class,
                       exclude=read_exclusions(args.exclusions).for_issuer(cik),
                       on_progress=_tick)
    _clear()
    # Print what WAS learned before giving up. "nothing found" conflated
    # three different outcomes: the person was never located, they were
    # located but have no filings here, or they filed and hold nothing --
    # and only the last is a real answer worth publishing.
    if not led.groups:
        if not led.owner_cik:
            from .successor import find_predecessor
            pre = find_predecessor(client, cik, name)
            if pre.cik:
                print(f"  this issuer's insider history is under CIK {pre.cik} "
                      f"({pre.name})")
                print(f"  verified by finding {pre.matched_owner} among its insiders")
                print(f"  re-run with --cik {pre.cik}")
                return 1
            if pre.considered:
                print("  looked at the CIKs that transmitted its filings:")
                for c, nm, n in pre.considered:
                    print(f"    {c:<12}{nm[:38]:<40}{n} Section 16 filings")
            print(f"  {led.note or 'the insider was never located'}")
            print(f"  searched {led.searched} Form 3s of "
                  f"{led.issuer_s16} Section 16 filings")
            print("  run `insiders --cik ...` to see who was there")
            return 1
        if led.trace:
            print(f"\n  every row read, newest filing first (II* = not counted):\n")
            last = None
            for when, form, table, title, di, nature, sh, code, moved in led.trace:
                if when != last:
                    print(f"  {when}  {form}")
                    last = when
                amt = "footnoted" if sh != sh else f"{sh:,.0f}"
                where = f"{di} {nature}".strip()[:20]
                mv = f"{moved:+,.0f}" if moved else ""
                print(f"      {table:<4}{code or '-':<3}{title[:32]:<34}"
                      f"{where:<22}{mv:>15}{amt:>16}")
            print()
        forms = ", ".join(f"{k}x{v}" for k, v in sorted(led.forms_seen.items())) or "none"
        print(f"  insider   {led.owner_name}  (CIK {led.owner_cik})")
        print(f"  filings   {led.filings_read} read [{forms}]")
        print(f"  scope     {led.matched} of the issuer's {led.issuer_s16} "
              f"Section 16 filings are theirs")
        if led.other_issuers:
            print(f"  skipped   {led.other_issuers} filings that name a "
                  f"different issuer:")
            for c, n in sorted(led.issuers_seen.items(), key=lambda kv: -kv[1])[:8]:
                print(f"              CIK {c or '(none stated)':<12}{n} filings")
        if led.matched == 0:
            print("  they are an insider here but have filed nothing under "
                  "this issuer")
        else:
            print("  they filed, and reported no holdings -- which is an "
                  "answer, not a failure: this person owns nothing")
        if led.options:
            print(f"\n  NOT counted, because it is not issued stock of this "
                  f"issuer: {led.options:,.0f}")
            for title, amt in sorted(led.option_titles.items(),
                                     key=lambda kv: -kv[1])[:8]:
                print(f"    {amt:>16,.0f}   {title[:60]}")
            print("  a strike price means an option; anything without one is "
                  "issued equity\n  of some entity -- read the title to see "
                  "which")
        return 1

    if led.trace:
        print(f"\n  every row read, newest filing first "
              f"(II* = not counted):\n")
        last = None
        for when, form, table, title, di, nature, sh, code, moved in led.trace:
            if when != last:
                print(f"  {when}  {form}")
                last = when
            amt = "footnoted" if sh != sh else f"{sh:,.0f}"
            where = f"{di} {nature}".strip()[:20]
            mv = f"{moved:+,.0f}" if moved else ""
            print(f"      {table:<4}{code or '-':<3}{title[:32]:<34}"
                  f"{where:<22}{mv:>15}{amt:>16}")
        print()

    forms = ", ".join(f"{k}x{v}" for k, v in sorted(led.forms_seen.items()))
    print(f"  insider   {led.owner_name}  (CIK {led.owner_cik})")
    if led.match_score:
        note = f", next best {led.runner_up:.2f}" if led.runner_up else ""
        # A runner-up existing is normal -- a spouse or sibling who is also an
        # insider shares the surname. What matters is the MARGIN: Michael Dell
        # beats Susan Lieberman Dell 1.00 to 0.75, which is decisive, and
        # warning on it would teach the reader to ignore the warning.
        if led.match_score < 0.9 or led.margin < 0.15:
            note += "  <- too close to call, check the person"
        who = "officer" if led.officer else "NOT flagged as an officer"
        print(f"  matched   {led.match_score:.2f} against the certification, "
              f"{who}{note}")
    if led.tied:
        print(f"  TIED      {', '.join(led.tied)} matched equally well; "
              f"the one with more filings was used")
    print(f"  filings   {led.filings_read} read [{forms}]  "
          f"{led.first_filing} to {led.last_filing}")
    print(f"  scope     {led.matched} of the issuer's {led.issuer_s16} "
          f"Section 16 filings are theirs")
    if led.other_issuers:
        print(f"  skipped   {led.other_issuers} filings naming a different issuer: "
              + ", ".join(f"CIK {c or 'none'} x{n}" for c, n in
                          sorted(led.issuers_seen.items(), key=lambda kv: -kv[1])[:6]))
    if led.single_class:
        print("  classes   one, per the company's own cover page -- so every "
              "security\n            title is that class and none is read")
    elif led.classes:
        print(f"  classes   {', '.join(led.classes)}"
              f"  -- as the company names them")
    if led.excluded:
        print("  excluded  from the curated list -- the company itself says "
              "these are\n            not theirs:")
        for lab, (sh, why, src) in led.excluded.items():
            print(f"              {sh:>16,.0f}   {lab[:52]}")
            print(f"              {'':>16}   {why[:66]}")
            print(f"              {'':>16}   {src[:66]}")
    if led.unnamed_class:
        print(f"  excluded  {len(led.unnamed_class)} title(s) naming a class the "
              f"cover page does not list:")
        for t, v in sorted(led.unnamed_class.items(), key=lambda kv: -kv[1])[:5]:
            print(f"              {v:>16,.0f}   {t[:52]}")
    print(f"  ended     {led.source}")

    print(f"\n  {'line':<52}{'shares':>16}   last stated")
    for line in sorted(led.groups.values(), key=lambda l: -l.shares):
        tag = "" if line.table == "I" else "  [Table II]"
        print(f"    {line.label():<50}{line.shares:>16,.0f}   {line.as_of}{tag}")
    print(f"    {'':<50}{'-' * 16}")
    print(f"    {'common stock held':<50}{led.total:>16,.0f}")

    out = shares_outstanding(client, cik)
    if out.ok:
        print(f"\n  shares outstanding{'':<32}{out.shares:>16,.0f}   "
              f"{out.as_of}  {out.form}")
        if out.note:
            print(f"  {out.note}")
        print(f"  OWNS{'':<46}{led.total / out.shares * 100:>15.3f}%")
        moved, how = jumped(out.history)
        if moved:
            print(f"  denominator moved {how}")
    else:
        print(f"\n  {out.note}")

    if led.converted:
        print(f"\n  a convertible class is counted: "
              f"{', '.join(sorted(set(led.converted)))}")
        print("  1:1 for Meta's Class B; 1:1500 for Berkshire's. Confirm the ratio.")
    if led.options:
        print(f"\n  options and units, NOT counted{'':<20}{led.options:>16,.0f}")
        for title, amt in sorted(led.option_titles.items(),
                                 key=lambda kv: -kv[1])[:5]:
            print(f"    {amt:>16,.0f}   {title[:60]}")
    fl = led.flows
    if fl.sourced:
        print(f"\n  where the stake came from, over their whole filing history")
        for label, amt in [("already held at their Form 3", fl.opening),
                           ("bought on the open market", fl.bought),
                           ("granted by the company", fl.granted),
                           ("from options or units", fl.from_derivative),
                           ("gifted in", fl.gifted_in),
                           ("other", fl.other_in)]:
            if amt:
                print(f"    {amt:>16,.0f}   {label}")
        print(f"    {'':>16}   {'-'*34}")
        parts = []
        if fl.founded_share is not None and fl.opening:
            parts.append(f"{fl.founded_share:.1f}% already held")
        if fl.bought_share is not None:
            parts.append(f"{fl.bought_share:.1f}% bought")
        print(f"    {fl.sourced:>16,.0f}   in total"
              + (f" -- {', '.join(parts)}" if parts else ""))
        if not fl.opening:
            print(f"    {'':>16}   no Form 3 holdings were read, so anything "
                  f"held before\n    {'':>16}   they became an insider is "
                  f"missing here")
        for label, amt in [("sold", fl.sold), ("withheld or forfeited", fl.surrendered),
                           ("gifted away", fl.gifted_out)]:
            if amt:
                print(f"    {amt:>16,.0f}   {label}")
        print(f"\n  by code: {fl.tally()}")

    if led.partnership_units:
        # The title that set operating_partnership is often a small line the
        # display trims away, which makes a false positive impossible to see
        # from the sheet. Show it whatever its size.
        print(f"\n  counted as an operating partnership interest"
              f"{'':<8}{led.partnership_units:>13,.0f}")
        for title, amt in sorted(led.option_titles.items(), key=lambda kv: -kv[1]):
            if is_partnership_unit(re.sub(r"\s*\[strike[^\]]*\]", "", title)):
                print(f"    {amt:>16,.0f}   {title[:60]}")
    if led.blind:
        # These are holes in the total, not cosmetic noise.
        print(f"\n  {len(led.blind)} line(s) whose balance was ONLY ever given "
              f"as a footnote, so they are missing from the total:")
        for lab in led.blind[:6]:
            print(f"    {lab}")
    elif led.footnoted:
        print(f"\n  {len(led.footnoted)} footnoted balance(s), all on lines "
              f"stated numerically elsewhere -- nothing lost")
    return 0


# --------------------------------------------------------- outstanding

def cmd_outstanding(args) -> int:
    """The denominator, and the series it came from."""
    client = _client(args)
    out = shares_outstanding(client, int(args.cik))
    if not out.ok:
        print(f"  {out.note}")
        return 1
    print(f"  {out.shares:,.0f}   as of {out.as_of}   {out.form}  {out.accession}")
    if out.note:
        print(f"  {out.note}")
    if out.per_class:
        print("\n  by class, as the company names them:")
        for name, v in sorted(out.per_class.items(), key=lambda kv: -kv[1]):
            print(f"    {name[:46]:<48}{v:>18,.0f}")
    print("\n  reported history:")
    for when, val, form in out.history:
        print(f"    {when}  {val:>18,.0f}   {form}")
    moved, how = jumped(out.history)
    if moved:
        print(f"\n  moved {how}")
        print("  a rise is an issuance or a conversion; a fall is buybacks. "
              "Either can also be a misread tag.")
    return 0


# ----------------------------------------------------------------- run

def cmd_run(args) -> int:
    """One or more companies, end to end."""
    client = _client(args)
    ciks = [int(c.strip()) for c in args.ciks.split(",") if c.strip()]
    rows = []
    for cik in ciks:
        rec = build(client, cik, exclusions=read_exclusions(args.exclusions),
                    on_progress=_tick)
        _clear()
        rows.append(rec)
        if rec.error:
            print(f"  {cik:<12} ERROR  {rec.error}")
            continue
        pct = f"{rec.pct:.3f}%" if rec.pct is not None else "n/a"
        print(f"  {cik:<12}{pct:>10}  {rec.confidence:<7}{rec.ceo[:26]:<28}"
              f"{rec.shares:>15,.0f} / {rec.outstanding or 0:>16,.0f}")
        for lvl, f in (rec.graded or [("note", x) for x in rec.flags]):
            mark = {"problem": "!", "caution": "·", "note": " "}.get(lvl, "·")
            print(f"  {'':<12}  {mark} {f}")

    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r.as_dict())
        print(f"\n  wrote {len(rows)} rows -> {args.out}")
    return 0


# --------------------------------------------------------------- index

def cmd_index(args) -> int:
    """Snapshot S&P 500 membership to a dated file."""
    client = _client(args)
    if getattr(args, "min_cap", None):
        return cmd_market_universe(args)
    if args.all:
        from .universe import fetch_all_tickers
        members = fetch_all_tickers(client)
        if not members:
            print("  could not read the SEC ticker file")
            return 1
        print(f"  {len(members)} registrants with tickers, from the SEC's "
              f"own file")
    else:
        members = fetch_members(client)
        if not members:
            print("  could not parse the membership table")
            return 1
    path = args.out or default_name()
    write_universe(members, path)
    print(f"  {len(members)} companies -> {path}")
    print("  deduplicated by CIK, so a dual-class filer counts once")
    return 0


# --------------------------------------------------------------- panel

def _exclusive(path: str):
    """Hold an exclusive lock on <path>.lock for the life of a long run, or
    exit naming the holder. Two panels on one checkpoint, or two walks on
    one output file, corrupt each other -- and the day nine stopped runs
    turned out to be alive and writing, the corruption was invisible until
    a ps. The lock makes a second run impossible however it is launched:
    by hand, by wrapper, by a forgotten terminal. Released by the OS the
    instant the process ends, so a crash never leaves a stale lock."""
    import fcntl
    lock_path = path + ".lock"
    os.makedirs(os.path.dirname(lock_path) or ".", exist_ok=True)
    fh = open(lock_path, "a+")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.seek(0)
        holder = fh.read().strip() or "unknown pid"
        print(f"another run holds {lock_path} (pid {holder}); "
              f"stop it first: kill {holder}", file=sys.stderr)
        raise SystemExit(2)
    fh.seek(0); fh.truncate(); fh.write(str(os.getpid())); fh.flush()
    return fh          # keep the handle alive; dropping it releases the lock


def cmd_panel(args) -> int:
    _lock = _exclusive(args.checkpoint)   # noqa: F841 -- held until return
    """Run the universe, resuming what is already done."""
    client = _client(args)
    members = read_universe(args.universe)
    if args.tickers:
        want = {t.strip().upper().replace(".", "-")
                for t in args.tickers.split(",") if t.strip()}
        members = [m for m in members if m.ticker.upper() in want]
        missing = want - {m.ticker.upper() for m in members}
        if missing:
            print(f"  not in this universe: {', '.join(sorted(missing))}")
    if args.ciks:
        want = {int(c) for c in args.ciks.split(",") if c.strip()}
        members = [m for m in members if m.cik in want]
    if args.limit:
        # Deliberately the first N in ticker order, not a random sample. v1
        # had --sample and --seed, and their runs could not be compared with
        # each other; the same slice every time can be.
        members = members[:args.limit]
    if not members:
        print("  nothing to run")
        return 1
    print(f"  {len(members)} companies from {args.universe}")
    print(f"  checkpoint {args.checkpoint}"
          + (f"  (redo: {args.redo})" if args.redo != "none" else ""))

    def num(v):
        return f"{v:,.0f}" if isinstance(v, (int, float)) else "--"

    def on_filing(i, n, m, a, b):
        # Some insiders have four filings and some have 778, so a bare
        # company counter looks stalled on the big ones.
        sys.stdout.write(f"\r   {i:>4}/{n}  {m.ticker[:6]:<7} "
                         f"reading filing {a}/{b}...".ljust(74))
        sys.stdout.flush()

    def row_done(i, n, row, resumed):
        sys.stdout.write("\r" + " " * 74 + "\r")
        pct = row.get("pct")
        mark = "·" if resumed else " "
        shown = f"{pct:.3f}%" if isinstance(pct, (int, float)) else "  --  "
        print(f"  {mark}{i:>4}/{n}  {(row.get('ticker') or '')[:6]:<7}"
              f"{shown:>9}  {(row.get('confidence') or '')[:6]:<7}"
              f"{num(row.get('shares')):>15} / {num(row.get('outstanding')):>16}"
              f"  {(row.get('ceo') or row.get('error') or '')[:34]}"
              # The certification names a person; the filings name whoever
              # actually filed. When those differ, show it -- a line reading
              # "Brian Armstrong -> Brian Armstrong Living Trust" needs no
              # explanation, and 500 of them can be skimmed in a minute.
              + (f"  -> {row.get('owner_name')}"
                 if row.get("owner_name") and not row.get("is_officer") else ""))

    try:
        from .panel import _load as _load_rows
        prior_path = getattr(args, "prior", None)
        prior = _load_rows(prior_path) if prior_path else {}
        if prior:
            print(f"  prior rows: {len(prior)} from {prior_path} -- a company "
                  f"whose feeds show nothing new keeps its row")
        excl = read_exclusions(args.exclusions)
        n_add = sum(1 for es in excl.by_cik.values() for e in es if e.is_addition)
        if n_add:
            print(f"  {n_add} supplement(s) in {excl.path} -- shares a filer states in a remark, injected as table lines")
        rows = run_panel(client, members, args.checkpoint, redo=args.redo,
                         exclusions=excl,
                         on_row=row_done, on_filing=on_filing,
                         workers=max(1, int(getattr(args, "workers", 1) or 1)),
                         prior=prior)
    except KeyboardInterrupt:
        _clear()
        print("  interrupted; the checkpoint keeps every finished company")
        return 130
    write_csv(rows, args.out)
    s = summarise(rows)
    print(f"\n  {s['with_a_figure']} of {s['total']} produced a figure"
          f"  ({s['errors']} errors, {s['unsettled']} did not settle)")
    print("  confidence: " + ", ".join(f"{k} {v}" for k, v in
                                       sorted(s["confidence"].items())))
    if s["flags"]:
        print("  most common flags:")
        for f, n in s["flags"][:8]:
            print(f"    {n:>4}  {f}")
    print(f"\n  wrote {args.out}")
    print("  every row carries form4_url and cover_url -- checking one means "
          "opening two filings")
    return 0


# ------------------------------------------------------------ insiders



def _filings_for(client, issuer_cik: int, owner_cik: str):
    """That person's filings for this issuer, newest first."""
    from .ledger import SECTION16
    subs = client.submissions(issuer_cik)
    theirs = client.submissions(int(owner_cik)) if owner_cik else {}
    accs = {f.get("accessionNumber") for f in theirs.get("_filings", [])}
    out = [f for f in subs.get("_filings", [])
           if f.get("form") in SECTION16
           and (not accs or f.get("accessionNumber") in accs)]
    out.sort(key=lambda f: (f.get("filingDate") or ""), reverse=True)
    return out




def cmd_history(args) -> int:
    _lock = _exclusive(args.out)          # noqa: F841 -- held until return
    """A snapshot after every filing, for each company in the universe.

    The same settling rule as the panel, walked oldest-first instead of
    newest-first -- so the LAST snapshot must equal the panel's figure. That
    is reported per company as `matches_panel`, because a series that ends
    somewhere else means one of the two is wrong.
    """
    from .history import build_history
    from .series import denominator_series
    from .ledger import build_ledger
    from .splits import fetch_splits

    if not args.splits:
        print("  note: --splits is off. Share counts stay in the basis of "
              "their own day, and a percentage computed between a split and "
              "the cover page that restates the count will be wrong by the "
              "split factor (Nvidia's 3.5% read as 35% for eleven weeks "
              "of 2024).")

    client = _client(args)
    excl = read_exclusions(args.exclusions)
    members = read_universe(args.universe)
    if args.tickers:
        want = {t.strip().upper() for t in args.tickers.split(",")}
        members = [m for m in members if m.ticker.upper() in want]
    if args.limit:
        members = members[:args.limit]

    # A COMPANY THAT HAS NOT FILED HAS NOTHING NEW TO SAY.
    #
    # Walking all five hundred takes hours, and on a given night almost none
    # of them have filed. So the newest Section 16 accession per company is
    # remembered; if it has not moved, yesterday's rows are carried over
    # verbatim and the walk is skipped. One cheap request replaces the whole
    # rebuild, which is what makes a nightly refresh possible at all.
    #
    # AND THE NEWEST COVER PAGE. A 10-Q moves the count and so adds a point
    # (history.add_cover_points) with no Form 4 from the person; keyed on
    # Section 16 alone, a company whose chief executive had not filed was
    # carried for months with a stale last point. The key carries both.
    prior_rows: dict = {}
    prior_state: dict = {}
    if args.reuse:
        try:
            with open(args.reuse, encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh):
                    prior_rows.setdefault(row["ticker"], []).append(row)
        except FileNotFoundError:
            pass
        try:
            with open(args.state, encoding="utf-8") as fh:
                prior_state = json.load(fh)
        except (FileNotFoundError, ValueError):
            pass
        if prior_rows:
            print(f"  reuse: {len(prior_rows)} companies in {args.reuse}")

    new_state: dict = {}
    reused = 0
    agree = disagree = 0
    walked = failed = 0
    from .history import mark_restated_rows, COVER_FORMS
    from .ledger import SECTION16
    from .walk import run_pool
    key_forms = SECTION16 + COVER_FORMS

    cols = ["cik", "ticker", "ceo", "owner_cik", "date", "form", "accession",
            "shares", "shares_split_adjusted", "outstanding", "pct",
            "traded", "traded_value", "unpriced_rows", "unexplained",
            "codes", "groups", "classes", "restated", "matches_panel"]
    n_rows = 0
    tickers_out: set = set()

    # THE FILE IS WRITTEN AS COMPANIES COMPLETE, NOT AT THE END. The parent
    # holds one company's rows at a time; the write-time restated marking
    # runs per company (it groups by person anyway). Carried rows and
    # walked rows go through the same door.
    fh = open(args.out, "w", newline="", encoding="utf-8-sig")
    w = csv.DictWriter(fh, fieldnames=cols)
    w.writeheader()

    def emit(rows: list) -> None:
        nonlocal n_rows
        if not rows:
            return
        mark_restated_rows(rows)
        for r in rows:
            w.writerow({k: " ".join(str(r.get(k, "")).split()) for k in cols})
        n_rows += len(rows)
        tickers_out.add(rows[0]["ticker"])
        fh.flush()

    # 1 -- decide reuse for every company (cheap: one index each), emit the
    #      carried rows now, and queue the rest for the workers
    jobs = []
    for i, m in enumerate(members, 1):
        sys.stdout.write(f"\r  {i}/{len(members)} {m.ticker}  checking...".ljust(52))
        sys.stdout.flush()
        try:
            if args.reuse and m.ticker in prior_rows:
                subs = client.submissions(int(m.cik))
                latest = ""
                for f in subs.get("_filings", []):
                    if f.get("form") in key_forms:
                        acc = f.get("accessionNumber") or ""
                        when = f.get("filingDate") or ""
                        if (when, acc) > (latest[:10], latest[11:]):
                            latest = f"{when} {acc}"
                if latest and prior_state.get(m.ticker) == latest:
                    emit(prior_rows[m.ticker])
                    new_state[m.ticker] = latest
                    reused += 1
                    if prior_rows[m.ticker][-1].get("matches_panel") == "TRUE":
                        agree += 1
                    else:
                        disagree += 1
                    continue
                new_state[m.ticker] = latest
        except Exception:  # noqa: BLE001
            pass
        jobs.append({"cik": int(m.cik), "ticker": m.ticker,
                     "since": args.since, "splits": bool(args.splits)})
    _clear()

    # 2 -- walk the rest in recycled worker processes
    workers = max(1, int(getattr(args, "workers", 1) or 1))
    if jobs:
        print(f"  walking {len(jobs)} companies in {workers} worker(s), "
              f"recycled every 25")
        done = 0
        for res in run_pool(jobs, workers,
                            user_agent=getattr(args, "user_agent", None),
                            exclusions=args.exclusions,
                            cache_dir=SETTINGS.cache_dir):
            done += 1
            if res.get("rows"):
                sys.stdout.write(f"\r  {done}/{len(jobs)} {res['ticker']}  ok"
                                 .ljust(44)[:44])
                sys.stdout.flush()
                emit(res["rows"])
                walked += 1
                agree, disagree = ((agree + 1, disagree) if res.get("ok")
                                   else (agree, disagree + 1))
            else:
                # a company that produced nothing says why, on a line that
                # STAYS -- the first rehearsal printed reasons only on the
                # transient ticker line and "0 snapshots" arrived unexplained
                why = (res.get("skipped") or res.get("error")
                       or "walked but produced no snapshots")
                print(f"\r  {done}/{len(jobs)} {res['ticker']}  -- {why}"
                      .ljust(64))
                if res.get("error"):
                    failed += 1
    fh.close()
    _clear()
    if args.reuse:
        print(f"  {reused} unchanged (rows carried over), "
              f"{len(members) - reused} rewalked")
        try:
            with open(args.state, "w", encoding="utf-8") as fh:
                json.dump(new_state, fh, indent=0, sort_keys=True)
        except OSError:
            pass

    print(f"  {n_rows:,} snapshots across {len(tickers_out)} companies since {args.since}")
    print(f"  {agree} end on the panel's figure, {disagree} do not"
          + (f"; {failed} failed" if failed else ""))
    print(f"  wrote {args.out}")
    return 0


PRICE_STORE = "price-history"   # one <TICKER>.csv per ticker, date,close

def event_row(e) -> list:
    """One events.csv row, in EVENT_COLUMNS order. A column added to the
    header alone once shifted every later field one to the left, and the
    page read the residue as the holding; the header and this list are
    checked against each other in the tests."""
    return [
        e.ticker, e.issuer_cik, e.ceo, e.owner_cik, e.filed, e.traded,
        e.code, e.label, f"{e.shares:.0f}",
        "" if e.value is None else f"{e.value:.2f}",
        "" if e.avg_price is None else f"{e.avg_price:.4f}",
        "" if e.pct_of_holding is None else f"{e.pct_of_holding:.4f}",
        "" if e.pct_approx is None else f"{e.pct_approx:.4f}",
        "" if e.net_change is None else f"{e.net_change:.0f}",
        "" if e.day_net is None else f"{e.day_net:.0f}",
        "" if e.holding_after is None else f"{e.holding_after:.0f}",
        "" if e.outstanding is None else f"{e.outstanding:.0f}",
        "" if e.pct_after is None else f"{e.pct_after:.4f}",
        "" if e.residue is None else f"{e.residue:.0f}",
        e.plan, e.other_codes, e.rows, e.unpriced_rows, e.securities,
        e.direct, e.form, e.accession, e.price_flag, e.url,
        e.registered, "1" if e.pre_registration else "",
        "" if e.avg_price_adjusted is None else f"{e.avg_price_adjusted:.4f}",
        e.traded_from, "1" if e.first_buy else ""]


EVENT_COLUMNS = ["ticker", "cik", "ceo", "owner_cik", "filed", "traded",
                 "code", "label", "shares", "value", "avg_price",
                 "pct_of_holding", "pct_approx", "net_change", "day_net", "holding_after", "outstanding", "pct_after", "residue",
                 "plan", "other_codes", "rows", "unpriced_rows", "securities",
                 "direct", "form", "accession", "price_flag", "url",
                 "registered", "pre_ipo", "avg_price_adjusted", "traded_from", "first_buy"]


def cmd_events(args) -> int:
    """What each chief executive actually bought and sold, one row per
    filing and code (see events.py: the filing is the unit the position
    is reported at).

    The trade comes from the filing and the position comes from history, so
    this runs AFTER history in the nightly and reads the file it wrote. Every
    filing it needs is already cached by the panel, which makes it the
    cheapest stage in the run.
    """
    import csv as _csv
    from .events import build_events, flag_prices, load_history
    from .exclusions import read_exclusions

    client = _client(args)
    excl = read_exclusions(getattr(args, "exclusions", None))
    try:
        history = load_history(args.history)
    except FileNotFoundError:
        history = {}
        print(f"  no history at {args.history} -- position columns will be "
              f"empty; run the history stage first")

    with open(args.panel, encoding="utf-8-sig") as fh:
        panel = [r for r in _csv.DictReader(fh)]
    if args.tickers:
        want = {t.strip().upper() for t in args.tickers.split(",") if t.strip()}
        panel = [r for r in panel if (r.get("ticker") or "").upper() in want]

    out, failed = [], 0
    for i, r in enumerate(panel, 1):
        cik = int(r.get("cik") or 0)
        owner = (r.get("owner_cik") or "").strip()
        if not cik or not owner:
            continue
        try:
            out += build_events(
                client, cik, owner, r.get("ticker") or "", r.get("ceo") or "",
                since=args.since, history=history,
                exclude=excl.for_issuer(cik))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  {r.get('ticker')}: {type(exc).__name__}: {exc}"[:110])
        if i % 50 == 0:
            print(f"  {i}/{len(panel)}  {len(out):,} events", flush=True)

    flag_prices(out)
    out.sort(key=lambda e: (e.filed, e.ticker, e.traded), reverse=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = _csv.writer(fh)
        w.writerow(EVENT_COLUMNS)
        for e in out:
            w.writerow(event_row(e))

    buys = sum(1 for e in out if e.buy)
    flagged = sum(1 for e in out if e.residue)
    unjoined = sum(1 for e in out if e.holding_after is not None and e.net_change is None)
    spans = sum(1 for e in out if e.traded_from and e.traded_from != e.traded)
    print(f"  {len(out):,} events across {len(panel)} companies"
          f"  ({failed} failed); {spans:,} span more than one day")
    print(f"  {buys:,} purchases, {len(out) - buys:,} sales;"
          f" {flagged:,} on days history could not fully explain;"
          f" {unjoined:,} whose filing day has no point in the record")
    print(f"  wrote {args.out}")
    return 0


def cmd_prices(args) -> int:
    """One request for the whole market's closes, written beside the panel.

    The dashboard multiplies shares by these to show stake values. Every
    price carries the trading day it belongs to, and a ticker Polygon does
    not return simply has no value on the site -- never an estimate.
    """
    from .prices import fetch_prices

    client = _client(args)
    tickers = []
    with open(args.panel, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            t = (row.get("ticker") or "").strip()
            if t:
                tickers.append(t)
    got = fetch_prices(client, tickers, SETTINGS.polygon_api_key,
                       date=args.date)
    if not got.ok:
        print(f"  no prices: {got.note}")
        return 1
    with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "close", "as_of"])
        for t in tickers:
            if t in got.by_ticker:
                w.writerow([t, f"{got.by_ticker[t]:.4f}", got.as_of])
    print(f"  {got.matched} of {len(tickers)} tickers priced "
          f"at the {got.as_of} close")
    if got.missing:
        print(f"  no price for: {', '.join(got.missing[:12])}"
              + (f" and {len(got.missing)-12} more" if len(got.missing) > 12 else ""))
    print(f"  wrote {args.out}")

    # THE SAME CLOSES KEEP THE DAILY STORE CURRENT. One request a night
    # already carries every ticker's close; appending it here is what lets
    # the price chart and the performance index share one record without
    # a per-ticker fetch. A ticker whose close moved more than 2x on the
    # day is re-asked in full: a split the store has not been told about
    # looks exactly like that, and the feed knows which it was.
    store = getattr(args, "store", None) or PRICE_STORE
    if os.path.isdir(store):
        from .dailies import append_day, fetch_history, merge, read_one, write_one
        # the benchmarks are not in the panel; the store carries them
        for_store = list(tickers) + [b for b in ("SPY", "RSP") if b not in tickers]
        appended, suspect, refetched = 0, [], []
        for t in for_store:
            close = got.by_ticker.get(t) if t in got.by_ticker else got.all_closes.get(t)
            if close is None:
                continue
            series = read_one(store, t)
            if not series:
                continue                 # not backfilled yet; the weekly refresh will
            if append_day(series, got.as_of, close):
                suspect.append(t)
                if SETTINGS.polygon_api_key:
                    fresh, _note = fetch_history(client, t, SETTINGS.polygon_api_key)
                    if fresh:
                        series = merge(series, fresh)
                        refetched.append(t)
            write_one(store, t, series)
            appended += 1
        print(f"  price store: {got.as_of} appended to {appended} series"
              + (f"; re-asked {len(refetched)} after a >2x move: "
                 + ", ".join(refetched[:8]) if refetched else "")
              + (f"; could not re-ask: {', '.join(x for x in suspect if x not in refetched)}"
                 if len(suspect) > len(refetched) else ""))
    return 0


def edge_confidence(panel_path: str, history_path: str,
                    size: float = 0.5) -> int:
    """Downgrade a company whose NEWEST filing does not reconcile.

    THE ONE PLACE A READER COULD BE MISLED WITHOUT WARNING.

    A partial filing -- lawful under Form 4's per-line rules, naming only
    some of a person's vehicles -- understates the position until the next
    filing completes it. Everywhere in the record this is caught: the
    arithmetic leaves a residue in `unexplained`, mark_restated pairs the
    drop with its reversal, and the site excludes marked rows from every
    summary.

    Everywhere except the trailing edge. The newest filing has no successor
    yet, so nothing can distinguish "reported partially" from "genuinely
    sold" -- mark_restated deliberately refuses to guess, and the headline
    figure is published as filed. That is the honest choice for the NUMBER.
    It is not, by itself, honest about the CONFIDENCE: the row was reading
    `high` while its own arithmetic said a large balance change had no
    transaction behind it.

    So: a residue on the last snapshot worth at least `size` of the position
    caps confidence at `medium` and says why, in the reader's language. A
    row already `low` stays `low` -- this never raises anything.

    Runs after the history stage and before the atomic publish, so the panel
    and the history that judged it are published together or not at all.
    """
    from .history import COVER_FORMS
    try:
        with open(history_path, encoding="utf-8-sig", newline="") as fh:
            last = {}
            for r in csv.DictReader(fh):
                # THE PERSON'S LAST FILING. A cover-page point after it
                # carries no residue by construction; judged on that row the
                # cap would never fire again once a 10-Q followed the filing.
                if (r.get("form") or "") in COVER_FORMS:
                    continue
                last[r["ticker"]] = r
    except OSError:
        return 0

    flagged = {}
    for tk, r in last.items():
        try:
            u = float(r.get("unexplained") or 0)
            sh = float(r.get("shares") or 0)
        except ValueError:
            continue
        # only a DROP misleads: an unreconciled rise overstates nothing the
        # reader is being asked to trust, and reads as the award it usually is
        if u < 0 and abs(u) >= size * max(sh + abs(u), 1.0):
            flagged[tk] = abs(u)
    if not flagged:
        return 0

    try:
        with open(panel_path, encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            cols = reader.fieldnames or []
            rows = list(reader)
    except OSError:
        return 0

    note = ("the newest filing reports a balance far below the last with no "
            "transaction to explain it -- filings like this are usually "
            "partial, naming only some vehicles; shown as filed")
    hit = 0
    for row in rows:
        if row.get("ticker") not in flagged:
            continue
        hit += 1
        if row.get("confidence") == "high":
            row["confidence"] = "medium"
        cautions = row.get("cautions") or ""
        row["cautions"] = f"{cautions}|{note}" if cautions else note
    if hit:
        tmp = panel_path + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp, panel_path)
    return hit


def _has_events(client, ticker: str) -> bool:
    from .dailies import symbol_spans
    return bool(symbol_spans(client, ticker, SETTINGS.polygon_api_key))


def cmd_perf(args) -> int:
    """Refresh the daily price store for every ticker, then cut perf.csv.

    THE STORE IS THE MECHANISM. One request per ticker, every ticker in
    the panel plus the two benchmarks, five years of adjusted daily closes
    (or whatever the plan returns); days older than the plan's window are
    preserved from the stored file and rescaled if a split restated the
    overlap. perf.csv is the month-end close of each series; the site
    build cuts it to the chart's cohort, and the company page reads the
    daily file for its price chart.

    Weekly is enough: the nightly `prices` stage appends each day's close
    to the same files, so between refreshes the store is one day behind
    at most.
    """
    from .dailies import fetch_history, merge, read_store, write_store
    from .perf import (apply_floors, build_perf,
                       listing_month, write_perf)

    if not SETTINGS.polygon_api_key:
        print("  no price API key; the price store and perf.csv not written")
        return 0
    tickers = []
    try:
        with open(args.panel, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                t = (row.get("ticker") or "").strip().upper()
                if t and t not in tickers:
                    tickers.append(t)
    except OSError:
        print(f"  {args.panel} missing; run the panel stage first")
        return 1
    only = {t.strip().upper() for t in (getattr(args, "only", None) or "").split(",") if t.strip()}
    if only:
        tickers = [t for t in tickers if t in only]
    store = getattr(args, "store", None) or PRICE_STORE
    client = _client(args)
    stored = read_store(store)
    todo = ["SPY", "RSP"] + tickers
    fresh, missing, seams, by_events, refused = {}, [], [], set(), []
    for i, tk in enumerate(todo, 1):
        sys.stdout.write(f"\r  prices {i}/{len(todo)} {tk}...      ")
        sys.stdout.flush()
        # THE ENTITY'S HISTORY, ACROSS ITS SYMBOLS (dailies.fetch_history).
        # This replaced a hand-kept table of former tickers (XYZ was SQ)
        # and, for entities the feed knows, the list_date floor below: the
        # symbol events say both what to fetch and from when.
        # A REFUSAL IS A MISSING DAY, NOT A STOPPED RUN. Polygon refusing a
        # ticker (a rate cap, a plan limit, an outage) keeps yesterday's
        # series for it and moves on; the count of refusals is printed so
        # a vendor problem is seen the next morning, not felt as a hang.
        try:
            pts, note = fetch_history(client, tk, SETTINGS.polygon_api_key)
            has_ev = bool(pts) and _has_events(client, tk)
        except Exception as e:  # noqa: BLE001 -- the vendor's refusal, not ours
            refused.append(f"{tk}: {str(e)[:60]}")
            pts, note, has_ev = None, "", False
        if note:
            seams.append(note)
        if has_ev:
            by_events.add(tk)
        if pts:
            # a series rebuilt from the entity's own symbols replaces what
            # was stored under the symbol; a stranger's years must not be
            # preserved as "older than the fetch" (see merge)
            fresh[tk] = merge(stored.get(tk, []), pts) if tk not in by_events else pts
        else:
            missing.append(tk)
    _clear()
    if refused:
        print(f"  VENDOR REFUSED {len(refused)} of {len(todo)} tickers (yesterday's series kept): "
              + "; ".join(refused[:3]) + (" ..." if len(refused) > 3 else ""))
    if seams:
        print("  seams to look at: " + "; ".join(seams[:6]))
    # NO PRICE BEFORE THIS SECURITY TRADED UNDER THE SYMBOL. For an entity
    # the events feed knows, its first symbol's date is that floor. For the
    # rest, the vendor's per-security list_date (see perf.listing_month
    # for why not EDGAR's registration date).
    floors, cut = {}, []
    for tk in fresh:
        if tk in ("SPY", "RSP") or tk in by_events:
            continue
        fl = listing_month(client, tk, SETTINGS.polygon_api_key)
        if fl:
            floors[tk] = fl
            gone = sum(1 for p in fresh[tk] if p[0] < fl)
            if gone:
                cut.append(f"{tk} ({gone} days before {fl})")
    fresh = apply_floors(fresh, floors)
    if cut:
        print(f"  dropped price history from before the symbol's listing for {len(cut)}: "
              + ", ".join(cut[:8]) + (" ..." if len(cut) > 8 else ""))
    # tickers no longer in the panel leave the store with it, unless this
    # was a partial run
    keep = fresh if not only else {**stored, **fresh}
    n = write_store(store, keep)
    days = sum(len(v) for v in keep.values())
    print(f"  price store: {n} tickers, {days:,} daily closes -> {store}/")
    if missing:
        print(f"  no history for: {', '.join(missing[:12])}"
              + (" ..." if len(missing) > 12 else ""))
    perf = build_perf(keep, [t for t in keep if t not in ("SPY", "RSP")])
    rows = write_perf(perf, args.out)
    print(f"  {len(perf.series)} tickers, {rows} month-end closes -> {args.out}")
    if perf.note:
        print(f"  NOTE: {perf.note}")
    return 0


def cmd_market_universe(args) -> int:
    """The market-cap universe: a dated snapshot by written rules.

    Writes three files under universe/: the members list (same columns
    as the S&P file, so every other stage runs on it unchanged), the
    evidence for every registrant considered, and the review file -- the
    disagree/unsized rows a human reads before the snapshot is trusted.
    """
    from .market_universe import (build_snapshot, load_prior,
                                  write_snapshot)
    client = _client(args)
    today = datetime.date.today().isoformat()
    stem = args.out or f"universe/universe-{today}.csv"
    if not stem.endswith(".csv"):
        stem += ".csv"
    evidence = stem[:-4] + "-evidence.csv"
    review = stem[:-4] + "-review.csv"
    prior = load_prior(args.prior) if args.prior else {}
    if args.prior:
        print(f"  prior snapshot: {len(prior)} members from {args.prior}")
    if not SETTINGS.polygon_api_key:
        print("  no POLYGON_API_KEY: vendor market caps unavailable; "
              "sizing will lean on SEC counts alone", file=sys.stderr)

    def _p(i, n, tk):
        if i % 25 == 0 or i == n:
            sys.stdout.write(f"\r  universe {i:,}/{n:,} {tk:8}")
            sys.stdout.flush()
    checkpoint = os.path.join("_staging", f"universe-{today}.jsonl")
    if os.path.exists(checkpoint):
        print(f"  resuming from {checkpoint}")
    snap = build_snapshot(client, SETTINGS.polygon_api_key,
                          entry=args.min_cap, exit_=args.exit_cap,
                          prior=prior, snapshot=today, limit=args.limit,
                          on_step=_p, checkpoint=checkpoint)
    print()
    n_members, n_review = write_snapshot(snap, stem, evidence, review)
    from .market_universe import write_page
    page = write_page(stem, evidence, today, "about.html", "universe.html")
    by = {}
    for r in snap.rows:
        by[r.status.split(":")[0]] = by.get(r.status.split(":")[0], 0) + 1
    print(f"  {len(snap.rows):,} registrants considered: "
          + ", ".join(f"{k} {v:,}" for k, v in sorted(by.items())))
    print(f"  {n_members:,} members at >= ${args.min_cap:,.0f} "
          f"(exit below ${args.exit_cap:,.0f} after two snapshots)")
    print(f"  -> {stem}")
    print(f"  -> {evidence}  (every registrant, with both measures)")
    print(f"  -> {review}  ({n_review:,} rows for a human to read)")
    if page:
        print(f"  -> {page}  (the published list: every member and the rules)")
    return 0


def cmd_refresh(args) -> int:
    """The nightly, wrapped so that EVERY way it ends is reported.

    A DEAD-MAN'S SWITCH WITH BOTH HALVES. The heartbeat used to ping on
    success and on one kind of failure; a panel that failed, a gate that
    refused, an exception, a hang -- each returned or died without a word,
    and the monitor would have noticed only by the silence. Now: /start
    when the run begins (a hang is "started, never finished"), and the
    exit code when it ends, whatever the path, with the tail of the log
    as the body so the alert says why. By-hand runs stay silent: the URL
    lives in the service unit, not in .env.
    """
    log = _logger(args.dir)
    _heartbeat(log, "start")
    try:
        code = _refresh(args, log)
    except BaseException as exc:  # noqa: BLE001 - report, then re-raise
        log(f"FAILED refresh: {exc.__class__.__name__}: {exc}")
        _heartbeat(log, 1, _log_tail(args.dir))
        raise
    _heartbeat(log, code or 0, _log_tail(args.dir))
    return code


def _logger(live: str):
    def log(msg):
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{stamp}] {msg}"
        print(line, flush=True)
        try:
            with open(os.path.join(live, "refresh.log"), "a",
                      encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass
    return log


def _log_tail(live: str, n: int = 40) -> str:
    try:
        with open(os.path.join(live, "refresh.log"), encoding="utf-8") as fh:
            return "".join(fh.readlines()[-n:])
    except OSError:
        return ""


def _refresh(args, log) -> int:
    """One command, run by a timer, that publishes only if the data is sane.

    The stages are the same ones run by hand all along -- panel, diff,
    history, prices, founders -- but with three properties a nightly job
    needs and a person at a keyboard does not:

    NOTHING IS OVERWRITTEN UNTIL EVERYTHING SUCCEEDS. Work happens in a
    staging directory and is moved into place at the end, one atomic rename
    per file. A run that dies halfway leaves yesterday's site untouched,
    rather than serving a half-written CSV -- which nearly happened while
    reading founders.csv mid-run.

    THE ANCHORS ARE A GATE, NOT A REPORT. The nine holdings reconciled
    against proxies and outside data are checked before publishing. If one
    of them moves, the run refuses to publish and says so. A rule change
    that quietly breaks Musk should never reach the site at three in the
    morning with nobody watching.

    THE PROXIES ARE NOT READ EVERY NIGHT. Founder status changes when a
    company files a new proxy, roughly once a year. Re-reading five hundred
    of them daily would spend hours to learn nothing, so it runs weekly
    unless asked.
    """
    started = time.time()
    live, stage = args.dir, os.path.join(args.dir, "_staging")
    os.makedirs(stage, exist_ok=True)

    def path(name, staged=True):
        return os.path.join(stage if staged else live, name)

    def run(label, fn):
        log(f"{label}...")
        try:
            code = fn()
        except Exception as exc:  # noqa: BLE001
            log(f"FAILED {label}: {exc.__class__.__name__}: {exc}")
            return 1
        if code:
            log(f"FAILED {label}: exit {code}")
        return code or 0

    def ns(**kw):
        """A namespace for a sub-command, inheriting the global options.

        These were hand-listed once, and the list named a --cache-dir that
        the parser has never defined -- so every refresh died on its first
        stage. Copying whatever the parser actually produced cannot drift
        from it.
        """
        base = {k: v for k, v in vars(args).items()
                if k not in ("func", "cmd") and not k.startswith("_")}
        base.update(kw)
        return argparse.Namespace(**base)

    # 0 -- the universe, when the market-cap universe is in use.
    # THE SNAPSHOT IS QUARTERLY; THE PIPELINE READS THE NEWEST. A universe/
    # universe-<date>.csv present in the folder means the site runs on the
    # market-cap rules (fle/market_universe.py) rather than the S&P list.
    # When the newest snapshot is older than 90 days a fresh one is taken,
    # with the previous evidence file as memory for hysteresis, and the
    # published page is regenerated. The S&P site never enters this block:
    # no universe-*.csv exists there until the expansion is promoted.
    from .market_universe import newest_snapshot
    snap = newest_snapshot(os.path.join(args.dir, "universe"))
    if snap:
        members_path, evidence_path, taken = snap
        age = (datetime.date.today() - taken).days
        due = resnapshot_due(age, os.environ)
        if due == "hold":
            log(f"universe: snapshot {taken} is {age} days old; re-snapshot "
                f"held by FLE_UNIVERSE_RESNAPSHOT=0")
        elif due == "warn":
            log(f"universe: snapshot {taken} is {age} days old; a new one "
                f"will be taken in {90 - age} day(s) -- watch that night, or "
                f"set FLE_UNIVERSE_RESNAPSHOT=0 to hold")
        if due == "take":
            log(f"universe: snapshot {taken} is {age} days old; taking a new one")
            if run("universe", lambda: cmd_market_universe(ns(
                    min_cap=1e9, exit_cap=8e8, prior=evidence_path,
                    out=os.path.join(args.dir, "universe",
                                     f"universe-{datetime.date.today()}.csv"),
                    limit=None))):
                return 1
            members_path, evidence_path, taken = newest_snapshot(
                os.path.join(args.dir, "universe"))
        elif due != "warn":
            log(f"universe: snapshot {taken}, {age} days old, {sum(1 for _ in open(members_path))-1} members")
        args.universe = members_path
        from .market_universe import write_page
        write_page(members_path, evidence_path, taken.isoformat(),
                   os.path.join(args.dir, "about.html"),
                   path("universe.html"))

    # 0b -- the S&P list, weekly. It decides only who is free; every member
    # is already in the universe, so a change moves companies between tiers
    # and nothing else. One request, accepted only if it looks like the
    # S&P 500 (see universe.sp_list_acceptable); otherwise the current
    # list stays and the log says why.
    from .universe import newest_sp_list, sp_list_acceptable
    cur = newest_sp_list(os.path.join(args.dir, "universe"))
    sp_age = (datetime.date.today() - cur[1]).days if cur else 999
    if sp_age >= 7:
        try:
            fresh = fetch_members(_client(args))
            current = read_universe(cur[0]) if cur else []
            ok, why, adds, drops = sp_list_acceptable(fresh, current)
            if ok:
                out = os.path.join(args.dir, "universe",
                                   f"sp500-{datetime.date.today()}.csv")
                write_universe(fresh, out)
                log(f"S&P list: {len(fresh)} members -> {os.path.basename(out)}"
                    + (f"; added {', '.join(adds)}" if adds else "")
                    + (f"; dropped {', '.join(drops)}" if drops else "")
                    + " (commit the file)")
            else:
                log(f"S&P list: keeping {os.path.basename(cur[0]) if cur else 'none'}"
                    f" -- the fetched list was refused: {why}")
        except Exception as exc:  # noqa: BLE001 - the list is never a reason to lose a night
            log(f"S&P list: fetch failed ({exc.__class__.__name__}); keeping the current list")
    else:
        log(f"S&P list: {os.path.basename(cur[0])}, {sp_age} days old (weekly)")

    # 1 -- the panel. LAST NIGHT'S CHECKPOINT BECOMES TONIGHT'S PRIOR: a
    # finished checkpoint resumed as-is asks EDGAR nothing (five nights of
    # that, once), so it is moved aside and tonight starts empty -- and the
    # panel reads it as `prior`, carrying every company whose feeds show no
    # new relevant filing and recomputing the rest. An unfinished
    # checkpoint (a night that died) is left in place to resume.
    ck, prior = path("panel.jsonl"), path("panel-prior.jsonl")
    if rotate_checkpoint(ck, prior, args.universe):
        log("panel: last night's checkpoint is tonight's prior")
    # Each stage gets exactly what its own command reads. These defaults
    # mirror the parser's; a stage that grew an option and was not added
    # here used to die mid-run, hours in.
    if run("panel", lambda: cmd_panel(ns(
            universe=args.universe, out=path("panel.csv"), limit=None,
            tickers=None, ciks=None, redo="none",
            checkpoint=ck, prior=prior, workers=args.workers))):
        return 1

    # 2 -- the gate
    log("checking the verified holdings...")
    gate = cmd_diff(argparse.Namespace(
        before=path("panel.csv", staged=False), after=path("panel.csv"),
        limit=12, out=path("panel-diff.csv")))
    if gate and not args.force:
        moves = anchor_moves(path("panel.csv", staged=False), path("panel.csv"))
        bad = sorted(t for t, v in moves.items() if v == "unexplained")
        if bad:
            log(f"REFUSING TO PUBLISH -- a verified holding moved with no "
                f"newer filing to explain it: {', '.join(bad)}. Yesterday's "
                f"data is still live. Re-run with --force to override once "
                f"the change has been checked by hand.")
            return 2
        for t, v in sorted(moves.items()):
            if v == "explained":
                log(f"verified holding {t} moved on a new filing; publishing. "
                    f"Update ANCHORS in fle/cli.py once the figure is checked.")
            else:
                log(f"verified holding {t} still differs from its constant "
                    f"(unchanged tonight); ANCHORS in fle/cli.py is stale")
    # 2b -- the same question of every company: a share count that moved
    # with no newer filing to explain it is the rules moving, not the person
    odd = unexplained_moves(path("panel.csv", staged=False), path("panel.csv"))
    if odd and len(odd) > UNEXPLAINED_LIMIT and not args.force:
        log(f"REFUSING TO PUBLISH -- {len(odd)} companies' share counts moved "
            f"with no newer filing to explain it ({', '.join(odd[:12])}"
            f"{', ...' if len(odd) > 12 else ''}). That is a rule change, not "
            f"a night of filings. Yesterday's data is still live; "
            f"panel-diff.csv has every move. --force publishes anyway.")
        return 2
    if odd:
        log(f"{len(odd)} share count(s) moved with no newer filing -- within "
            f"the nightly allowance, worth a look: {', '.join(odd)}")

    # 3 -- history, reusing companies that have not filed
    if run("history", lambda: cmd_history(ns(
            universe=args.universe, out=path("history.csv"), limit=None,
            tickers=None, exclusions=args.exclusions, since=args.since,
            splits=True, reuse=path("history.csv", staged=False),
            state=os.path.join(live, "history-state.json"),
            workers=min(int(args.workers or 2), 3)))):
        return 1

    # 3.5 -- the trailing edge. History has just been rebuilt and the panel
    # is still staged, so the two can be reconciled before either is live.
    try:
        n = edge_confidence(path("panel.csv"), path("history.csv"))
        if n:
            log(f"capped confidence for {n} compan{'y' if n == 1 else 'ies'} "
                f"whose newest filing does not reconcile")
    except Exception as exc:  # noqa: BLE001 - never fail a run over a caveat
        log(f"edge confidence skipped: {exc.__class__.__name__}")

    # 4 -- prices
    run("prices", lambda: cmd_prices(ns(
        panel=path("panel.csv"), out=path("prices.csv"), date=None,
        store=PRICE_STORE)))

    # 5 -- events: the trade feed. Runs after history because the position
    # columns are read from the file history just wrote, and it is the
    # cheapest stage in the run -- every filing it needs is already in the
    # cache the panel filled. Non-fatal for the same reason prices is: a
    # site with yesterday's feed beats no site at all.
    run("events", lambda: cmd_events(ns(
        panel=path("panel.csv"), history=path("history.csv"),
        tickers=None, since=args.since, exclusions=args.exclusions,
        out=path("events.csv"))))

    # 6 -- founders, weekly
    fpath = path("founders.csv", staged=False)
    age = (time.time() - os.path.getmtime(fpath)) / 86400 if os.path.exists(fpath) else 999
    if args.founders or age >= 7:
        run("founders", lambda: cmd_founders(ns(
            panel=path("panel.csv"), out=path("founders.csv"),
            only=None, verbose=False, overrides=os.path.join(
                live, "founder-overrides.csv"),
            no_escalate=False, no_llm=False)))
    else:
        log(f"founders: {age:.1f} days old, skipping (weekly)")
        # copy2, not copyfile: a plain copy takes tonight's date, is
        # published, and reads as one day old again tomorrow -- so the
        # weekly re-read never came. The date must travel with the file.
        shutil.copy2(fpath, path("founders.csv"))

    # 6.2 -- performance, weekly: monthly closes move monthly
    ppath = path("perf.csv", staged=False)
    page = (time.time() - os.path.getmtime(ppath)) / 86400 \
        if os.path.exists(ppath) else 999
    if page >= 6:
        run("perf", lambda: cmd_perf(ns(
            panel=path("panel.csv"), out=path("perf.csv"), store=PRICE_STORE)))
    else:
        log(f"perf: {page:.1f} days old, skipping (weekly)")
        shutil.copy2(ppath, path("perf.csv"))

    # 6.5 -- free variants. The paywall is only as real as the files behind
    # it: with everything at public URLs, a blur is an honour system. The
    # rule for what a free file carries is exactly WHAT THE FREE PAGE SHOWS:
    # every purchase (the standing promise), plus the last 90 days of sales
    # -- not because free readers see sale rows (they don't; those are
    # blurred) but because the Selling-down cards, the teaser, and the
    # counts on the gated filter chips are all computed from them, and a
    # tease of "Sold 0" would gut the free page. The decade archive, the
    # thing Pro actually sells, deploys behind the gate.
    # (The free-tier variants once written here are the deploy's job now:
    # ops/build_site_data.py cuts the free files from these full ones by the
    # S&P list, and it is the only place that rule lives.)

    # 7 -- publish, atomically. panel.csv is one row per company in the
    # universe; the S&P list decides at deploy which rows are open.
    published = []
    for name in ("panel.csv", "history.csv", "prices.csv", "founders.csv",
                 "events.csv", "universe.html"):
        src = path(name)
        if os.path.exists(src) and os.path.getsize(src) > 0:
            os.replace(src, os.path.join(live, name))
            published.append(name)
    log(f"published {', '.join(published)} in "
        f"{(time.time() - started) / 60:.1f} min")
    # A FEED SERVED STALE IS SAID OUT LOUD. The client falls back to a
    # cached submissions list when EDGAR refuses the refetch; that keeps a
    # throttled night alive, and this line keeps it honest.
    if _stale_feeds():
        log(f"WARNING: {_stale_feeds()} submissions feed(s) served from a "
            f"stale cache after a failed refetch -- those companies may "
            f"lack tonight's filings")

    # 8 -- hand off to the host, if a deploy command is configured.
    # The mini PC is the builder, not the server: it assembles the site and
    # pushes it to a CDN, so the site stays up when the box does not. The
    # command lives in the environment rather than here, because it names
    # accounts and projects this code should not know about.
    deploy = os.environ.get("FLE_DEPLOY_CMD")
    if deploy:
        code = os.system(deploy)  # noqa: S605 - operator-configured, by design
        if code:
            log(f"FAILED deploy: exit {code}")
            return 1
        log("deployed")
    # the heartbeat is sent by cmd_refresh, for every exit path
    return 0


FREE_HISTORY_TICKERS = {"META", "TSLA", "COIN"}


def _write_variant(src: str, dst: str, keep) -> None:
    """Filter one published CSV into its free-tier sibling, header intact."""
    import csv as _csv
    if not os.path.exists(src) or os.path.getsize(src) == 0:
        return
    with open(src, encoding="utf-8-sig", newline="") as fh:
        reader = _csv.DictReader(fh)
        rows = [r for r in reader if keep(r)]
        fields = reader.fieldnames or []
    if not fields:
        return
    tmp = dst + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        writer = _csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, dst)


def _heartbeat(log, signal, body: str = "") -> None:
    """Ping the dead-man's switch: "start", or an exit code (0 = success).

    healthchecks.io reads /start as "a run began", /<n> as "it ended with
    exit status n" (nonzero alerts), and shows a POSTed body in the alert,
    so the tail of the log rides along and the email says why.
    """
    url = os.environ.get("FLE_HEARTBEAT_URL")
    if not url:
        return
    suffix = "/start" if signal == "start" else f"/{int(signal)}"
    try:
        import urllib.request
        req = urllib.request.Request(
            url.rstrip("/") + suffix,
            data=(body or "").encode("utf-8")[-100_000:],
            headers={"Content-Type": "text/plain; charset=utf-8"},
            method="POST")
        urllib.request.urlopen(req, timeout=10)  # noqa: S310 - operator-configured URL
    except Exception as exc:  # noqa: BLE001 - monitoring must never kill the run
        log(f"heartbeat failed: {exc.__class__.__name__}")


# Verified outside the pipeline; see VERIFIED in the dashboards.
ANCHORS = {"TSLA": 1123324786, "META": 342463325, "DELL": 294263250,
           "COIN": 25640144, "XYZ": 48844566, "LYV": 4188167,
           "ECHO": 147184017, "SMCI": 66396146, "FOXA": 86776627}


def anchor_moves(before_path: str, after_path: str) -> dict:
    """What to make of each verified holding that differs from its figure.

    THE GATE MUST TELL A FILING FROM A RULE CHANGE. It compares the new
    panel to nine share counts verified by hand, and any difference used to
    refuse the night -- which catches the rule change that quietly breaks
    Musk, and also catches Musk filing a Form 4, and after one real trade
    would have refused every night until the constants were edited by hand.

    Three verdicts per anchor that differs from its verified figure:
      explained  -- the new panel's figure was last stated on a NEWER
                    filing than the old panel's: the person filed, and the
                    number followed. Publish, and say so.
      carried    -- the figure is unchanged from last night: the difference
                    is inherited from a move already explained. Publish, and
                    remind the operator the constant is stale.
      unexplained -- the figure moved and no newer filing states it: the
                    rules moved, not the person. Refuse.
    """
    def read(path):
        out = {}
        try:
            with open(path, encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh):
                    t = (row.get("ticker") or "").strip().upper()
                    if t:
                        out[t] = row
        except FileNotFoundError:
            pass
        return out

    def num(row, col):
        try:
            return float((row.get(col) or "").replace(",", ""))
        except (ValueError, AttributeError):
            return None

    old, new = read(before_path), read(after_path)
    verdict = {}
    for t, want in ANCHORS.items():
        n = new.get(t)
        if n is None:
            continue
        got = num(n, "shares")
        if got is None or abs(got - want) <= 0.5:
            continue
        o = old.get(t)
        before = num(o, "shares") if o else None
        if before is not None and abs(before - got) <= 0.5:
            verdict[t] = "carried"
        elif o and (n.get("shares_as_of") or "") > (o.get("shares_as_of") or ""):
            verdict[t] = "explained"
        else:
            verdict[t] = "unexplained"
    return verdict


def unexplained_moves(before_path: str, after_path: str) -> list[str]:
    """Every company whose share count moved with no newer filing to say so.

    WITH FINGERPRINTED REUSE, AN UNCHANGED COMPANY IS CARRIED VERBATIM, so
    a row whose share count differs from last night's was recomputed
    because a relevant filing landed. If its shares_as_of did not advance,
    the number moved and no filing explains it: the rules moved, not the
    person. That is the anchor gate's question asked of every company
    instead of nine, with no constants to maintain.
    """
    def read(path):
        out = {}
        try:
            with open(path, encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh):
                    t = (row.get("ticker") or "").strip().upper()
                    if t:
                        out[t] = row
        except FileNotFoundError:
            pass
        return out

    def num(row, col):
        try:
            return float((row.get(col) or "").replace(",", ""))
        except (ValueError, AttributeError):
            return None

    old, new = read(before_path), read(after_path)
    bad = []
    for t, n in new.items():
        o = old.get(t)
        if o is None:
            continue
        a, b = num(o, "shares"), num(n, "shares")
        if a is None or b is None or abs(a - b) <= 0.5:
            continue
        if (n.get("shares_as_of") or "") > (o.get("shares_as_of") or ""):
            continue
        bad.append(t)
    return sorted(bad)


# how many unexplained moves a night may carry before it is a rule change
# rather than a filer's oddity (an amended cover page, a restated figure)
UNEXPLAINED_LIMIT = 5


def resnapshot_due(age_days: int, env: dict) -> str:
    """"take" | "warn" | "hold" | "" for a universe snapshot of this age.

    QUARTERLY, ON BY DEFAULT, WITH A WEEK'S NOTICE. The cadence the About
    page promises and the two-snapshot exit rule was designed around. The
    log says a week ahead that one is coming, so the first unattended
    snapshot can be watched; FLE_UNIVERSE_RESNAPSHOT=0 holds it.
    """
    if age_days >= 90:
        return "hold" if env.get("FLE_UNIVERSE_RESNAPSHOT") == "0" else "take"
    if age_days >= 83:
        return "warn"
    return ""


def cmd_diff(args) -> int:
    """Two panels, side by side, so a rule change can be inspected.

    A change to the counting rule is not a bug fix until someone has looked
    at what it moved. This prints every company whose number changed,
    largest first, and flags the anchors -- the holdings reconciled against
    proxies and outside data -- so that a regression in them is impossible
    to miss.
    """
    def read(path):
        """A panel keyed by ticker, or nothing if the file is not there.

        The first run has no published panel to compare against, and the
        gate does not need one: the anchor check below reads only the new
        panel. Treating a missing baseline as empty lets a first run reach
        the gate instead of dying at it, and the report simply lists every
        company as added.
        """
        out = {}
        try:
            fh = open(path, encoding="utf-8-sig")
        except FileNotFoundError:
            return out
        with fh:
            for row in csv.DictReader(fh):
                t = (row.get("ticker") or "").strip().upper()
                if t:
                    out[t] = row
        return out

    old, new = read(args.before), read(args.after)
    if not old:
        print(f"  no baseline at {args.before} -- first run, "
              f"nothing to compare against\n")
    def num(row, col):
        try:
            return float((row.get(col) or "").replace(",", ""))
        except (ValueError, AttributeError):
            return None

    moved, gone, added, anchor_breaks = [], [], [], []
    for t, n in new.items():
        o = old.get(t)
        if o is None:
            added.append(t)
            continue
        a_, b_ = num(o, "shares"), num(n, "shares")
        if a_ is None or b_ is None or a_ == b_:
            continue
        moved.append((abs((b_ - a_) / a_) if a_ else 9e9, t,
                      o.get("ceo", ""), a_, b_,
                      num(o, "pct"), num(n, "pct")))
    gone = [t for t in old if t not in new]

    for t, want in ANCHORS.items():
        if t in new:
            got = num(new[t], "shares")
            if got is not None and abs(got - want) > 0.5:
                anchor_breaks.append((t, want, got))

    moved.sort(reverse=True)
    print(f"  {len(new)} companies; {len(moved)} changed, "
          f"{len(added)} added, {len(gone)} dropped\n")
    if anchor_breaks:
        print("  *** VERIFIED HOLDINGS THAT MOVED -- these were reconciled "
              "against proxies and outside data ***")
        for t, want, got in anchor_breaks:
            print(f"    {t:<6} was verified at {want:>15,.0f}, "
                  f"now {got:>15,.0f}")
        print()
    else:
        print("  all nine verified holdings unchanged\n")

    if moved:
        print(f"  {'ticker':<7}{'chief executive':<26}{'before':>15}"
              f"{'after':>15}{'change':>10}   pct")
        for rel, t, ceo, a_, b_, pa, pb in moved[:args.limit]:
            pct = f"{pa:.3f} -> {pb:.3f}" if pa is not None and pb is not None else ""
            print(f"    {t:<7}{ceo[:24]:<26}{a_:>15,.0f}{b_:>15,.0f}"
                  f"{(b_-a_)/a_*100 if a_ else 0:>9.1f}%   {pct}")
        if len(moved) > args.limit:
            print(f"    ... and {len(moved)-args.limit} more")
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow(["ticker", "ceo", "shares_before", "shares_after",
                        "change_pct", "pct_before", "pct_after"])
            for rel, t, ceo, a_, b_, pa, pb in moved:
                w.writerow([t, ceo, int(a_), int(b_),
                            f"{(b_-a_)/a_*100:.2f}" if a_ else "",
                            pa if pa is not None else "",
                            pb if pb is not None else ""])
        print(f"\n  wrote {args.out}")
    return 1 if anchor_breaks else 0


def cmd_founders(args) -> int:
    """Read each company's newest proxy and decide the founder flag.

    Three verdicts, never two: yes and no come from the document, unknown
    means the document could not be read -- a failed fetch is not a no.
    Every yes carries the sentence that earned it, checked against the
    filing before it is written.
    """
    from .founders import FoundersApiError, VerdictCache, find_founder

    client = _client(args)
    rows = []
    only = {t.strip().upper() for t in (args.only or "").split(",") if t.strip()}
    with open(args.panel, encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            t = (row.get("ticker") or "").strip()
            if t and (not only or t.upper() in only):
                rows.append(row)

    key = None if args.no_llm else SETTINGS.anthropic_api_key
    if not args.no_llm and not key:
        # A NOTE IS NOT CONSENT. This used to print one line and then
        # classify the whole universe by heuristics -- a third of it
        # "uncertain" at zero cost, the note long scrolled away. Running
        # without the model is a choice the operator makes with a flag,
        # never a degradation the run makes for them.
        print("  no ANTHROPIC_API_KEY configured. Add it to .env, or pass "
              "--no-llm to record the windows without a verdict (deliberately).")
        return 2

    # ANSWERS ARE KEYED BY WHAT WAS READ. Unchanged proxies cost nothing on
    # a re-run and cannot drift; a changed one is always asked afresh.
    cache = VerdictCache(os.path.join(SETTINGS.cache_dir, "founders-verdicts.json"))
    if cache.data:
        print(f"  {len(cache.data)} cached verdict(s) in {cache.path}")

    overrides = {}
    if args.overrides:
        try:
            with open(args.overrides, encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh):
                    t = (row.get("ticker") or "").strip().upper()
                    if t and (row.get("founder") or "").strip():
                        overrides[t] = row
            print(f"  {len(overrides)} hand-settled override(s) loaded")
        except FileNotFoundError:
            pass

    counts: dict = {}
    not_verbatim = 0
    with open(args.out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "cik", "ceo", "founder", "method",
                    "early_presence", "evidence", "source", "founders_named"])
        for i, row in enumerate(rows, 1):
            tick, ceo = row["ticker"].strip(), (row.get("ceo") or "").strip()
            company = (row.get("company") or "").strip()
            try:
                cik = int(float(row.get("cik") or 0))
            except ValueError:
                cik = 0
            v = None
            if not cik or not ceo:
                v_founder, v_method, ev, src = "unknown", "no-name", "", ""
                early, named = "", ""
            else:
                try:
                    v = find_founder(client, cik, ceo, company=company,
                                     api_key=key, escalate=not args.no_escalate,
                                     cache=cache)
                except FoundersApiError as exc:
                    print(f"\n  founders aborted at {tick}: {exc}")
                    print("  nothing usable written; fix the key/network "
                          "and rerun (or --only the remainder)")
                    return 2
                v_founder, v_method = v.founder, v.method
                ev, src = v.evidence[:400], v.source
                early, named = v.early_presence, v.founders_named[:120]
                if "not verbatim" in v_method:
                    not_verbatim += 1
                if only and args.verbose:
                    # SHOW THE WORK for a few companies: every window the
                    # reader saw, and its reason. Built for the day Tesla
                    # came back "no" and the only way to know why was to
                    # read the windows.
                    print(f"  {tick}: {v.founder} ({v.method}) from {src}")
                    if v.reason:
                        print(f"      reason: {v.reason}")
                    if named:
                        print(f"      founders named: {named}")
                    for j, win in enumerate(v.snippets, 1):
                        print(f"      [{j}] ...{win[:220]}...")
            ov = overrides.get(tick.upper())
            if ov:
                # A HUMAN SETTLED THIS ONE, AND SAYS SO IN THE FILE.
                # The verdict is applied last, labelled manual, and carries
                # the evidence the person recorded -- never a bare flag.
                v_founder = (ov.get("founder") or "").strip().lower()
                v_method = "manual"
                ev = (ov.get("evidence") or "")[:400]
                src = ov.get("source") or "overrides.csv"
            counts[v_founder] = counts.get(v_founder, 0) + 1
            if v_founder != "yes" and v is not None and v.other_company:
                # Worth surfacing: they founded something, just not this.
                v_method = f"{v_method} (founded {v.other_company[:40]})"
            w.writerow([tick, cik or "", ceo, v_founder, v_method, early,
                        ev, src, named])
            if i % 25 == 0 or i == len(rows):
                print(f"  {i}/{len(rows)}  "
                      + "  ".join(f"{k}:{n}" for k, n in sorted(counts.items())))
    print(f"  wrote {args.out}")
    print(f"  reader: {cache.misses} asked, {cache.hits} answered from cache")
    if not_verbatim:
        print(f"  {not_verbatim} verdict(s) whose quote was not verbatim; the "
              "window is shown instead and the method says so")
    if counts.get("uncertain"):
        print(f"  {counts['uncertain']} uncertain -- their windows are in the "
              "evidence column; settle them by hand in founder-overrides.csv "
              "if the document is genuinely ambiguous")
    return 0


def cmd_forms(args) -> int:
    """Every form type in a filing feed, with how many and the date range.

    Built because a 13D/13G scan found nothing anywhere after 14 November
    2024 -- across fifteen companies and nine hundred filings -- while the
    XML mandate for those schedules took effect on 18 December 2024. Emanuel
    filed a 13D/A on 24 March 2025 reporting his shared power had gone to
    zero, and we cannot see it.

    Either the feed lacks them or our form filter does. This shows which,
    instead of another guess.
    """
    client = _client(args)
    subs = client.submissions(int(args.cik))
    rows = subs.get("_filings", [])
    kinds: dict = {}
    for f in rows:
        k = f.get("form") or "(blank)"
        d = f.get("filingDate") or ""
        lo, hi, n = kinds.get(k, ("9999", "0000", 0))
        kinds[k] = (min(lo, d) if d else lo, max(hi, d), n + 1)

    if args.period:
        # BY THE PERIOD, NOT THE POSTMARK.
        #
        # The walk groups filings by the date they report on, so "what else
        # is in this moment" cannot be answered by filing date. A Form 4 for
        # the 9th is normally filed on the 10th or the 11th, and asking for
        # the 9th finds none of them.
        same = [f for f in rows
                if (f.get("reportDate") or f.get("filingDate") or "")
                == args.period]
        print(f"  {len(same)} filing(s) REPORTING ON {args.period} "
              f"for CIK {int(args.cik)}\n")
        for f in sorted(same, key=lambda x: x.get("filingDate") or ""):
            print(f"    {f.get('form'):<8}{f.get('accessionNumber')}"
                  f"   filed {f.get('filingDate')}"
                  f"   {f.get('primaryDocument')}")
        return 0

    if args.date:
        # EVERY FILING MADE ON ONE DAY.
        #
        # A day is the unit the walk emits, and a person may file several
        # times in it. Musk's 10 March 2023 shows two option exercises in
        # the document we opened, but the day's codes read "GM" -- there is
        # another form, and it has to be nameable before it can be read.
        same = [f for f in rows if (f.get("filingDate") or "") == args.date]
        print(f"  {len(same)} filing(s) on {args.date} for CIK {int(args.cik)}\n")
        for f in same:
            print(f"    {f.get('form'):<8}{f.get('accessionNumber')}"
                  f"   {f.get('primaryDocument')}")
        return 0

    print(f"  {len(rows)} filings in the feed for CIK {int(args.cik)}")
    files = subs.get("filings", {}).get("files", [])
    print(f"  {len(files)} archive file(s) beyond `recent`\n")
    print(f"  {'form':<18}{'count':>7}   {'earliest':<12}{'latest'}")
    want = (args.grep or "").lower()
    for k, (lo, hi, n) in sorted(kinds.items(), key=lambda kv: -kv[1][2]):
        if want and want not in k.lower():
            continue
        print(f"  {k[:18]:<18}{n:>7}   {lo:<12}{hi}")
    return 0


def cmd_lines(args) -> int:
    """Every raw row for one person, grouped by what we key on.

    Built because a fix for Blackstone appears to have broken Block, and I
    guessed twice at why instead of looking. This prints what the filings
    actually contain: the raw natureOfOwnership, the footnote ids, the
    footnote text, and the balance -- so the shape of the problem is visible
    rather than inferred.
    """
    from .ledger import SECTION16, _parse, _t, _num, _rows
    client = _client(args)
    cik = int(args.cik)

    subs = client.submissions(cik)
    s16 = [f for f in subs.get("_filings", []) if f.get("form") in SECTION16]
    s16.sort(key=lambda f: (f.get("filingDate") or ""), reverse=True)

    # ONE DOCUMENT, EVERY ROW.
    #
    # The grouped view answers "what titles does this person use"; it cannot
    # answer "what did THIS filing say", which is the question when a single
    # snapshot disagrees with its neighbours. Nvidia's 6 January 2021 point
    # reports 4,006,734 shares between two of 21.4 million, and the only way
    # to know whether the filing is partial or we mis-read it is to look at
    # the document.
    if args.accession:
        want = args.accession.replace("-", "")
        hit = [f for f in s16
               if (f.get("accessionNumber") or "").replace("-", "") == want]
        if not hit:
            print(f"  no filing {args.accession} for CIK {cik}")
            return 1
        f = hit[0]
        root = _parse(client, cik, f)
        if root is None:
            print("  the document would not parse")
            return 1
        print(f"  {f.get('form')} filed {f.get('filingDate')}  "
              f"{f.get('accessionNumber')}\n")
        print(f"  {'tbl':<5}{'code':<6}{'D/I':<5}{'title':<34}"
              f"{'nature':<34}{'moved':>14}{'price':>10}{'balance':>16}")
        total = 0.0
        for r in _rows(root, f.get("form") or "", f.get("filingDate") or "",
                       f.get("accessionNumber") or ""):
            bal = r.shares
            has_bal = bal == bal          # NaN means the row is footnoted
            if has_bal and r.table == "I":
                total += bal
            print(f"  {r.table:<5}{(r.code or '-'):<6}{r.direct:<5}"
                  # The nature is printed WHOLE. Truncating it at thirty-two
                  # characters hid the "(9)" that split Armstrong's trust in
                  # two and cost a day of investigation.
                  f"{r.security[:24]:<26}{(r.nature or ''):<46}"
                  f"{(f'{r.moved:,.0f}' if r.moved else '-'):>14}"
                  f"{(f'{r.price:,.2f}' if r.price else '-'):>10}"
                  f"{(f'{bal:,.0f}' if has_bal else 'footnoted'):>16}")
        # HOW THE WALK ACTUALLY GROUPS THEM.
        #
        # The row dump shows what the document says; it does not show what
        # the rule does with it. When a total is wrong but every row looks
        # right, the fault is in the KEY -- two rows that should share a
        # vehicle landing under different ones, or the reverse. So the
        # grouping is replayed here, keys quoted exactly.
        from .ledger import Group, vehicle_key
        groups: dict = {}
        for r in _rows(root, f.get("form") or "", f.get("filingDate") or "",
                       f.get("accessionNumber") or ""):
            key = r.security.strip().lower()
            g = groups.setdefault(key, Group(security=r.security,
                                             direct=r.direct))
            vehicle = vehicle_key(r.direct, r.nature)
            if r.code:
                if vehicle not in g.opening:
                    signed = (r.moved if r.acquired else -r.moved) or 0.0
                    g.opening[vehicle] = r.shares - signed
                g.last_txn[vehicle] = r.shares
            else:
                g.opening.setdefault(vehicle, r.shares)
                g.holdings += r.shares
                g.hold_by_vehicle[vehicle] = (
                    g.hold_by_vehicle.get(vehicle, 0.0) + r.shares)
        print("\n  as the walk groups them "
              "(opening -> closing; chains join where one segment's opening"
              "\n   is another's closing balance):")
        walked = 0.0
        for title, g in groups.items():
            sub = sum(g.vehicles().values())
            walked += sub
            print(f"    {title!r}  ->  {sub:,.0f}")
            for vehicle, v in g.vehicles().items():
                op = g.opening.get(vehicle, v)
                tag = "txn" if vehicle in g.last_txn else "holding"
                print(f"        {vehicle!r} [{tag}]: "
                      f"{op:,.0f} -> {v:,.0f}")
        print(f"    this filing contributes {walked:,.0f}")
        print(f"\n  Table I balances sum to {total:,.0f} -- compare this "
              f"with the neighbouring filings.")
        print("  A filing that names fewer vehicles than usual reports less "
              "than the person holds.")
        return 0

    seen: dict = {}
    for f in s16[:args.limit]:
        root = _parse(client, cik, f)
        if root is None:
            continue
        when = f.get("filingDate") or ""
        for tag in ("nonDerivativeTransaction", "nonDerivativeHolding",
                    "derivativeTransaction", "derivativeHolding"):
            for node in root.iter(tag):
                own = node.find("ownershipNature")
                if own is None:
                    continue
                sec = _t(node, "securityTitle") or ""
                if args.security and args.security.lower() not in sec.lower():
                    continue
                nat = _t(own, "natureOfOwnership") or ""
                di = (_t(own, "directOrIndirectOwnership") or "D").upper()[:1]
                bal = _num(node.find("postTransactionAmounts"),
                           "sharesOwnedFollowingTransaction")
                seen.setdefault((sec, di), []).append((when, nat, bal))

    print(f"  {len(seen)} distinct security titles in the "
          f"{args.limit} newest filings\n")
    print(f"  {'rows':>5}  {'D/I':<5}{'title as the filer wrote it':<46}"
          f"newest balance")
    for (sec, di), rows in sorted(seen.items(), key=lambda kv: -len(kv[1])):
        bal = next((b for _, _, b in rows if b is not None), None)
        print(f"  {len(rows):>5}  {di:<5}{sec[:44]:<46}"
              f"{(f'{bal:,.0f}' if bal is not None else 'footnoted'):>16}")
        for when, nat, b in rows[:args.show]:
            if nat:
                print(f"  {'':>12}{when}  {nat[:40]:<42}"
                      f"{(f'{b:,.0f}' if b is not None else '-'):>16}")
    return 0


def cmd_footnotes(args) -> int:
    """The footnote text of one person's filings, around a given date.

    We parse footnote IDs and never read what they say -- but a vehicle that
    stops appearing usually has an explanation in prose. Zuckerberg's "Chan
    Zuckerberg Initiative, LLC" holds 414,123,745 Class B shares in December
    2015 and never again; whether those shares moved, and where, should be
    written in a footnote on a filing shortly after.

    Reading the filings is cheap. Guessing, as I did, is not.
    """
    from .ledger import SECTION16, _parse
    client = _client(args)
    cik = int(args.cik)

    subs = client.submissions(cik)
    s16 = [f for f in subs.get("_filings", []) if f.get("form") in SECTION16]
    s16.sort(key=lambda f: (f.get("filingDate") or ""))
    window = [f for f in s16
              if (not args.after or (f.get("filingDate") or "") >= args.after)
              and (not args.before or (f.get("filingDate") or "") <= args.before)]
    print(f"  {len(window)} filings between {args.after or 'the start'} and "
          f"{args.before or 'now'}\n")

    shown = 0
    for f in window[:args.limit]:
        root = _parse(client, cik, f)
        if root is None:
            continue
        notes = [(fn.get("id"), " ".join((fn.text or "").split()))
                 for fn in root.iter("footnote")]
        notes = [(i, t) for i, t in notes
                 if not args.grep or args.grep.lower() in t.lower()]
        if not notes:
            continue
        shown += 1
        print(f"  {f.get('filingDate')}  {f.get('form')}  "
              f"{f.get('accessionNumber')}")
        for fid, text in notes:
            print(f"    {fid or '-':<5}{text[:args.width]}")
        print()
    if not shown:
        print("  nothing matched")
    return 0


def cmd_insiders(args) -> int:
    """Every reporting owner this issuer has, scored against the CEO name.

    "could not find this person among 3,385 Section 16 filings" says nothing
    about WHY. The answer is always one of three things -- the name is spelled
    differently, the person genuinely has no filings, or the search did not
    reach them -- and seeing the candidates tells them apart in a glance.
    """
    import xml.etree.ElementTree as ET
    from .ledger import SECTION16, _owners, _parse
    from .names import names_match

    client = _client(args)
    cik = int(args.cik)
    want = args.owner
    if not want:
        cert = peo_from_certification(client, cik)
        if not cert:
            print("  no Section 302 certification; pass --owner")
            return 1
        want = cert.name
        print(f"  certification names: {want}  ({cert.form} {cert.filing_date})")

    subs = client.submissions(cik)
    s16 = [f for f in subs.get("_filings", []) if f.get("form") in SECTION16]
    s16.sort(key=lambda f: (f.get("filingDate") or ""), reverse=True)
    threes = [f for f in s16 if (f.get("form") or "").startswith("3")]
    look = threes + [f for f in s16 if f not in threes][:args.max_search]
    print(f"  {len(s16)} Section 16 filings, {len(threes)} of them Form 3s; "
          f"reading {len(look)}")

    seen: dict = {}
    for i, f in enumerate(look, 1):
        if i % 20 == 0:
            sys.stdout.write(f"\r  {i}/{len(look)}..."); sys.stdout.flush()
        root = _parse(client, cik, f)
        if root is None:
            continue
        for owner_cik, name, title, is_officer in _owners(root):
            prev = seen.get(owner_cik)
            if not prev or (is_officer and not prev[2]):
                seen[owner_cik] = (name, title, is_officer,
                                   names_match(want, name))
    _clear()

    # When every score is 0.00, ranking by score shows 25 arbitrary names and
    # hides the one being looked for. Fall back to shared name parts, which
    # at least puts the near-misses on top.
    from .names import token_overlap
    ranked = sorted(seen.items(),
                    key=lambda kv: (-kv[1][3], -token_overlap(want, kv[1][0]),
                                    -kv[1][2]))
    print(f"\n  {len(ranked)} distinct reporting owners\n")
    print(f"  {'score':>6}{'shared':>8}  {'officer':<8}{'name':<38}{'CIK':<12}title")
    for owner_cik, (name, title, is_officer, score) in ranked[:args.top]:
        mark = "yes" if is_officer else ""
        print(f"  {score:>6.2f}{token_overlap(want, name):>8.2f}  {mark:<8}"
              f"{name[:36]:<38}{owner_cik:<12}{title[:26]}")
    best = ranked[0][1][3] if ranked else 0
    if best < 0.7:
        print(f"\n  nothing reached 0.70. Either the name is spelled "
              f"differently above, or they have never filed here.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser("fle", description=__doc__)
    p.add_argument("--user-agent", default=None,
                   help=f"default: {SETTINGS.user_agent}")
    p.add_argument("--exclusions", default=None,
                   help="curated corrections (default universe/exclusions.csv)")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("ceo", help="who the certification names")
    c.add_argument("--cik", required=True)
    c.add_argument("--why", action="store_true",
                   help="when it fails, show which stage broke")
    c.set_defaults(func=cmd_ceo)

    l = sub.add_parser("ledger", help="every line the insider holds")
    l.add_argument("--cik", required=True, help="the ISSUER's CIK")
    l.add_argument("--owner", default=None, help="skip the certification lookup")
    l.add_argument("--owner-cik", default=None)
    l.add_argument("--max-filings", type=int, default=None,
                   help="cap the walk; the default reads all of their filings")
    l.add_argument("--ticker", default=None,
                   help="needed to adjust historical amounts for splits")
    l.add_argument("--trace", action="store_true",
                   help="print every row of every filing, newest first")
    l.add_argument("--fast", action="store_true",
                   help="stop once every line seen so far is current -- quick "
                        "for one company, unsafe for a panel")
    l.add_argument("--max-search", type=int, default=500,
                   help="Form 3s are always searched in full; this bounds the "
                        "Form 4 sweep afterwards. 0 means no bound.")
    l.set_defaults(func=cmd_ledger)

    hi = sub.add_parser("history",
                        help="a snapshot after every filing")
    hi.add_argument("--universe", required=True)
    hi.add_argument("--tickers", default=None)
    hi.add_argument("--since", default="2016-01-01",
                    help="emit nothing before this (all filings are still read)")
    hi.add_argument("--limit", type=int, default=None)
    hi.add_argument("--splits", action="store_true",
                    help="restate share counts to today's split basis, AND "
                         "carry the denominator through splits so the "
                         "percentage stays right in the months between a "
                         "split and the cover page that restates the count")
    hi.add_argument("--out", default="history.csv")
    hi.add_argument("--workers", type=int, default=2,
                    help="walk companies in this many recycled worker "
                         "processes (bounds memory; shares the SEC rate limit)")
    hi.add_argument("--reuse", default=None,
                    help="carry over rows for companies with no new filings, "
                         "from this previous history CSV")
    hi.add_argument("--state", default="history-state.json",
                    help="where the newest accession per company is remembered")
    hi.set_defaults(func=cmd_history)

    ev = sub.add_parser("events",
                        help="every CEO buy/sell, one row per filing, code and day")
    ev.add_argument("--panel", default="panel.csv")
    ev.add_argument("--history", default="history.csv",
                    help="where the position columns come from")
    ev.add_argument("--tickers", default=None)
    ev.add_argument("--since", default="",
                    help="emit nothing traded before this date")
    ev.add_argument("--exclusions", default=None)
    ev.add_argument("--out", default="events.csv")
    ev.set_defaults(func=cmd_events)

    pr = sub.add_parser("prices",
                        help="closing prices for every panel ticker, one request")
    pr.add_argument("--panel", default="panel.csv")
    pr.add_argument("--date", default=None,
                    help="trading day to price at (default: most recent)")
    pf = sub.add_parser("perf",
                        help="refresh the daily price store for every ticker "
                             "and cut perf.csv (month-end closes) from it")
    pf.add_argument("--panel", default="panel.csv")
    pf.add_argument("--store", default=PRICE_STORE,
                    help="folder of <TICKER>.csv daily closes")
    pf.add_argument("--only", default=None,
                    help="comma-separated tickers; refresh just these")
    pf.add_argument("--out", default="perf.csv")
    pf.set_defaults(func=cmd_perf)
    pr.add_argument("--out", default="prices.csv")
    pr.add_argument("--store", default=PRICE_STORE,
                    help="folder of <TICKER>.csv daily closes to append the day to")
    pr.set_defaults(func=cmd_prices)

    rf = sub.add_parser("refresh",
                        help="the nightly job: rebuild, check the anchors, "
                             "publish only if they hold")
    rf.add_argument("--dir", default=".",
                    help="the folder the site is served from")
    rf.add_argument("--universe", default="universe/sp500-2026-08-25.csv")
    rf.add_argument("--exclusions", default=None)
    rf.add_argument("--since", default="2016-01-01")
    rf.add_argument("--workers", type=int, default=4)
    rf.add_argument("--founders", action="store_true",
                    help="re-read every proxy tonight, not just weekly")
    rf.add_argument("--force", action="store_true",
                    help="publish even if a verified holding moved")
    rf.set_defaults(func=cmd_refresh)

    df = sub.add_parser("diff",
                        help="compare two panel CSVs, before and after a rule change")
    df.add_argument("--before", required=True)
    df.add_argument("--after", required=True)
    df.add_argument("--limit", type=int, default=40)
    df.add_argument("--out", default="panel-diff.csv")
    df.set_defaults(func=cmd_diff)

    fo = sub.add_parser("founders",
                        help="decide the founder flag from each proxy statement")
    fo.add_argument("--panel", default="panel.csv")
    fo.add_argument("--only", default=None,
                    help="comma-separated tickers; run just these")
    fo.add_argument("--verbose", action="store_true",
                    help="with --only: print every window the reader saw and its reason")
    fo.add_argument("--overrides", default="founder-overrides.csv",
                    help="hand-settled verdicts applied last (ticker,founder,"
                         "evidence,source); marked method=manual")
    fo.add_argument("--no-escalate", action="store_true",
                    help="do not consult the earliest proxy and the "
                         "registration statement when the newest proxy is "
                         "silent (faster, and more false negatives)")
    fo.add_argument("--no-llm", action="store_true",
                    help="never call the language model; every company with founder "
                         "language near the name stays uncertain, windows recorded")
    fo.add_argument("--out", default="founders.csv")
    fo.set_defaults(func=cmd_founders)

    fm = sub.add_parser("forms",
                        help="what form types a filing feed actually contains")
    fm.add_argument("--cik", required=True)
    fm.add_argument("--grep", default=None, help="only forms matching this")
    fm.add_argument("--period", default=None,
                    help="list every filing REPORTING ON this date, whenever "
                         "it was filed (YYYY-MM-DD)")
    fm.add_argument("--date", default=None,
                    help="list every filing made on this date (YYYY-MM-DD)")
    fm.set_defaults(func=cmd_forms)

    ln = sub.add_parser("lines",
                        help="raw rows for one person, grouped by our key")
    ln.add_argument("--cik", required=True, help="the PERSON's CIK")
    ln.add_argument("--security", default=None, help="filter by security title")
    ln.add_argument("--limit", type=int, default=40)
    ln.add_argument("--show", type=int, default=6)
    ln.add_argument("--accession", default=None,
                    help="print every row of ONE filing instead of the "
                         "grouped view (dashes optional)")
    ln.set_defaults(func=cmd_lines)

    fn = sub.add_parser("footnotes",
                        help="read the footnote text of a person's filings")
    fn.add_argument("--cik", required=True, help="the PERSON's CIK, not the issuer")
    fn.add_argument("--after", default=None, help="YYYY-MM-DD")
    fn.add_argument("--before", default=None, help="YYYY-MM-DD")
    fn.add_argument("--grep", default=None, help="only notes containing this")
    fn.add_argument("--limit", type=int, default=12)
    fn.add_argument("--width", type=int, default=300)
    fn.set_defaults(func=cmd_footnotes)

    ins = sub.add_parser("insiders",
                         help="list reporting owners, scored against the CEO")
    ins.add_argument("--cik", required=True)
    ins.add_argument("--owner", default=None)
    ins.add_argument("--max-search", type=int, default=200)
    ins.add_argument("--top", type=int, default=25)
    ins.set_defaults(func=cmd_insiders)

    o = sub.add_parser("outstanding", help="the denominator and its history")
    o.add_argument("--cik", required=True)
    o.set_defaults(func=cmd_outstanding)

    ix = sub.add_parser("index", help="snapshot S&P 500 membership")
    ix.add_argument("--out", default=None, help="default: universe/sp500-<today>.csv")
    ix.add_argument("--all", action="store_true",
                    help="every SEC registrant with a ticker, not the S&P 500")
    ix.add_argument("--min-cap", type=float, default=None,
                    help="the market-cap universe: every domestic filer at or "
                         "above this cap (e.g. 1e9), by written rules")
    ix.add_argument("--exit-cap", type=float, default=8e8,
                    help="a member leaves after two snapshots below this")
    ix.add_argument("--prior", default=None,
                    help="previous snapshot's -evidence.csv, for hysteresis")
    ix.add_argument("--limit", type=int, default=None,
                    help="cap registrants considered (trial runs)")
    ix.set_defaults(func=cmd_index)

    pn = sub.add_parser("panel", help="run a universe, resumably")
    pn.add_argument("--universe", required=True)
    pn.add_argument("--checkpoint", default="panel.jsonl")
    pn.add_argument("--out", default="panel.csv")
    pn.add_argument("--ciks", default=None, help="restrict to these CIKs")
    pn.add_argument("--tickers", default=None,
                    help="restrict to these tickers, e.g. TSLA,META,NVDA")
    pn.add_argument("--limit", type=int, default=None,
                    help="first N in ticker order -- the same N every time")
    pn.add_argument("--redo", default="none", choices=["none", "failed", "all"])
    pn.add_argument("--prior", default=None,
                    help="a finished checkpoint from a previous run; rows whose "
                         "feeds show no new relevant filing are carried over")
    pn.add_argument("--workers", type=int, default=1,
                    help="companies identified concurrently; the checkpoint "
                         "is appended under a lock either way")
    pn.set_defaults(func=cmd_panel)

    r = sub.add_parser("run", help="companies end to end")
    r.add_argument("--ciks", required=True, help="comma separated")
    r.add_argument("--out", default=None)
    r.set_defaults(func=cmd_run)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
