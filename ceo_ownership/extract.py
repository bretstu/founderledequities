"""Structured extraction of the ownership table.

pandas.read_html cannot do this job. The headline cell is often `1,240,000(3)`
and footnote 3 says "includes 400,000 shares subject to options exercisable
within 60 days and 200,000 shares held by the Smith Family Trust". Separating
those is the whole task, and it is a reading problem, not a parsing problem.

The extractor therefore gets the table HTML *plus* the trailing footnote text
and returns a strict schema. Anything it cannot determine comes back null --
never zero. A null propagates into a confidence downgrade; a zero silently
becomes a wrong answer.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field, asdict

from bs4 import BeautifulSoup

from .config import SETTINGS


def table_to_text(table_html: str) -> str:
    """Render a table as compact pipe-delimited rows.

    Sending raw EDGAR HTML means paying for inline styles, span wrappers and
    XBRL attributes -- typically 8-15x more tokens than the information the
    model actually needs. Footnote markers like "(1)" survive because they
    are text content, and that is all the extractor depends on.
    """
    soup = BeautifulSoup(table_html, "lxml")
    lines = []
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        cells = [re.sub(r"\s+", " ", c) for c in cells if c and c.strip()]
        if cells:
            lines.append(" | ".join(cells))
    return "\n".join(lines)


def _cache_key(table_text: str, footnotes: str, model: str) -> str:
    blob = f"{model}\x00{table_text}\x00{footnotes}".encode()
    return hashlib.sha256(blob).hexdigest()[:32]


def _cache_dir() -> str:
    path = os.path.join(SETTINGS.cache_dir, "extractions")
    os.makedirs(path, exist_ok=True)
    return path

SYSTEM_PROMPT = """You extract beneficial ownership data from SEC proxy statements.

You will receive a pipe-delimited table and the footnote text that follows it.
Return ONLY a JSON object. No markdown fences, no commentary.

Schema:
{
  "as_of_date": "YYYY-MM-DD or null",
  "share_classes": ["Class A Common Stock", ...],
  "rows": [
    {
      "name_raw": "exact text of the name cell",
      "title": "title if stated in the table, else null",
      "share_class": "which class this row reports, or null if single-class",
      "shares_reported": integer or null,
      "pct_reported": float or null,
      "pct_is_asterisk": true if the filing shows * or < 1% instead of a number,
      "options_60d": integer or null,
      "shares_in_trusts_or_indirect": integer or null,
      "shares_disclaimed": integer or null,
      "shares_pledged": integer or null,
      "unvested_awards": integer or null,
      "exchangeable_units": integer or null,
      "is_group_row": true for the "all directors and executive officers" line,
      "is_five_percent_holder": true for institutional/outside 5% holders,
      "footnote_text": "concatenated text of footnotes referenced by this row",
      "notes": "anything unusual, else null"
    }
  ]
}

Critical rules:
- shares_reported is the number PRINTED in the table, unmodified. Do not do arithmetic.
- options_60d: only if a footnote states it. If no footnote mentions options, use null, NOT 0.
- The distinction between null and 0 is load-bearing. null means "not stated".
- exchangeable_units: LLC/LP/operating-partnership units exchangeable for common (Up-C).
- Include every row, including group rows and 5% holders.
"""


@dataclass
class OwnershipRow:
    name_raw: str
    title: str | None = None
    share_class: str | None = None
    shares_reported: int | None = None
    pct_reported: float | None = None
    pct_is_asterisk: bool = False
    pct_voting_power: float | None = None
    options_60d: int | None = None
    shares_in_trusts_or_indirect: int | None = None
    shares_disclaimed: int | None = None
    shares_pledged: int | None = None
    unvested_awards: int | None = None
    exchangeable_units: int | None = None
    is_group_row: bool = False
    is_five_percent_holder: bool = False
    footnote_text: str | None = None
    notes: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)

    @property
    def common_shares(self) -> int | None:
        """Shares under the project definition: reported minus 60-day options.

        Derivatives are excluded because an unexercised option is a right to
        buy, not ownership -- and an underwater one is worth nothing. Anything
        already exercised or vested is inside shares_reported already, since
        settlement moves it into common on the books.
        """
        if self.shares_reported is None:
            return None
        out = self.shares_reported
        if self.options_60d:
            out -= self.options_60d
        if self.shares_disclaimed:
            out -= self.shares_disclaimed
        return max(out, 0)


@dataclass
class ExtractionResult:
    as_of_date: str | None
    share_classes: list[str] = field(default_factory=list)
    rows: list[OwnershipRow] = field(default_factory=list)
    raw_response: str | None = None
    error: str | None = None
    salvaged: bool = False


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def extract_ownership(
    table_html: str,
    footnote_context: str,
    model: str | None = None,
    api_key: str | None = None,
    pre_rendered: bool = False,
) -> ExtractionResult:
    """Call the model and coerce the response into the schema."""
    try:
        from anthropic import Anthropic
    except ImportError:  # pragma: no cover
        return ExtractionResult(None, error="anthropic SDK not installed")

    key = api_key or SETTINGS.anthropic_api_key
    if not key:
        return ExtractionResult(None, error="ANTHROPIC_API_KEY not set")

    model_name = model or SETTINGS.extraction_model
    table_text = (table_html if pre_rendered else table_to_text(table_html))[:40000]
    footnotes = footnote_context[:8000]

    # Extraction responses are cached on content, so re-runs and iteration
    # cost nothing. Only genuinely new filings are billed.
    key_hash = _cache_key(table_text, footnotes, model_name)
    cache_path = os.path.join(_cache_dir(), key_hash)
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as fh:
            return parse_extraction_response(fh.read())

    client = Anthropic(api_key=key)
    user_content = (
        "TABLE:\n"
        + table_text
        + "\n\nFOOTNOTES AND FOLLOWING TEXT:\n"
        + footnotes
    )

    try:
        resp = client.messages.create(
            model=model_name,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
    except Exception as exc:  # noqa: BLE001
        return ExtractionResult(None, error=f"API call failed: {exc}")

    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    truncated = getattr(resp, "stop_reason", None) == "max_tokens"
    result = parse_extraction_response(text, truncated=truncated)
    if result.error is None:
        with open(cache_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return result


def _salvage_partial_json(text: str) -> str | None:
    """Recover the complete rows from a response that was cut off mid-object.

    A truncated response is still mostly good data -- the CEO is usually in
    the first few rows. Trim back to the last complete row object, close the
    array and the outer brace, and parse that. Better to return 14 rows with
    a flag than to throw away the whole company.
    """
    last = text.rfind("},")
    if last == -1:
        return None
    candidate = text[: last + 1] + "]}"
    try:
        json.loads(candidate)
        return candidate
    except json.JSONDecodeError:
        return None


def parse_extraction_response(text: str, truncated: bool = False) -> ExtractionResult:
    """Split out so it can be unit-tested without an API key."""
    cleaned = _strip_fences(text)
    salvaged = False
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        repaired = _salvage_partial_json(cleaned)
        if repaired is None:
            reason = (
                "response hit the token limit"
                if truncated
                else "model emitted malformed JSON"
            )
            return ExtractionResult(
                None, raw_response=text, error=f"bad JSON ({reason}): {exc}"
            )
        data = json.loads(repaired)
        salvaged = True

    rows = []
    for r in data.get("rows", []):
        rows.append(
            OwnershipRow(
                name_raw=r.get("name_raw", ""),
                title=r.get("title"),
                share_class=r.get("share_class"),
                shares_reported=_as_int(r.get("shares_reported")),
                pct_reported=_as_float(r.get("pct_reported")),
                pct_is_asterisk=bool(r.get("pct_is_asterisk", False)),
                options_60d=_as_int(r.get("options_60d")),
                shares_in_trusts_or_indirect=_as_int(
                    r.get("shares_in_trusts_or_indirect")
                ),
                shares_disclaimed=_as_int(r.get("shares_disclaimed")),
                shares_pledged=_as_int(r.get("shares_pledged")),
                unvested_awards=_as_int(r.get("unvested_awards")),
                exchangeable_units=_as_int(r.get("exchangeable_units")),
                is_group_row=bool(r.get("is_group_row", False)),
                is_five_percent_holder=bool(r.get("is_five_percent_holder", False)),
                footnote_text=r.get("footnote_text"),
                notes=r.get("notes"),
            )
        )
    return ExtractionResult(
        as_of_date=data.get("as_of_date"),
        share_classes=data.get("share_classes", []) or [],
        rows=rows,
        raw_response=text,
        salvaged=salvaged,
    )


def _as_int(v) -> int | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return int(v)
    cleaned = re.sub(r"[^\d\-]", "", str(v))
    return int(cleaned) if cleaned not in ("", "-") else None


def _as_float(v) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    cleaned = re.sub(r"[^\d.\-]", "", str(v))
    try:
        return float(cleaned)
    except ValueError:
        return None


TARGETED_PROMPT = """You extract ONE person's beneficial ownership from an SEC proxy table.

You will receive a pipe-delimited table, the footnotes that follow it, and the
name of the target person. Return ONLY a JSON object for that person plus the
"all directors and executive officers as a group" row. No other rows. No
markdown fences, no commentary.

{
  "as_of_date": "YYYY-MM-DD or null",
  "share_classes": ["..."],
  "target": {
    "name_raw": "the name exactly as printed in the table",
    "share_class": null,
    "shares_reported": integer or null,
    "pct_reported": float or null,
    "pct_is_asterisk": bool,
    "pct_voting_power": float or null,
    "options_60d": integer or null,
    "shares_in_trusts_or_indirect": integer or null,
    "shares_disclaimed": integer or null,
    "shares_pledged": integer or null,
    "unvested_awards": integer or null,
    "exchangeable_units": integer or null,
    "notes": "brief, only if unusual, else null"
  },
  "group_shares": integer or null
}

Rules:
- shares_reported is the number PRINTED. Do no arithmetic.
- Only fill options_60d / unvested_awards / etc. if a footnote for THIS person
  states them. If not stated, use null, NOT 0. The distinction is load-bearing.
- If the table reports several classes for this person, sum them into
  shares_reported and list the classes in share_classes.
- The target may be printed under a different form of their name (e.g. legal
  vs. familiar). Match on surname.
- Do not echo footnote text back. Keep the response minimal.
- pct_reported must be the ECONOMIC percent of shares (percent of class /
  percent of shares outstanding). Dual-class tables often also show "% of
  Total Voting Power" -- that is a DIFFERENT number and must go in
  pct_voting_power, never in pct_reported. If only voting power is shown,
  leave pct_reported null.
"""


def extract_target(
    table_text: str,
    footnote_context: str,
    target_name: str,
    model: str | None = None,
    api_key: str | None = None,
) -> ExtractionResult:
    """Extract only the CEO's row.

    The full-table extractor returns ~16 rows x ~16 fields. Output tokens are
    several times the price of input, so that -- not the input HTML -- was
    what made a call expensive. Since Form 4 already tells us who the CEO is,
    naming them cuts the response to two rows and roughly an order of
    magnitude off the per-company cost.
    """
    try:
        from anthropic import Anthropic
    except ImportError:  # pragma: no cover
        return ExtractionResult(None, error="anthropic SDK not installed")

    key = api_key or SETTINGS.anthropic_api_key
    if not key:
        return ExtractionResult(None, error="ANTHROPIC_API_KEY not set")

    model_name = model or SETTINGS.extraction_model
    table_text = table_text[:40000]
    footnotes = footnote_context[:8000]

    key_hash = _cache_key(f"TARGET:{target_name}\x00{table_text}", footnotes, model_name)
    cache_path = os.path.join(_cache_dir(), key_hash)
    if os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as fh:
            return parse_targeted_response(fh.read())

    client = Anthropic(api_key=key)
    content = (
        f"TARGET PERSON: {target_name}\n\nTABLE:\n{table_text}"
        f"\n\nFOOTNOTES AND FOLLOWING TEXT:\n{footnotes}"
    )
    try:
        resp = client.messages.create(
            model=model_name,
            max_tokens=2000,
            system=TARGETED_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
    except Exception as exc:  # noqa: BLE001
        return ExtractionResult(None, error=f"API call failed: {exc}")

    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    result = parse_targeted_response(text)
    if result.error is None:
        with open(cache_path, "w", encoding="utf-8") as fh:
            fh.write(text)
    return result


def parse_targeted_response(text: str) -> ExtractionResult:
    try:
        data = json.loads(_strip_fences(text))
    except json.JSONDecodeError as exc:
        return ExtractionResult(None, raw_response=text, error=f"bad JSON: {exc}")

    t = data.get("target") or {}
    if not t.get("name_raw"):
        return ExtractionResult(
            data.get("as_of_date"), raw_response=text,
            error="target person not found in table",
        )

    rows = [
        OwnershipRow(
            name_raw=t.get("name_raw", ""),
            share_class=t.get("share_class"),
            shares_reported=_as_int(t.get("shares_reported")),
            pct_reported=_as_float(t.get("pct_reported")),
            pct_is_asterisk=bool(t.get("pct_is_asterisk", False)),
            pct_voting_power=_as_float(t.get("pct_voting_power")),
            options_60d=_as_int(t.get("options_60d")),
            shares_in_trusts_or_indirect=_as_int(t.get("shares_in_trusts_or_indirect")),
            shares_disclaimed=_as_int(t.get("shares_disclaimed")),
            shares_pledged=_as_int(t.get("shares_pledged")),
            unvested_awards=_as_int(t.get("unvested_awards")),
            exchangeable_units=_as_int(t.get("exchangeable_units")),
            notes=t.get("notes"),
        )
    ]
    group = _as_int(data.get("group_shares"))
    if group is not None:
        rows.append(OwnershipRow(name_raw="(group)", shares_reported=group,
                                 is_group_row=True))
    return ExtractionResult(
        as_of_date=data.get("as_of_date"),
        share_classes=data.get("share_classes", []) or [],
        rows=rows,
        raw_response=text,
    )
