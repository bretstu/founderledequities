"""Command line interface."""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import sys
from datetime import date

from .config import SEC_BASE
from .edgar import EdgarClient
from .dashboard import load_records, write_dashboard
from .site import write_site
from .triage import triage
from .inspect import inspect_ticker
from .panel import build_panel, panel_records, load_completed
from .verify import (build_sample, write_worksheet, score_worksheet,
                     format_score, answer_counts, WorksheetOpenError,
                     build_roll_worksheet, write_roll_worksheet)
from .pipeline import run_tickers, OwnershipRecord
from .universe import proxy_filers, find_exits

CSV_COLUMNS = [
    "ticker", "cik", "company", "sic_description", "ceo_name", "ceo_name_in_table", "ceo_source", "ceo_identity_source", "ceo_identity_evidence", "peo_names",
    "resolution", "escalation_reason",
    "shares_13d3", "shares_source", "column_used", "options_60d", "options_60d_implied", "prior_year_shares", "yoy_change_pct",
    "shares_outstanding", "share_class_count", "denominator_source",
    "denominator_region", "parser_shares", "model_shares", "model_note", "model_outstanding",
    "parser_outstanding", "llm_outstanding",
    "rolled_shares", "rolled_pct", "rolled_net_delta", "rolled_txn_count",
    "numerator_as_of", "rolled_denominator", "rolled_denominator_as_of",
    "rolled_gap_days", "buyback_pace",
    "model_column", "agreement", "agreement_detail", "denominator_as_of", "denominator_record_date", "denominator_gap_days",
    "denominator_confirmed_by", "denominator_disagreement", "denominator_spread",
    "pct_comparable", "pct_reported", "pct_voting_power",
    "as_of_date", "filing_date", "source_form", "confidence",
    "form4_common_shares", "form4_filing_date",
    "flags", "error", "source_url",
]


def _write_csv(records: list[OwnershipRecord], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in records:
            row = r.as_dict()
            row["flags"] = "|".join(row.get("flags") or [])
            w.writerow(row)


def cmd_run(args) -> int:
    tickers: list[str] = []
    ciks: list[int] = []
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if args.ciks:
        ciks = [int(c.strip()) for c in args.ciks.split(",") if c.strip()]
    if args.from_csv:
        with open(args.from_csv, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row.get("cik"):
                    ciks.append(int(row["cik"]))
                elif row.get("ticker"):
                    tickers.append(row["ticker"].strip().upper())
        if args.limit:
            ciks, tickers = ciks[: args.limit], tickers[: args.limit]
    if not tickers and not ciks:
        print("Nothing to do: pass --tickers, --ciks or --from-csv")
        return 1

    records = run_tickers(
        tickers, ciks=ciks,
        as_of=args.as_of, user_agent=args.user_agent, model=args.model,
        llm_mode=args.llm_mode, with_form4=args.with_form4,
        continuity=not args.no_continuity,
    )

    for r in records:
        # Running from a universe CSV means there is no ticker, so fall back
        # to the CIK for a stable label.
        label = r.ticker or (f"CIK{r.cik}" if r.cik else "?")
        if r.error:
            print(f"  {label:<12} ERROR  {r.error[:96]}")
            continue
        pct = f"{r.pct_comparable:.3f}%" if r.pct_comparable is not None else "n/a"
        tag = {"free_path": "FREE", "llm_targeted": "LLM1",
               "llm_extraction": "LLM*"}.get(r.resolution, "    ")
        print(
            f"  {label:<12} {pct:>9}  {r.confidence:<6} {tag} "
            f"{(r.ceo_name or '?')[:24]:<24} "
            f"{(r.company or '')[:22]:<22} "
            f"{('[' + '|'.join(r.flags) + ']') if r.flags else ''}"
        )

    if args.out:
        _write_csv(records, args.out)
        print(f"\nWrote {len(records)} rows -> {args.out}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump([r.as_dict() for r in records], fh, indent=2)
        print(f"Wrote full detail -> {args.json}")
    if args.html:
        write_dashboard([r.as_dict() for r in records], args.html, args.title)
        print(f"Wrote dashboard   -> {args.html}")

    from collections import Counter
    reasons = Counter()
    for r in records:
        if r.error:
            # Collapse to the first clause so distinct failure modes group.
            reasons[r.error.split("--")[-1].strip()[:60]] += 1
    if reasons:
        print("\nFailure modes:")
        for reason, n in reasons.most_common():
            print(f"  {n:>3}x  {reason}")

    flags = Counter()
    for r in records:
        for f in (r.flags or []):
            flags[f.split(":")[0]] += 1
    if flags:
        print("\nFlags:")
        for f, n in flags.most_common(12):
            print(f"  {n:>3}x  {f}")

    high = sum(1 for r in records if r.confidence == "HIGH")
    free = sum(1 for r in records if r.resolution == "free_path")
    paid = sum(1 for r in records
               if r.resolution in ("llm_targeted", "llm_extraction"))
    print(f"\nHIGH confidence: {high}/{len(records)}")
    print(f"Resolved free:   {free}/{len(records)}   (API calls made: {paid})")
    return 0


def cmd_inspect(args) -> int:
    if not args.ticker and not args.cik:
        print("Pass --ticker or --cik")
        return 1
    def _run():
        inspect_ticker(
            ticker=args.ticker.strip().upper() if args.ticker else None,
            cik=int(args.cik) if args.cik else None,
            as_of=args.as_of,
            user_agent=args.user_agent,
            use_llm=not args.no_llm,
            table_index=args.table,
            show_table=args.show_table,
            footnote_chars=args.footnote_chars,
            show_form4=args.show_form4,
        )

    if args.out:
        # Write the file from Python in explicit UTF-8. Shell redirection goes
        # through the console codec, which mangles or rejects proxy glyphs.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _run()
        text = buf.getvalue()
        with open(args.out, "w", encoding="utf-8", errors="replace") as fh:
            fh.write(text)
        print(text[:1500])
        if len(text) > 1500:
            print(f"... full output ({len(text):,} chars) written to {args.out}")
    else:
        _run()
    return 0


def cmd_panel(args) -> int:
    """Run the pipeline across a universe. This is the only path.

    The order of the universe file is the order of the run, unchanged. That
    matters more than it sounds: the working set has to be the SAME hundred
    companies every time, or a hand-checked answer from one run cannot be
    compared with a figure from the next.

    Ranking by market cap was tried and removed. Public float, the only
    SEC-native size signal, is mandated and XBRL-tagged but unvalidated --
    Cabot reports $4.4 quadrillion -- and a quote service brought in a
    dependency whose answers change between runs for reasons unrelated to the
    pipeline.
    """
    ciks: list[int] = []
    tickers: list[str] = []
    seen: set[int] = set()
    with open(args.universe, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            if row.get("cik"):
                c = int(row["cik"])
                if c not in seen:
                    seen.add(c)
                    ciks.append(c)
            elif row.get("ticker"):
                tickers.append(row["ticker"].strip().upper())

    client = EdgarClient(user_agent=args.user_agent)

    if tickers:
        # Resolved through the SEC's own ticker file, so the same list always
        # produces the same companies.
        unresolved = []
        for t in tickers:
            try:
                c = client.resolve_cik(t)
            except KeyError:
                unresolved.append(t)
                continue
            if c not in seen:
                seen.add(c)
                ciks.append(c)
        if unresolved:
            print(f"Could not resolve {len(unresolved)} ticker(s): "
                  f"{', '.join(unresolved)}")

    if args.top:
        ciks = ciks[: args.top]
    if args.second_reader:
        # A flag that silently does nothing is worse than one that stops. The
        # reader failed quietly once already, because a missing key and a
        # disabled reader look identical in the output.
        from .config import SETTINGS
        if not SETTINGS.anthropic_api_key:
            print("--second-reader needs ANTHROPIC_API_KEY. Set it in .env "
                  "or drop the flag.")
            return 1
        try:
            import anthropic  # noqa: F401
        except ImportError:
            print("--second-reader needs the anthropic package: "
                  "python -m pip install anthropic")
            return 1
        print("Second reader: on (model reads each ownership section and "
              "each denominator region)")

    print(f"Working set: {len(ciks)} companies from {args.universe}, "
          f"in the order listed")
    print(f"Checkpoint -> {args.checkpoint}")

    prog = build_panel(
        ciks, checkpoint=args.checkpoint, user_agent=args.user_agent,
        as_of=args.as_of, llm_mode=args.llm_mode, model=args.model,
        continuity=not args.no_continuity,
        skip_non_operating=args.skip_funds,
        second_reader=args.second_reader,
        roll=args.roll,
        redo=args.redo,
    )
    # Only the working set. The checkpoint accumulates every company ever
    # processed against it, so writing all of it made a --top 10 run produce
    # a hundred-row file -- and made a run look like it had done work it had
    # not.
    wanted = set(ciks)
    records = [r for r in panel_records(args.checkpoint)
               if int(r.get("cik") or 0) in wanted]
    extra = len(panel_records(args.checkpoint)) - len(records)
    if extra:
        print(f"({extra} other companies are in {args.checkpoint} from earlier "
              f"runs and are not in this output)")
    if args.out:
        _write_csv_dicts(records, args.out)
        print(f"Wrote panel      -> {args.out}")
    if args.html:
        write_dashboard(records, args.html, args.title)
        print(f"Wrote dashboard  -> {args.html}")
    if args.site:
        write_site(records, args.site, args.site_title)
        print(f"Wrote site       -> {args.site}")
    print(f"\nDone: {prog.ok} with a figure, {prog.errored} without.")
    return 0


def cmd_verify(args) -> int:
    if args.roll:
        records = (panel_records(args.checkpoint) if args.checkpoint
                   else load_records(args.json))
        rows = build_roll_worksheet(records)
        write_roll_worksheet(rows, args.out)
        flagged = sum(1 for r in rows if r["hint"])
        moved = sum(1 for r in rows if r["net_delta"] not in ("0", ""))
        print(f"Wrote roll-forward worksheet -> {args.out} "
              f"({len(rows)} companies, {moved} moved since the proxy, "
              f"{flagged} flagged)")
        return 0

    if args.score:
        print(format_score(score_worksheet(args.score, tolerance=args.tolerance)))
        return 0

    records = (panel_records(args.checkpoint) if args.checkpoint
               else load_records(args.json))
    rows = build_sample(records, include_all=not args.sample_only)
    try:
        preserved = write_worksheet(rows, args.out, force=args.force)
    except WorksheetOpenError as exc:
        print(f"\n{exc}\n")
        return 1

    from collections import Counter
    # The worksheet no longer carries a stratum column. What matters when
    # you sit down to check is how many rows are flagged and why, since
    # those are sorted to the top.
    tally = Counter((r.get("hint") or "").split(";")[0].strip() or "no flag"
                    for r in rows)
    print(f"Wrote worksheet -> {args.out}  ({len(rows)} companies)")
    if preserved:
        print(f"Carried forward {preserved} row(s) you had already checked.")
    counts = answer_counts(args.out)
    if any(counts.values()):
        print("Checked so far:")
        for col, n in counts.items():
            if n:
                print(f"    {n:>4}  {col}")
    for name, n in tally.most_common():
        print(f"  {n:>3}  {name}")
    print("\nOpen each source_url, find the ownership table, and fill in")
    print("actual_ceo_name and actual_shares. Then:")
    print(f"  python -m ceo_ownership.cli verify --score {args.out}")
    return 0


def _write_csv_dicts(records: list[dict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in records:
            r = dict(r)
            r["flags"] = "|".join(r.get("flags") or [])
            w.writerow(r)


def cmd_triage(args) -> int:
    records = (panel_records(args.checkpoint) if args.checkpoint
               else load_records(args.json))
    report = triage(records)
    print(report)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"Wrote triage -> {args.out}")
    return 0


def cmd_site(args) -> int:
    records = (panel_records(args.checkpoint) if args.checkpoint
               else load_records(args.json))
    write_site(records, args.out, args.title)
    usable = sum(1 for r in records
                 if r.get("pct_comparable") and not r.get("error"))
    print(f"Wrote site -> {args.out}  ({usable} companies with a figure)")
    return 0


def cmd_dashboard(args) -> int:
    records = load_records(args.json)
    write_dashboard(records, args.out, args.title)
    print(f"Wrote dashboard -> {args.out}  ({len(records)} rows)")
    return 0


def cmd_universe(args) -> int:
    client = EdgarClient(user_agent=args.user_agent)
    rows = proxy_filers(client, args.year, args.quarter)
    print(f"{len(rows)} proxy filers in {args.year}"
          + (f" Q{args.quarter}" if args.quarter else ""))
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(
                fh,
                fieldnames=["cik", "company", "form_type", "date_filed",
                            "accession", "document_path"],
            )
            w.writeheader()
            for r in rows:
                w.writerow(r.as_dict())
        print(f"Wrote -> {args.out}")
    return 0


def cmd_exits(args) -> int:
    client = EdgarClient(user_agent=args.user_agent)
    rows = find_exits(client, args.year)
    print(f"{len(rows)} delisting/deregistration notices in {args.year}")
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(
                fh,
                fieldnames=["cik", "company", "date_filed", "form_type",
                            "exit_kind", "exit_reason"],
            )
            w.writeheader()
            w.writerows(rows)
        print(f"Wrote -> {args.out}")
    return 0


def _force_utf8_stdout() -> None:
    """Windows consoles default to cp1252, which cannot encode characters that
    appear routinely in proxies (checkbox glyphs, en dashes, curly quotes).
    Without this, printing a filing crashes with UnicodeEncodeError."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass


def main(argv=None) -> int:
    _force_utf8_stdout()
    p = argparse.ArgumentParser(prog="ceo-ownership")
    p.add_argument(
        "--user-agent",
        default=None,
        help="SEC requires 'Name email'. Or set OWNERSHIP_UA.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="Extract CEO ownership for tickers")
    r.add_argument("--tickers", default=None, help="Comma-separated, e.g. AAPL,META")
    r.add_argument("--ciks", default=None,
                   help="Comma-separated CIKs -- use for companies whose "
                        "ticker does not resolve (delisted, OTC, funds)")
    r.add_argument("--from-csv", default=None,
                   help="Read a 'cik' (or 'ticker') column from this CSV, e.g. "
                        "the output of the universe command")
    r.add_argument("--limit", type=int, default=None,
                   help="Process at most N companies from --from-csv")
    r.add_argument("--as-of", default=None,
                   help="YYYY-MM-DD filing-date cutoff (point-in-time)")
    r.add_argument("--model", default=None,
                   help="Extraction model. Try claude-haiku-4-5-20251001 to cut cost.")
    r.add_argument("--no-continuity", action="store_true",
                   help="Skip the year-over-year check (saves one proxy fetch)")
    r.add_argument("--with-form4", action="store_true",
                   help="Also fetch Form 4 as an informational cross-check "
                        "(slow; reports under a different legal standard)")
    r.add_argument("--llm-mode", default="auto", choices=["auto", "always", "never"],
                   help="auto (default): free path first, pay only where ambiguous. "
                        "never: free path only, zero cost. always: skip the router.")
    r.add_argument("--out", default=None, help="CSV output path")
    r.add_argument("--json", default=None, help="JSON output path (full detail)")
    r.add_argument("--html", default=None,
                   help="Write a self-contained HTML review page here")
    r.add_argument("--title", default="CEO ownership",
                   help="Heading for the HTML page")
    r.set_defaults(func=cmd_run)

    i = sub.add_parser("inspect", help="Debug one company: tables, Form 4, extraction")
    i.add_argument("--ticker", default=None)
    i.add_argument("--cik", "--ciks", dest="cik", default=None,
                   help="Inspect by CIK. Most panel rows have no ticker.")
    i.add_argument("--as-of", default=None)
    i.add_argument("--no-llm", action="store_true",
                   help="Skip extraction (free, no API call)")
    i.add_argument("--table", type=int, default=0,
                   help="Which candidate table to extract (default 0)")
    i.add_argument("--show-table", action="store_true",
                   help="Print the located table and its footnotes as text")
    i.add_argument("--footnote-chars", type=int, default=2500,
                   help="How much footnote context to print with --show-table")
    i.add_argument("--show-form4", action="store_true",
                   help="Print the CEO's raw Form 4 ownership XML")
    i.add_argument("--out", default=None,
                   help="Write output to this file as UTF-8 (avoids Windows "
                        "console encoding errors from shell redirection)")
    i.set_defaults(func=cmd_inspect)

    pa = sub.add_parser("panel", help="Run the pipeline across a universe, resumably")
    pa.add_argument("--universe", required=True,
                    help="CSV with a 'cik' or 'ticker' column. Use "
                         "working_set.csv for the fixed hundred, or the "
                         "output of the universe command for everything.")
    pa.add_argument("--checkpoint", default="panel.jsonl",
                    help="Append-as-you-go results file; rerun to resume")
    pa.add_argument("--top", type=int, default=None,
                    help="Process only the N largest companies. Omit to run "
                         "the whole universe.")
    pa.add_argument("--redo", default="none", choices=["none", "failed", "all"],
                    help="Reprocess after a fix: 'failed' retries error rows, "
                         "'all' ignores the checkpoint entirely")
    pa.add_argument("--as-of", default=None)
    pa.add_argument("--llm-mode", default="never",
                    choices=["auto", "always", "never"])
    pa.add_argument("--model", default=None)
    pa.add_argument("--no-continuity", action="store_true")
    pa.add_argument("--second-reader", action="store_true",
                    help="Have a model read the same ownership section "
                         "independently and compare. Roughly a cent per "
                         "company, cached by document, and the only check "
                         "that is not our own reading checked against "
                         "itself.")
    pa.add_argument("--roll", action="store_true",
                    help="Carry each proxy figure forward with Form 4 deltas "
                         "and the latest cover-page share count. Both legs "
                         "are structured data, so this costs nothing.")
    pa.add_argument("--skip-funds", action="store_true",
                    help="Skip filers positively identified as registered "
                         "investment companies (N-CSR/N-CEN). Off by default: "
                         "every filer is processed and classified with a "
                         "filer_kind flag, so nothing is excluded unseen.")
    pa.add_argument("--out", default=None, help="CSV of the panel so far")
    pa.add_argument("--html", default=None)
    pa.add_argument("--title", default="CEO ownership panel")
    pa.add_argument("--site", default=None,
                    help="Write the public-facing analytics page here")
    pa.add_argument("--site-title", default="Skin in the Game")
    pa.set_defaults(func=cmd_panel)

    v = sub.add_parser("verify", help="Stratified hand-check worksheet, and scoring")
    v.add_argument("--checkpoint", default=None, help="A panel .jsonl file")
    v.add_argument("--json", default=None, help="Or a --json file from a run")
    v.add_argument("--out", default="verification_worksheet.csv")
    v.add_argument("--roll", action="store_true",
                   help="Build the roll-forward worksheet instead: anchor, "
                        "delta and result, for checking that a CHANGE is real")
    v.add_argument("--sample-only", action="store_true",
                   help="Draw the stratified 100-row sample instead of "
                        "listing every company")
    v.add_argument("--force", action="store_true",
                   help="Write even if the worksheet looks open in Excel, or "
                        "if the new sheet would hold fewer answers")
    v.add_argument("--score", default=None,
                   help="Score a filled-in worksheet instead of sampling")
    v.add_argument("--tolerance", type=float, default=0.005,
                   help="Relative difference treated as a match (default 0.5%%)")
    v.set_defaults(func=cmd_verify)

    tr = sub.add_parser("triage", help="Group a run's failures by signature")
    tr.add_argument("--checkpoint", default=None, help="A panel .jsonl file")
    tr.add_argument("--json", default=None, help="Or a --json file from a run")
    tr.add_argument("--out", default="triage.txt")
    tr.set_defaults(func=cmd_triage)

    si = sub.add_parser("site", help="Build the public analytics page")
    si.add_argument("--checkpoint", default=None, help="A panel .jsonl file")
    si.add_argument("--json", default=None, help="Or a --json file from a run")
    si.add_argument("--out", default="index.html")
    si.add_argument("--title", default="Skin in the Game")
    si.set_defaults(func=cmd_site)

    d = sub.add_parser("dashboard", help="Build the HTML page from a saved JSON")
    d.add_argument("--json", required=True, help="A --json file from a run")
    d.add_argument("--out", default="dashboard.html")
    d.add_argument("--title", default="CEO ownership")
    d.set_defaults(func=cmd_dashboard)

    u = sub.add_parser("universe", help="Survivorship-free proxy-filer universe")
    u.add_argument("--year", type=int, required=True)
    u.add_argument("--quarter", type=int, default=None, choices=[1, 2, 3, 4])
    u.add_argument("--out", default=None)
    u.set_defaults(func=cmd_universe)

    e = sub.add_parser("exits", help="Delisting/deregistration notices for a year")
    e.add_argument("--year", type=int, required=True)
    e.add_argument("--out", default=None)
    e.set_defaults(func=cmd_exits)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
