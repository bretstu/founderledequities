"""Point-in-time universe construction -- the survivorship-bias fix.

The rule: never build the universe from a list of companies that exist today.
Build it from what was actually filed at the time.

EDGAR publishes a `master.idx` for every quarter since 1993 listing every
filing accepted in that quarter. Filtering it to DEF 14A gives the exact set
of proxy filers as of that date. Companies that later went bankrupt, were
acquired, or deregistered are present, because they filed while alive. There
is no way for survivorship to creep in, because we never consult the present.

Exit detection uses Form 25 (delisting) and Form 15 (deregistration), which
tells you *when* a company left. Distinguishing a merger exit from a failure
exit needs the surrounding filings -- that classification is left explicit
rather than guessed, because the two require opposite return assumptions and
guessing wrong is exactly how a backtest manufactures fake alpha.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, asdict
from datetime import date

from .config import SEC_BASE, EXIT_FORMS
from .edgar import EdgarClient


@dataclass
class UniverseRow:
    cik: int
    company: str
    form_type: str
    date_filed: str
    accession: str
    document_path: str

    def as_dict(self) -> dict:
        return asdict(self)


def _quarter_of(month: int) -> int:
    return (month - 1) // 3 + 1


def fetch_quarter_index(client: EdgarClient, year: int, quarter: int) -> list[dict]:
    """Parse one quarter's master.idx.

    Format is pipe-delimited after an 11-line header:
        CIK|Company Name|Form Type|Date Filed|Filename
    """
    url = f"{SEC_BASE}/Archives/edgar/full-index/{year}/QTR{quarter}/master.idx"
    raw = client.get(url)

    # The header block ends with a line of dashes.
    lines = raw.splitlines()
    start = 0
    for i, line in enumerate(lines[:20]):
        if set(line.strip()) == {"-"}:
            start = i + 1
            break
    else:
        start = 11

    rows = []
    reader = csv.reader(io.StringIO("\n".join(lines[start:])), delimiter="|")
    for parts in reader:
        if len(parts) != 5:
            continue
        cik, company, form_type, date_filed, filename = parts
        if not cik.strip().isdigit():
            continue
        rows.append(
            {
                "cik": int(cik),
                "company": company.strip(),
                "form_type": form_type.strip(),
                "date_filed": date_filed.strip(),
                "filename": filename.strip(),
            }
        )
    return rows


def proxy_filers(
    client: EdgarClient, year: int, quarter: int | None = None
) -> list[UniverseRow]:
    """Every company that filed a proxy in the given year (or quarter).

    This IS the universe. Nothing is filtered by whether the company still
    exists, because that information does not exist at the point in time we
    are simulating.
    """
    quarters = [quarter] if quarter else [1, 2, 3, 4]
    out: list[UniverseRow] = []
    for q in quarters:
        try:
            rows = fetch_quarter_index(client, year, q)
        except Exception:  # noqa: BLE001
            continue  # future quarter, or index not yet published
        for r in rows:
            if r["form_type"] not in ("DEF 14A", "DEFR14A"):
                continue
            accession = r["filename"].split("/")[-1].replace(".txt", "")
            out.append(
                UniverseRow(
                    cik=r["cik"],
                    company=r["company"],
                    form_type=r["form_type"],
                    date_filed=r["date_filed"],
                    accession=accession,
                    document_path=r["filename"],
                )
            )
    return out


def find_exits(client: EdgarClient, year: int) -> list[dict]:
    """Companies that filed a delisting or deregistration notice in `year`.

    A cik appearing here means the company left the public universe. Whether
    that was a merger (holder receives cash/stock -- roughly a neutral to
    positive return) or a failure (holder receives ~nothing) is NOT inferred
    here. `exit_reason` is left as None for you to classify, because getting
    it wrong biases the backtest in opposite directions.
    """
    exits: list[dict] = []
    for q in (1, 2, 3, 4):
        try:
            rows = fetch_quarter_index(client, year, q)
        except Exception:  # noqa: BLE001
            continue
        for r in rows:
            kind = EXIT_FORMS.get(r["form_type"])
            if kind:
                exits.append(
                    {
                        "cik": r["cik"],
                        "company": r["company"],
                        "date_filed": r["date_filed"],
                        "form_type": r["form_type"],
                        "exit_kind": kind,
                        "exit_reason": None,  # merger | failure | going_private
                    }
                )
    return exits


def build_panel(
    client: EdgarClient, start_year: int, end_year: int
) -> list[UniverseRow]:
    """Survivorship-free panel across a range of years."""
    panel: list[UniverseRow] = []
    for year in range(start_year, end_year + 1):
        panel.extend(proxy_filers(client, year))
    return panel


def rebalance_dates(rows: list[UniverseRow]) -> dict[int, str]:
    """Map cik -> earliest date the proxy data became PUBLIC.

    Uses date_filed, never the as-of date printed inside the document. A proxy
    stating holdings as of March is typically not filed until April; keying a
    rebalance off the as-of date is look-ahead bias.
    """
    out: dict[int, str] = {}
    for r in rows:
        prev = out.get(r.cik)
        if prev is None or r.date_filed < prev:
            out[r.cik] = r.date_filed
    return out
