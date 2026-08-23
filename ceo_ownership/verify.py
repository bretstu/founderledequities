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

WORKSHEET_COLUMNS = [
    # Filled in by the sampler
    "stratum", "cik", "ticker", "company", "ceo_name",
    "pipeline_shares", "pipeline_pct", "column_used", "confidence",
    "flags", "source_url",
    # Filled in by you, reading the filing
    "actual_ceo_name", "actual_shares", "actual_outstanding", "verdict", "notes",
]


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


def build_sample(
    records: list[dict],
    plan: list[tuple[str, str, int]] | None = None,
    seed: int = 20260823,
) -> list[dict]:
    """Draw a stratified sample, plus the top holdings by ownership."""
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
        for r in pool[:target]:
            chosen.append((name, r))
            taken.add(int(r.get("cik") or 0))

    rows = []
    for stratum, r in chosen:
        pct = r.get("pct_comparable")
        rows.append({
            "stratum": stratum,
            "cik": r.get("cik"),
            "ticker": r.get("ticker") or "",
            "company": r.get("company") or "",
            "ceo_name": r.get("ceo_name") or "",
            "pipeline_shares": r.get("shares_13d3") or "",
            "pipeline_pct": f"{pct:.4f}" if isinstance(pct, (int, float)) else "",
            "column_used": (r.get("column_used") or "").replace("column=", ""),
            "confidence": r.get("confidence") or "",
            "flags": "|".join(r.get("flags") or []),
            "source_url": r.get("source_url") or "",
            "actual_ceo_name": "",
            "actual_shares": "",
            "actual_outstanding": "",
            "verdict": "",
            "notes": "",
        })
    return rows


def write_worksheet(rows: list[dict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=WORKSHEET_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


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
        stratum = r.get("stratum") or "unknown"
        st = per_stratum.setdefault(
            stratum, {"checked": 0, "match": 0, "wrong_number": 0, "wrong_person": 0}
        )
        st["checked"] += 1

        actual_name = (r.get("actual_ceo_name") or "").strip()
        pipeline_name = (r.get("ceo_name") or "").strip()
        if actual_name and pipeline_name:
            from .validate import names_match
            if names_match(actual_name, pipeline_name) < 0.7:
                st["wrong_person"] += 1
                mismatches.append({**r, "issue": "wrong person"})
                continue

        pipeline = _num(r.get("pipeline_shares"))
        if pipeline is None:
            st["wrong_number"] += 1
            mismatches.append({**r, "issue": "pipeline had no figure"})
            continue

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
                 f"{'bad #':>7} {'bad who':>8}  rate")
    for name, s in sorted(result["per_stratum"].items()):
        rate = s["match"] / s["checked"] if s["checked"] else 0
        lines.append(f"  {name:<18} {s['checked']:>8} {s['match']:>7} "
                     f"{s['wrong_number']:>7} {s['wrong_person']:>8}  {rate:.0%}")

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
