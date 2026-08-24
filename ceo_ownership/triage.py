"""Group a panel run's problems by signature, so the next fix is obvious.

A 100-company run produces 100 individual stories. What matters is which of
them are the same story: five companies failing for one reason is a bug worth
fixing, five failing for five reasons is the long tail.

So this collapses errors and failed checks into signatures, counts them,
names examples, and emits the exact `inspect` command to diagnose each. The
output is small enough to read in full and to hand to someone else.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict


def _signature(text: str) -> str:
    """Reduce an error message to its recurring shape.

    Company-specific detail -- names, counts, scores -- is what makes two
    instances of one bug look like two bugs, so it is stripped out.
    """
    t = (text or "").strip()
    t = t.split("--", 1)[1].strip() if "--" in t else t
    t = re.sub(r"'[^']*'", "'X'", t)
    t = re.sub(r"\b\d[\d,\.]*\b", "N", t)
    return t[:88]


def _failed_checks(record: dict) -> list[tuple[str, str]]:
    out = []
    for c in (record.get("validation") or {}).get("checks", []):
        if c.get("passed") is False:
            out.append((c.get("name") or "?", c.get("detail") or ""))
    return out


def triage(records: list[dict], examples: int = 3) -> str:
    lines: list[str] = []
    n = len(records)
    # `is not None`, not truthiness: a CEO owning exactly zero shares is a
    # real answer, and treating it as "no figure" made the counts disagree
    # with the failure groups.
    with_figure = [r for r in records if r.get("shares_13d3") is not None]
    errored = [r for r in records if r.get("error")]
    no_name = [r for r in records if not r.get("ceo_name")]
    zero_holders = [r for r in records if r.get("shares_13d3") == 0]

    conf = Counter(r.get("confidence") for r in records)
    lines.append("=" * 74)
    lines.append(f"PANEL TRIAGE  ({n} companies)")
    lines.append("=" * 74)
    lines.append(f"  with a figure : {len(with_figure)}"
                 + (f"  (of which {len(zero_holders)} own zero shares)"
                    if zero_holders else ""))
    lines.append(f"  no figure     : {n - len(with_figure)}")
    # Two very different failures. Without a name we never had a chance;
    # with a name but no row, we looked in the wrong table.
    lines.append(f"  no CEO name   : {len(no_name)}"
                 + ("   <- identity itself failed" if no_name else "   (identity resolved for every company)"))
    lines.append(f"  confidence    : " + "  ".join(
        f"{k}={v}" for k, v in sorted(conf.items(), key=lambda kv: str(kv[0]))))

    # ---- errors, grouped -------------------------------------------------
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in errored:
        groups[_signature(r["error"])].append(r)

    if groups:
        lines.append("")
        lines.append("-" * 74)
        lines.append("FAILURES BY SIGNATURE  (fix the biggest group first)")
        lines.append("-" * 74)
        for sig, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            lines.append(f"\n  [{len(rs)}x] {sig}")
            for r in rs[:examples]:
                lines.append(f"      CIK{r.get('cik')}  "
                             f"{(r.get('company') or '')[:44]}")
                raw = (r.get("error") or "")
                if "--" in raw:
                    lines.append(f"          {raw.split('--', 1)[1].strip()[:96]}")
            lines.append(f"      inspect: python -m ceo_ownership.cli inspect "
                         f"--cik {rs[0].get('cik')} --no-llm --show-table "
                         f"--out diag_{rs[0].get('cik')}.txt")

    # ---- rows that produced a figure we should not trust -----------------
    doubtful = [r for r in records
                if r.get("shares_13d3") and r.get("confidence") != "HIGH"]
    if doubtful:
        lines.append("")
        lines.append("-" * 74)
        lines.append("FIGURES PRODUCED BUT NOT TRUSTED  (a number is shown; "
                     "a check objected)")
        lines.append("-" * 74)
        by_check: dict[str, list[dict]] = defaultdict(list)
        for r in doubtful:
            failed = _failed_checks(r)
            key = failed[0][0] if failed else "no check failed (skipped only)"
            by_check[key].append(r)
        for check, rs in sorted(by_check.items(), key=lambda kv: -len(kv[1])):
            lines.append(f"\n  [{len(rs)}x] {check}")
            for r in rs[:examples]:
                pct = r.get("pct_comparable")
                lines.append(
                    f"      CIK{r.get('cik')}  {(r.get('company') or '')[:34]:<34} "
                    f"{pct:>8.3f}%" if isinstance(pct, (int, float))
                    else f"      CIK{r.get('cik')}  {(r.get('company') or '')[:34]}")
                det = next((d for nm, d in _failed_checks(r) if nm == check), "")
                if det:
                    lines.append(f"          {det[:96]}")

    # ---- flags -----------------------------------------------------------
    flags = Counter()
    for r in records:
        for f in (r.get("flags") or []):
            flags[f.split(":")[0]] += 1
    if flags:
        lines.append("")
        lines.append("-" * 74)
        lines.append("FLAGS")
        lines.append("-" * 74)
        for f, c in flags.most_common(15):
            lines.append(f"  {c:>4}x  {f}")

    # ---- coverage of the checks themselves --------------------------------
    ran = Counter()
    for r in records:
        for c in (r.get("validation") or {}).get("checks", []):
            state = {True: "passed", False: "failed", None: "skipped"}[c.get("passed")]
            ran[f"{c.get('name')}:{state}"] += 1
    if ran:
        lines.append("")
        lines.append("-" * 74)
        lines.append("CHECK COVERAGE  (a check that mostly skips is not "
                     "protecting you)")
        lines.append("-" * 74)
        names = sorted({k.split(":")[0] for k in ran})
        lines.append(f"  {'check':<26} {'passed':>8} {'failed':>8} {'skipped':>8}")
        for nm in names:
            lines.append(f"  {nm:<26} {ran.get(nm + ':passed', 0):>8} "
                         f"{ran.get(nm + ':failed', 0):>8} "
                         f"{ran.get(nm + ':skipped', 0):>8}")

    # ---- the two readers -------------------------------------------------
    verdicts = Counter(r.get("agreement") for r in records if r.get("agreement"))
    if verdicts:
        lines.append("")
        lines.append("-" * 74)
        lines.append("TWO READERS  (the model answers; the parser checks it)")
        lines.append("-" * 74)
        total = sum(verdicts.values())
        for v, n in verdicts.most_common():
            note = {"agree": "  <- parser confirms the reported figure",
                    "disagree": "  <- parser dissents; check these",
                    "model_only": "  <- only the model found a figure",
                    "parser_only": "  <- model found none; parser's used"}.get(v, "")
            lines.append(f"      {n:>4}x  {v}{note}")
        agreed = verdicts.get("agree", 0)
        if total:
            lines.append(f"\n  {agreed}/{total} agree "
                         f"({agreed / total:.0%}). Disagreements are listed "
                         f"below and are the queue to hand-check.")
        dis = [r for r in records if r.get("agreement") == "disagree"]
        for r in dis[:12]:
            lines.append(f"\n      CIK{r.get('cik')} "
                         f"{(r.get('company') or '')[:38]}")
            lines.append(f"          {(r.get('agreement_detail') or '')[:150]}")

    # ---- why does a check skip? ------------------------------------------
    # "Skipped" collapses two very different situations: a filer printing an
    # asterisk because the holding is under one percent (nothing to be done),
    # and a table with no percentage column at all (a coverage gap that a
    # different check could fill). Guessing which dominates is not good
    # enough to plan around.
    skip_reasons: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        for c in (r.get("validation") or {}).get("checks", []):
            if c.get("passed") is not None:
                continue
            detail = (c.get("detail") or "").strip()
            if "asterisk" in detail.lower():
                bucket = "filer printed an asterisk (holding under 1%)"
            elif "missing inputs" in detail.lower():
                bucket = "no percentage in the table, or no denominator"
            elif detail:
                bucket = detail[:64]
            else:
                bucket = "(no reason recorded)"
            skip_reasons[c.get("name") or "?"][bucket] += 1

    if skip_reasons:
        lines.append("")
        lines.append("-" * 74)
        lines.append("WHY CHECKS SKIP  (an unfixable skip and a coverage gap "
                     "look alike until you split them)")
        lines.append("-" * 74)
        for check, reasons in sorted(skip_reasons.items()):
            lines.append(f"\n  {check}")
            for reason, count in reasons.most_common(5):
                lines.append(f"      {count:>4}x  {reason}")

    # ---- where does the denominator come from? ---------------------------
    # The numerator is a selection problem -- Item 403 guarantees a table, so
    # the question is only which one. The denominator is an extraction
    # problem: Item 6(a) mandates the number but not its location, and the
    # word "outstanding" appears throughout ownership prose in unrelated
    # senses. Knowing which region supplied it is most of knowing whether to
    # trust it.
    regions = Counter(r.get("denominator_region") for r in records
                      if r.get("denominator_region"))
    sources = Counter(r.get("denominator_source") for r in records
                      if r.get("denominator_source"))
    if regions or sources:
        lines.append("")
        lines.append("-" * 74)
        lines.append("DENOMINATOR PROVENANCE")
        lines.append("-" * 74)
        if sources:
            lines.append("\n  source")
            for src, n in sources.most_common():
                lines.append(f"      {n:>4}x  {src}")
        if regions:
            lines.append("\n  region of the proxy it was found in "
                         "(nearest the table is best)")
            for reg, n in regions.most_common():
                note = ""
                if reg == "whole_document":
                    note = "   <- weakest; both silent errors came from here"
                elif reg in ("table_footnotes", "table_context"):
                    note = "   <- strongest"
                lines.append(f"      {n:>4}x  {reg}{note}")

        confirmed = [r.get("denominator_confirmed_by", 0) or 0 for r in records
                     if r.get("shares_outstanding")]
        if confirmed:
            lines.append(f"\n  corroboration: "
                         f"{sum(1 for c in confirmed if c >= 2)} confirmed by 2+, "
                         f"{sum(1 for c in confirmed if c == 1)} by 1, "
                         f"{sum(1 for c in confirmed if c == 0)} unconfirmed")
        gaps = [r.get("denominator_gap_days") for r in records
                if isinstance(r.get("denominator_gap_days"), int)]
        if gaps:
            gaps.sort()
            lines.append(f"  days from the record date: median "
                         f"{gaps[len(gaps)//2]}, max {max(gaps)}")
        dis = [r.get("denominator_disagreement") for r in records
               if isinstance(r.get("denominator_disagreement"), float)]
        if dis:
            over = sum(1 for d in dis if d > 0.05)
            lines.append(f"  other sources disagree by >5% on {over} row(s)")

    lines.append("")
    return "\n".join(lines)
