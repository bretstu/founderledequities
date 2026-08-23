"""Command line interface."""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import sys
from datetime import date

from .edgar import EdgarClient
from .dashboard import load_records, write_dashboard
from .inspect import inspect_ticker
from .pipeline import run_tickers, OwnershipRecord
from .universe import proxy_filers, find_exits

CSV_COLUMNS = [
    "ticker", "cik", "company", "sic_description", "ceo_name", "ceo_source", "ceo_identity_source", "ceo_identity_evidence", "peo_names",
    "resolution", "escalation_reason",
    "shares_13d3", "shares_source", "column_used", "options_60d", "options_60d_implied", "prior_year_shares", "yoy_change_pct",
    "shares_outstanding", "share_class_count", "denominator_source",
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
    def _run():
        inspect_ticker(
            args.ticker.strip().upper(),
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
    i.add_argument("--ticker", required=True)
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
