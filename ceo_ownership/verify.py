"""Stratified verification: measure accuracy instead of estimating it.

Two checks run automatically. `pct_reconciliation` proves the share count and
the denominator are mutually consistent, but only where the filer printed a
real percentage -- most CEOs hold under 1% and their row shows an asterisk.
`yoy_continuity` covers the rest, but it proves STABILITY, not correctness: a
column misread the same way in both years passes cleanly.

That residual -- consistent error -- is invisible to the pipeline by
construction, and the only way to measure it is to read filings by hand.

Sampling randomly wastes the effort. Roughly seventy of a random hundred would
land on rows the reconciliation already proved, teaching you almost nothing.
So the sample is stratified by what each row's automatic checks could NOT
establish, with the largest allocation going to rows that passed on continuity
alone.

Workflow:
    1. `sample` writes a worksheet CSV, one row per company to check
    2. you open each source_url, find the table, fill in actual_shares
    3. `score` diffs your entries against the pipeline and reports accuracy
"""
from __future__ import annotations

import csv
import os
import random
from dataclasses import dataclass

# (name, description, how many to draw)
DEFAULT_PLAN = [
    ("reconciled", "HIGH, percentage reconciled -- confirms the check itself", 10),
    ("continuity_only", "HIGH on continuity alone -- the real blind spot", 30),
    ("flagged", "MEDIUM or carrying flags -- where errors should cluster", 20),
    ("top_ownership", "largest holdings -- the thesis, most scrutiny", 25),
    ("failed", "LOW or errored -- confirm failures really are failures", 15),
]

# What a person needs to check one company, and nothing else.
#
# This grew to 46 columns, one per debugging round, and became unusable for
# the task it exists for: open a filing, read two numbers, type them in.
# Diagnostics belong in the panel CSV and the triage report; the worksheet is
# for reading filings.
WORKSHEET_COLUMNS = [
    "company",          # who
    "ceo_name",         # who to look for in the table
    "source_url",       # the filing itself
    "hint",             # what tends to go wrong here, if anything
    # Both readings, always, side by side. Labels say who produced each:
    # "our_" was ambiguous, because the reported denominator is usually the
    # model's and the column read as though it were not.
    "reported_shares",  # what the dashboard would publish
    "source",           # which reader produced it
    "parser_shares",    # the free cross-check
    "llm_shares",
    "llm_note",         # why, when the model returned nothing
    "parser_outstanding",
    "llm_outstanding",
    "reported_pct",     # the figure the dashboard would publish
    # --- you fill these in ---
    "actual_shares",
    "actual_outstanding",
    "notes",
    "cik",              # last: needed to match rows, not to read
]

# Kept out of the worksheet but still worth surfacing as a hint, because
# they say what to look at before opening the filing.
_HINTS = {
    "readers_disagree": "two readers disagree -- check this one",
    "denominator_disagrees_over_5pct": "denominator disputed",
    "denominator_from_whole_document": "share count found by scanning; verify it",
    "ceo_appointed_after_proxy": "CEO may postdate this proxy",
    "proxy_reports_voting_classes_only": "table omits non-voting classes",
    "shares_from_form4_not_proxy": "figure came from Form 4, not the proxy",
    "table_chosen_by_ceo_name": "several ownership tables; picked by name",
    "ceo_not_in_any_candidate_table": "CEO not found in any table",
    "yoy_discontinuity": "large change since last year",
    "multi_class": "multiple share classes -- sum them",
}



# ---------------------------------------------------------------------------
# Protecting hand-entered work, without leaving files behind.
#
# Answers were lost twice: once because Excel held unsaved edits that were
# never on disk, and once because the guard meant to detect the loss counted
# answers using the same reader that had just failed to find them -- it
# compared zero against zero, saw no loss, and wrote.
#
# The response was backup copies and a shadow answers file. Both are gone:
# neither addressed the first failure (nothing can recover data that never
# reached disk), and they cluttered the working directory. What remains are
# the two guards that write nothing -- refuse to run while the file is open,
# and refuse to write a sheet holding fewer answers than the one on disk.
# ---------------------------------------------------------------------------

HAND_ENTERED = ("actual_shares", "actual_outstanding", "notes")


class WorksheetOpenError(RuntimeError):
    """The worksheet is open, or rewriting it would lose answers."""


def excel_lock_file(path: str) -> str | None:
    """Excel writes ~$name.csv while a file is open, which means there may be
    edits in memory that are not on disk."""
    d, name = os.path.split(os.path.abspath(path))
    lock = os.path.join(d, "~$" + name)
    return lock if os.path.exists(lock) else None


def _parse_cik(raw) -> int | None:
    """Excel may write a long integer as "1.32166E+06" or "1321655.0", and a
    plain int() raises on both -- which skipped the row in silence."""
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return int(float(text))
    except (ValueError, OverflowError):
        return None


def raw_answer_count(path: str) -> int:
    """Count filled answers by reading the file as text -- deliberately
    independent of the CSV parsing, because a guard sharing a code path with
    the failure it guards cannot detect that path failing."""
    if not os.path.exists(path):
        return 0
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            header = fh.readline()
            cols = [c.strip().strip('"') for c in header.split(",")]
            if "actual_shares" not in cols:
                return 0
            i = cols.index("actual_shares")
            n = 0
            for line in fh:
                parts = next(csv.reader([line]), [])
                if len(parts) > i and parts[i].strip():
                    n += 1
            return n
    except OSError:
        return 0


def load_hand_entered(path: str) -> dict[int, dict]:
    kept: dict[int, dict] = {}
    if not os.path.exists(path):
        return kept
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            cik = _parse_cik(row.get("cik"))
            entered = {k: (row.get(k) or "").strip() for k in HAND_ENTERED}
            if cik and any(entered.values()):
                kept[cik] = entered
    return kept


def load_hand_entered(path: str) -> dict[int, dict]:
    kept: dict[int, dict] = {}
    if not os.path.exists(path):
        return kept
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            cik = _parse_cik(row.get("cik"))
            entered = {k: (row.get(k) or "").strip() for k in HAND_ENTERED}
            if cik and any(entered.values()):
                kept[cik] = entered
    return kept


@dataclass
class Stratum:
    name: str
    description: str
    target: int


def _checks(record: dict) -> dict[str, bool | None]:
    out: dict[str, bool | None] = {}
    for c in (record.get("validation") or {}).get("checks", []):
        out[c.get("name")] = c.get("passed")
    return out


def assign_stratum(record: dict) -> str:
    """Which stratum does this row belong to? First match wins."""
    if record.get("error") or record.get("confidence") == "LOW":
        return "failed"
    checks = _checks(record)
    recon = checks.get("pct_reconciliation")
    cont = checks.get("yoy_continuity")

    if record.get("confidence") == "HIGH" and recon is True:
        return "reconciled"
    if record.get("confidence") == "HIGH" and recon is None and cont is True:
        # Passed on continuity alone: the share count was never checked
        # against an independent statement of it.
        return "continuity_only"
    if record.get("confidence") != "HIGH" or record.get("flags"):
        return "flagged"
    return "continuity_only"


def _num_str(v) -> str:
    return f"{v:.0f}" if isinstance(v, (int, float)) else ""


def build_sample(
    records: list[dict],
    plan: list[tuple[str, str, int]] | None = None,
    seed: int = 20260823,
    include_all: bool = False,
) -> list[dict]:
    """Draw a stratified sample, plus the top holdings by ownership.

    With include_all, every company is listed and the strata only determine
    the ORDER -- most-informative first. At a hundred companies the sample
    is nearly the whole panel anyway, and deciding what to skip is better
    done while looking at the rows than by a quota.
    """
    plan = plan or DEFAULT_PLAN
    rng = random.Random(seed)

    buckets: dict[str, list[dict]] = {name: [] for name, _, _ in plan}
    for r in records:
        buckets.setdefault(assign_stratum(r), []).append(r)

    chosen: list[tuple[str, dict]] = []
    taken: set[int] = set()

    # Top-ownership rows are picked deliberately, not sampled: these carry the
    # thesis and deserve scrutiny regardless of which stratum they fall in.
    top_n = next((n for name, _, n in plan if name == "top_ownership"), 0)
    ranked = sorted(
        (r for r in records if isinstance(r.get("pct_comparable"), (int, float))),
        key=lambda r: -(r.get("pct_comparable") or 0),
    )
    for r in ranked[:top_n]:
        chosen.append(("top_ownership", r))
        taken.add(int(r.get("cik") or 0))

    for name, _desc, target in plan:
        if name == "top_ownership":
            continue
        pool = [r for r in buckets.get(name, []) if int(r.get("cik") or 0) not in taken]
        rng.shuffle(pool)
        for r in (pool if include_all else pool[:target]):
            chosen.append((name, r))
            taken.add(int(r.get("cik") or 0))

    if include_all:
        # Anything not captured by a stratum still belongs on the sheet.
        for r in records:
            cik = int(r.get("cik") or 0)
            if cik and cik not in taken:
                chosen.append((assign_stratum(r), r))
                taken.add(cik)

    rows = []
    for stratum, r in chosen:
        pct = r.get("pct_comparable")
        out = r.get("shares_outstanding")
        shares = r.get("shares_13d3")

        # One short hint, chosen from the flags, so the checker knows what to
        # look for before opening the filing.
        hint = ""
        # A precise error outranks a general flag. Disney's CEO was
        # certified after the proxy was written, which is a different fact
        # from "not found in any table" and needs no investigation.
        if "ceo_appointed_after_proxy" in (r.get("flags") or []):
            hint = "CEO appointed after this proxy -- no row to find"
        for flag in ([] if hint else (r.get("flags") or [])):
            key = flag.split(":")[0]
            if key in _HINTS:
                hint = _HINTS[key]
                break
        if not hint and r.get("error"):
            hint = (r["error"].split("--")[0].strip())[:60]
        if r.get("agreement") == "disagree":
            col = (r.get("model_column") or "")[:40]
            hint = f"readers differ; model took {col!r}" if col else \
                   "two readers disagree -- check this one"

        rows.append({
            # Never blank: a row with no company name is unidentifiable in a
            # spreadsheet.
            "company": (r.get("company") or r.get("ticker")
                        or f"(CIK {r.get('cik')} -- no filing found)"),
            "ceo_name": r.get("ceo_name") or "",
            "source_url": r.get("source_url") or "",
            "hint": hint,
            "reported_shares": _num_str(shares),
            "source": {"llm_table_read": "llm",
                       "proxy_item403": "parser",
                       "form4_all_classes": "form 4"}.get(
                           r.get("shares_source") or "", ""),
            "parser_shares": _num_str(r.get("parser_shares")),
            # Always shown, never only on disagreement: a blank previously
            # meant either "they agreed" or "it never ran", which are not the
            # same thing at all.
            # A blank meant four different things -- never called, called
            # and found nothing, errored, or not applicable -- which needed
            # four different responses and looked identical.
            "llm_shares": (
                _num_str(r.get("model_shares")) if r.get("model_shares")
                else {"neither": "none found",
                      "parser_only": "declined",
                      "not_compared": "not run"}.get(
                          r.get("agreement") or "", "not run"
                          if r.get("shares_13d3") is not None else "")),
            "llm_note": (r.get("model_note") or "")[:70],
            "parser_outstanding": _num_str(r.get("parser_outstanding")),
            "llm_outstanding": _num_str(r.get("llm_outstanding")),
            "reported_pct": f"{pct:.3f}%" if isinstance(pct, (int, float)) else "",
            "actual_shares": "",
            "actual_outstanding": "",
            "notes": "",
            "cik": r.get("cik"),
        })
    # Most informative first: disagreements and flags, then everything else.
    rows.sort(key=lambda x: (0 if x["hint"] else 1, x["company"]))
    return rows


def write_worksheet(rows: list[dict], path: str, force: bool = False) -> int:
    """Write the worksheet, carrying forward any checks already done.

    Regenerating must never destroy manual work -- hours of reading filings
    would be lost to one command. Hand-entered columns are merged back in by
    CIK; the pipeline's own columns are refreshed, so after a parser fix you
    can re-score against the same answers and watch accuracy move without
    re-checking a single company.

    Returns how many previously-checked rows were preserved.
    """
    # Refuse to touch a file that is open. Edits sitting in Excel are not on
    # disk, so rewriting the file discards them and no merge can bring them
    # back. This is the failure the guard exists for.
    lock = excel_lock_file(path)
    if lock and not force:
        raise WorksheetOpenError(
            f"{os.path.basename(path)} appears to be open in Excel.\n"
            f"Close it and save first -- anything typed but not saved is not "
            f"on disk, and regenerating would lose it.\n"
            f"(Lock file: {os.path.basename(lock)}. Use --force to override.)"
        )

    previous = load_hand_entered(path)
    preserved = 0
    for row in rows:
        try:
            cik = int(row.get("cik") or 0)
        except (TypeError, ValueError):
            continue
        if cik in previous:
            row.update({k: v for k, v in previous[cik].items() if v})
            preserved += 1

    # A rewrite must never record less than the file already held.
    #    Counted from the raw text, NOT from the parsed result -- if parsing
    #    is what failed, a parsed count would agree with itself and wave the
    #    loss through. That is exactly what happened twice.
    before = max(raw_answer_count(path),
                 sum(1 for v in previous.values() if v.get("actual_shares")))
    after = sum(1 for r in rows if str(r.get("actual_shares") or "").strip())
    if before and after < before and not force:
        raise WorksheetOpenError(
            f"Refusing to write: the existing worksheet holds {before} share "
            f"count(s) and the new one would hold {after}.\n"
            f"Nothing has been changed -- your file is untouched.\n"
            f"This usually means the answers could not be read back. Copy "
            f"the file somewhere safe, or use --force to overwrite anyway."
        )

    # Atomic: write beside the target, then replace, so an interrupted run
    # cannot leave a half-written worksheet.
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=WORKSHEET_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)
    return preserved


def answer_counts(path: str) -> dict[str, int]:
    """How many values are held per column, so a partial loss is obvious."""
    entered = load_hand_entered(path)
    return {k: sum(1 for v in entered.values() if v.get(k))
            for k in HAND_ENTERED}


# ------------------------------------------------------------------ scoring


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def score_worksheet(path: str, tolerance: float = 0.005) -> dict:
    """Compare hand-checked values against the pipeline.

    `tolerance` is relative: 0.005 allows a half-percent difference, which
    absorbs a record-date mismatch without hiding a wrong column.
    """
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    per_stratum: dict[str, dict] = {}
    mismatches: list[dict] = []
    checked = 0

    for r in rows:
        actual = _num(r.get("actual_shares"))
        if actual is None:
            continue  # not yet checked
        checked += 1
        stratum = "flagged" if (r.get("hint") or "").strip() else "clean"
        st = per_stratum.setdefault(
            stratum, {"checked": 0, "match": 0, "wrong_number": 0,
                      "wrong_person": 0, "wrong_denominator": 0}
        )
        st["checked"] += 1

        pipeline = _num(r.get("parser_shares"))
        if pipeline is None:
            st["wrong_number"] += 1
            mismatches.append({**r, "issue": "pipeline had no figure"})
            continue

        # A denominator that disagrees makes the percentage wrong even when
        # the share count is right, so check it when it was recorded.
        act_out = _num(r.get("actual_outstanding"))
        pipe_out = _num(r.get("parser_outstanding")) or _num(r.get("llm_outstanding"))
        if act_out and pipe_out:
            drel = abs(pipe_out - act_out) / max(act_out, 1.0)
            if drel > tolerance:
                st.setdefault("wrong_denominator", 0)
                st["wrong_denominator"] += 1
                mismatches.append({
                    **r, "issue": f"denominator off by {drel:.1%} "
                                  f"(pipeline {pipe_out:,.0f} vs "
                                  f"actual {act_out:,.0f})"})

        rel = abs(pipeline - actual) / max(actual, 1.0)
        if rel <= tolerance:
            st["match"] += 1
        else:
            st["wrong_number"] += 1
            mismatches.append({
                **r, "issue": f"off by {rel:.1%} "
                              f"(pipeline {pipeline:,.0f} vs actual {actual:,.0f})"
            })

    total_match = sum(s["match"] for s in per_stratum.values())
    return {
        "checked": checked,
        "unchecked": len(rows) - checked,
        "accuracy": (total_match / checked) if checked else None,
        "per_stratum": per_stratum,
        "mismatches": mismatches,
    }


def format_score(result: dict) -> str:
    lines = []
    acc = result["accuracy"]
    lines.append(f"Checked {result['checked']} of "
                 f"{result['checked'] + result['unchecked']} sampled rows")
    if acc is None:
        lines.append("Nothing scored yet -- fill in actual_shares first.")
        return "\n".join(lines)

    lines.append(f"Overall accuracy: {acc:.1%}")
    lines.append("")
    lines.append(f"  {'stratum':<18} {'checked':>8} {'match':>7} "
                 f"{'bad #':>7} {'bad who':>8} {'bad denom':>10}  rate")
    for name, s in sorted(result["per_stratum"].items()):
        rate = s["match"] / s["checked"] if s["checked"] else 0
        lines.append(f"  {name:<18} {s['checked']:>8} {s['match']:>7} "
                     f"{s['wrong_number']:>7} {s['wrong_person']:>8} "
                     f"{s.get('wrong_denominator', 0):>10}  {rate:.0%}")

    if result["mismatches"]:
        lines.append("")
        lines.append("Mismatches:")
        for m in result["mismatches"][:25]:
            lines.append(f"  CIK{m.get('cik')} {(m.get('company') or '')[:34]:<34} "
                         f"{m['issue']}")
            if m.get("notes"):
                lines.append(f"      note: {m['notes']}")
    else:
        lines.append("\nNo mismatches among checked rows.")

    lines.append("")
    lines.append("The continuity_only rate is the number that matters most: "
                 "those rows had no independent check on the share count, so "
                 "they are where consistent error would hide.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Checking the roll-forward.
#
# A different question from checking a proxy. There, you open one filing and
# read one number. Here the anchor is already verified and what needs
# checking is whether the CHANGE is real: did the pipeline apply the right
# transactions, in the right direction, and leave out the ones that were
# already counted?
#
# So the worksheet is arranged around the arithmetic -- anchor, delta, result
# -- with a link to the insider's Form 4 history rather than to a proxy. The
# question for each row is "does this add up", not "what does the table say".
# ---------------------------------------------------------------------------

ROLL_COLUMNS = [
    "company",
    "ceo_name",
    "anchor_shares",        # verified proxy figure
    "anchor_date",
    "net_delta",            # what the Form 4s added up to
    "txn_count",
    "rolled_shares",        # anchor + delta
    "rolled_pct",
    "numerator_as_of",
    "denominator_as_of",
    "gap_days",             # how far apart the two legs are
    "buyback_pace",         # what that gap is likely to cost
    "form4_url",            # every Form 4 for this filer
    "hint",
    # --- you fill these in ---
    "actual_delta",
    "notes",
    "cik",
]

ROLL_HAND_ENTERED = ("actual_delta", "notes")


def build_roll_worksheet(records: list[dict]) -> list[dict]:
    rows = []
    for r in records:
        if r.get("rolled_shares") is None:
            continue
        delta = r.get("rolled_net_delta") or 0
        gap = r.get("rolled_gap_days")
        pace = r.get("buyback_pace")

        hint = ""
        if delta and r.get("anchor_shares" ) is None and r.get("shares_13d3"):
            pass
        if delta:
            base = r.get("shares_13d3") or 1
            if abs(delta) / max(base, 1) > 0.25:
                hint = f"holding moved {delta / base:+.0%} since the proxy"
        if not hint and "rolled_neutral_codes_present" in (r.get("flags") or []):
            hint = "has exercises or grants treated as neutral -- verify"
        if not hint and gap and gap > 120:
            hint = f"denominator {gap} days behind the numerator"
        if not hint and pace and abs(pace) > 0.02:
            hint = f"share count moved {pace:+.1%} last quarter"

        rows.append({
            # Never blank: a row with no company name is unidentifiable in a
            # spreadsheet.
            "company": (r.get("company") or r.get("ticker")
                        or f"(CIK {r.get('cik')} -- no filing found)"),
            "ceo_name": r.get("ceo_name") or "",
            "anchor_shares": _num_str(r.get("shares_13d3")),
            "anchor_date": r.get("filing_date") or "",
            "net_delta": _num_str(delta) if delta else "0",
            "txn_count": r.get("rolled_txn_count") or 0,
            "rolled_shares": _num_str(r.get("rolled_shares")),
            "rolled_pct": (f"{r['rolled_pct']:.3f}%"
                           if isinstance(r.get("rolled_pct"), (int, float)) else ""),
            "numerator_as_of": r.get("numerator_as_of") or "",
            "denominator_as_of": r.get("rolled_denominator_as_of") or "",
            "gap_days": gap if gap is not None else "",
            "buyback_pace": f"{pace:+.2%}" if isinstance(pace, float) else "",
            "form4_url": (f"https://www.sec.gov/cgi-bin/browse-edgar?action="
                          f"getcompany&CIK={r.get('cik')}&type=4&dateb=&owner="
                          f"include&count=40"),
            "hint": hint,
            "actual_delta": "",
            "notes": "",
            "cik": r.get("cik"),
        })
    rows.sort(key=lambda x: (0 if x["hint"] else 1, x["company"]))
    return rows


def write_roll_worksheet(rows: list[dict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ROLL_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
