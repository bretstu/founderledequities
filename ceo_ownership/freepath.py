"""The free path: read the reported 13d-3 figure straight off the table.

The metric is beneficial ownership under Rule 13d-3, exactly as the filer
printed it in the Item 403 table. Because that is a single legal standard
rather than a constructed number, there is nothing to decompose from prose --
the footnotes annotate the figure, they do not change it. That is what makes
this path cheap: parse the table, take the number, done.

Escalation to the model is therefore reserved for cases where the TABLE could
not be read, not where the definition is ambiguous:

  * the heuristic parser found no usable rows
  * the CEO's row could not be matched by name
  * the table reports only VOTING classes, so it does not contain the whole
    answer (Alphabet omits its non-voting Class C entirely)

Form 4 is not consulted by default. Section 16 reports under Rule
16a-1(a)(2) -- "pecuniary interest", the opportunity to profit -- which is a
different legal test from 13d-3's voting-and-investment-power test. Comparing
them produced disagreements that looked like bugs but were in fact two
standards measuring different things.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .extract import OwnershipRow
from .proxy import GROUP_ROW_RE
from .validate import names_match

SHARES_RE = re.compile(r"^([\d,]{1,3}(?:,\d{3})*(?:\.\d+)?)((?:\s*\(\d+\))*)\s*$")
PCT_RE = re.compile(r"^(\*|\u2014|-|<?\s*[\d.]+\s*%?)$")
FOOTNOTE_REF_RE = re.compile(r"\((\d+)\)")
FOOTNOTE_CELL_RE = re.compile(r"^\(?\d{1,2}\)?$")
DASH_RE = re.compile(r"^[\u2014\u2013-]$")

SUBHEADER_TOKEN_RE = re.compile(r"^(shares?|%|percent|number|amount|#)$", re.I)
CLASS_LABEL_RE = re.compile(r"^class\s+[a-z]\b", re.I)
VOTING_ONLY_RE = re.compile(
    r"voting\s+shares?\s+beneficially|voting\s+shares?\s+owned", re.I
)

# Column roles. Order matters: the first pattern matching a header cell wins.
COLUMN_ROLES: list[tuple[str, str]] = [
    # An explicit total IS the 13d-3 figure -- JPMorgan prints common stock and
    # SARs separately, then totals them.
    ("total_beneficial", r"total beneficial|aggregate (?:amount )?beneficial|"
                         r"total (?:shares )?beneficially owned"),
    # Acquirable within 60 days: part of 13d-3, so ADDED, never chosen between.
    ("options", r"option|\bsar\b|sars|exercisab\w+ within|right to (?:buy|acquire)"),
    # Explicitly NOT beneficially owned -- filers say so in the footnotes.
    ("units", r"additional underlying|underlying (?:shares|stock)|"
              r"(?:stock|share) units?|unvested|deferred (?:stock|share)"),
    ("percent", r"percent|%|\bpct\b"),
    ("voting_power", r"(?:%|percent).{0,20}voting|voting power"),
    ("sole", r"sole voting|sole .{0,20}dispositive"),
    ("shared", r"shared voting|shared .{0,20}dispositive"),
    ("total", r"^total\b|^total\s*\(#\)"),
    ("common", r"common stock|common shares?|shares beneficially owned|"
               r"amount and nature|beneficially owned|shares owned|"
               r"^shares?\b|^common\b|ordinary shares?"),
]


@dataclass
class FreePathResult:
    row: OwnershipRow | None = None
    matched_name: str | None = None
    shares_13d3: float | None = None
    column_used: str | None = None
    escalate: bool = True
    reasons: list[str] = None

    def __post_init__(self):
        if self.reasons is None:
            self.reasons = []


# ----------------------------------------------------------------- headers


ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff\u00a0]")


def _cells(line: str) -> list[str]:
    """Split a pipe row into meaningful cells.

    Zero-width spaces must be stripped BEFORE testing emptiness: Tesla pads
    every cell with U+200B, and "\u200b".strip() is truthy, so those spacer
    cells survived and desynchronised the data rows from the header -- which
    degraded column choice to a first-numeric guess.
    """
    out = []
    for raw in line.split("|"):
        c = ZERO_WIDTH_RE.sub(" ", raw).strip()
        if c:
            out.append(c)
    return out


def classify_header(header_cells: list[str]) -> list[str]:
    """Assign a role to each header cell."""
    roles = []
    for i, cell in enumerate(header_cells):
        # Tesla pads every cell with zero-width spaces; without stripping them
        # no header role resolves and column choice degrades to guesswork.
        c = ZERO_WIDTH_RE.sub(" ", cell or "")
        c = re.sub(r"\s+", " ", c).strip().lower()
        c = re.sub(r"\s*\(?#\)?\s*$", "", c)
        c = re.sub(r"[\d,\s]+$", "", c)  # trailing footnote markers
        role = "name" if i == 0 else "unknown"
        if i > 0:
            for name, pat in COLUMN_ROLES:
                if re.search(pat, c):
                    role = name
                    break
        roles.append(role)
    return roles


def parse_multirow_header(lines: list[str]) -> tuple[list[str], int] | None:
    """Handle dual-class tables whose header spans several rows.

    Meta and Alphabet both render as:

        Name of Beneficial Owner | Shares Beneficially Owned | % of Total Voting Power
        Class A | Class B
        Shares | % | Shares | %
        Mark Zuckerberg (2) | 639,347 | * | 341,823,978 | 99.8 | 60.8

    A single-row reading takes only the Class A number -- 639,347 of
    Zuckerberg's 342,463,325. The sub-header row is what actually names the
    columns, so use it.
    """
    for i, ln in enumerate(lines[:5]):
        cells = _cells(ln)
        if len(cells) < 2:
            continue
        if not all(SUBHEADER_TOKEN_RE.match(c) for c in cells):
            continue
        has_classes = False
        if i >= 1:
            above = _cells(lines[i - 1])
            has_classes = any(CLASS_LABEL_RE.match(c) for c in above)
        if not has_classes:
            continue

        roles = ["name"]
        for c in cells:
            is_pct = c.strip() == "%" or c.lower().startswith("percent")
            roles.append("percent" if is_pct else "common")
        return roles, i
    return None


def header_reports_voting_only(lines: list[str]) -> bool:
    """Alphabet's table is headed "Voting Shares Beneficially Owned" and omits
    Class C entirely, because Class C is non-voting. The proxy therefore does
    not contain the whole 13d-3 answer -- Pichai's 227,560 Class A against
    holdings that also include 2.78M Class C. Such a table must not resolve
    free."""
    return any(VOTING_ONLY_RE.search(ln) for ln in lines[:4])


# ------------------------------------------------------------------- cells


def _to_number(cell: str) -> float | None:
    c = (cell or "").strip()
    if DASH_RE.match(c):
        return 0.0
    m = SHARES_RE.match(c)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def strip_footnote_cells(cells: list[str]) -> list[str]:
    """Drop cells that are bare footnote superscripts.

    Rendering turns "900,572(12)" into two cells: "900,572" and "12". Only
    drop a small bare integer when the PRECEDING cell was itself a share-like
    number -- otherwise a genuine tiny holding (JPMorgan lists a director with
    5 shares) would be discarded.
    """
    out: list[str] = []
    prev_was_number = False
    for cell in cells:
        c = (cell or "").strip()
        is_footnote = (
            FOOTNOTE_CELL_RE.match(c)
            and "," not in c
            and prev_was_number
            and (c.startswith("(") or len(c.strip("()")) <= 2)
        )
        if is_footnote:
            prev_was_number = False
            continue
        out.append(c)
        prev_was_number = bool(SHARES_RE.match(c)) and ("," in c or len(c) > 2)
    return out


def select_share_value(
    roles: list[str], cells: list[str]
) -> tuple[float | None, str]:
    """-> (shares_13d3, which_columns_were_used).

    Rule 13d-3 counts holdings PLUS anything acquirable within 60 days, so
    where a filer breaks those into separate columns they are ADDED, not
    chosen between. Columns the filer labels as not beneficially owned --
    "additional underlying shares or stock units", unvested awards, deferred
    units -- are always excluded.
    """
    values: dict[str, float] = {}
    common_total = 0.0
    common_count = 0
    for role, cell in zip(roles, cells):
        if role in ("name", "percent", "voting_power", "units"):
            continue
        v = _to_number(cell)
        if v is None:
            continue
        if role == "common":
            common_total += v
            common_count += 1
        elif role not in values:
            values[role] = v

    # 1. The filer already did the arithmetic.
    if "total_beneficial" in values:
        return values["total_beneficial"], "total_beneficial"

    # 2. Holdings plus 60-day acquirables.
    if common_count:
        total = common_total + values.get("options", 0.0)
        parts = ["common" if common_count == 1 else f"{common_count}xclass"]
        if values.get("options"):
            parts.append("options60d")
        return total, "+".join(parts)

    # 3. Ownership split by voting power rather than by security type.
    if "sole" in values:
        if "total" in values:
            return values["total"], "total(sole+shared)"
        return values["sole"] + values.get("shared", 0.0), "sole+shared"
    if "total" in values:
        return values["total"], "total"
    if "unknown" in values:
        return values["unknown"], "unknown"
    return None, "none"


# -------------------------------------------------------------------- rows


def parse_table_heuristic(table_text: str) -> list[OwnershipRow]:
    """Pull (name, shares_13d3, percent) out of a pipe-delimited table.

    No model, no cost. Column choice is driven by the header rather than by
    position, because filers split the numbers differently -- by security type
    (JPMorgan, Microsoft), by share class (Meta, Alphabet), or by voting power
    (Walmart).
    """
    lines = [ln for ln in table_text.splitlines() if ln.strip()]
    if not lines:
        return []

    roles: list[str] = []
    header_idx = 0
    multi = parse_multirow_header(lines)
    if multi:
        roles, header_idx = multi
    else:
        for i, ln in enumerate(lines[:4]):
            cells = _cells(ln)
            if len(cells) < 2:
                continue
            if any(_to_number(c) is not None and "," in c for c in cells[1:]):
                continue
            roles = classify_header(cells)
            header_idx = i
            break

    rows: list[OwnershipRow] = []
    for line in lines[header_idx + 1:]:
        raw_cells = _cells(line)
        if len(raw_cells) < 2:
            continue

        name = raw_cells[0]
        if not re.search(r"[A-Za-z]{2}", name):
            continue

        cells = strip_footnote_cells(raw_cells)
        refs = FOOTNOTE_REF_RE.findall(line)
        clean_name = FOOTNOTE_REF_RE.sub("", name)
        clean_name = re.sub(r"\s+\d{1,2}$", "", clean_name).strip(" .,")

        shares, used = (None, "none")
        if roles:
            shares, used = select_share_value(roles, cells)
        if shares is None:
            for c in cells[1:]:
                v = _to_number(c)
                if v is not None:
                    shares, used = v, "first_numeric"
                    break
        if shares is None:
            continue

        pct = None
        is_asterisk = False
        for role, cell in (zip(roles, cells) if roles else []):
            if role != "percent":
                continue
            c = cell.strip()
            if c.startswith("*") or DASH_RE.match(c):
                is_asterisk = True
            else:
                try:
                    pct = float(c.replace("%", "").replace("<", "").strip())
                except ValueError:
                    pass
            break

        # Fallback: no column was CLASSIFIED as a percentage, but one may still
        # be printed. Tesla's header is padded with zero-width spaces, so no
        # role resolves and its 19.8% was being lost -- which silently skipped
        # the percentage reconciliation, the strongest numeric check there is.
        if pct is None and not is_asterisk:
            for c in cells[1:]:
                c = c.strip()
                if not PCT_RE.match(c):
                    continue
                if c.startswith("*") or DASH_RE.match(c):
                    is_asterisk = True
                    break
                try:
                    val = float(c.replace("%", "").replace("<", "").strip())
                except ValueError:
                    continue
                # A percentage cannot exceed 100, and a bare integer with no
                # "%" is more likely a footnote marker than a percentage.
                if 0 < val <= 100 and ("%" in c or "." in c):
                    pct = val
                    break

        rows.append(
            OwnershipRow(
                name_raw=clean_name,
                shares_reported=int(shares),
                pct_reported=pct,
                pct_is_asterisk=is_asterisk,
                is_group_row=bool(GROUP_ROW_RE.search(name)),
                footnote_text="|".join(refs) if refs else None,
                notes=f"column={used}",
            )
        )
    return rows


# ------------------------------------------------------------------ router


def try_free_path(
    table_text: str,
    footnote_block: str,
    candidate_names: list[str],
) -> FreePathResult:
    """Settle the company with no API call, or say precisely why not."""
    res = FreePathResult()

    if not candidate_names:
        res.reasons.append("no CEO name available to match against")
        return res

    if header_reports_voting_only(table_text.splitlines()):
        res.reasons.append(
            "table reports VOTING shares only -- non-voting classes (e.g. "
            "Alphabet Class C) are omitted, so it does not hold the full "
            "13d-3 figure"
        )
        return res

    rows = parse_table_heuristic(table_text)
    if not rows:
        res.reasons.append("heuristic parse found no rows")
        return res

    people = [r for r in rows if not r.is_group_row]
    for cand in candidate_names:
        scored = sorted(
            ((names_match(r.name_raw, cand), r) for r in people),
            key=lambda t: t[0],
            reverse=True,
        )
        if scored and scored[0][0] >= 0.7:
            row = scored[0][1]
            res.row = row
            res.matched_name = row.name_raw
            res.shares_13d3 = float(row.shares_reported or 0)
            res.column_used = row.notes
            res.escalate = False
            res.reasons.append(
                f"matched {row.name_raw!r} in the Item 403 table ({row.notes})"
            )
            return res

    best = "none"
    if people:
        top = max(
            ((names_match(r.name_raw, candidate_names[0]), r) for r in people),
            key=lambda t: t[0],
        )
        best = f"{top[0]:.2f} for {top[1].name_raw!r}"
    res.reasons.append(
        f"CEO row not found: {len(people)} candidates, best match {best}"
    )
    return res
