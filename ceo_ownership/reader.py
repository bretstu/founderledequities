"""A second reader for the ownership section, and agreement as the check.

The parser's failures are silent. Johnson & Johnson came back HIGH
confidence and 25% wrong: identity matched, the group bound held, continuity
agreed with last year. Every automatic check compares one of our readings
against another of our readings, so they agreed with each other about a
number that was wrong. Only reading the filing by hand found it.

So this reads the same section independently and the two answers are
compared. Agreement is evidence neither has. Disagreement is a review queue.

Deliberate design choices:

  * The model is asked to QUOTE the column heading and the sentence it used.
    A figure that cannot be traced to a place in the document is not
    auditable, and auditability is the whole claim of this project.
  * It sees the table plus the text around it -- the same region the parser
    uses -- not the whole proxy. Smaller input, cheaper, and it removes the
    "find the right section" problem that the parser already solves well.
  * Its answer is subject to every existing check. The group bound,
    percentage reconciliation and continuity apply to a model's number
    exactly as they do to a parsed one.
  * Responses are cached by content hash. A filed proxy never changes, so
    each document is read once, and re-runs are free.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, asdict

from .config import SETTINGS

SYSTEM = """You read SEC proxy ownership tables. You are given the beneficial \
ownership table from a DEF 14A, the paragraph introducing it, and its \
footnotes.

Report the named person's beneficial ownership under Rule 13d-3: shares over \
which they hold voting or investment power, PLUS anything they may acquire \
within 60 days (exercisable options, shares underlying RSUs vesting in 60 \
days, convertible securities).

INCLUDE: direct holdings; shares in trusts, family entities or partnerships \
they control; 401(k) shares; pledged shares; options exercisable within 60 \
days; and, for multi-class companies, EVERY class summed together.

EXCLUDE: unvested restricted stock or RSUs not vesting within 60 days; \
deferred stock units payable after service ends; performance shares not yet \
earned; shares held by entities they do not control; and any holdings the \
table lists SEPARATELY from beneficial ownership, such as a column of \
"other stock-based holdings".

REPORT COMMON STOCK ONLY. Partnership units, operating-company units, \
exchangeable units and preferred stock are different securities and are NOT \
common shares beneficially owned, even where they are economically \
equivalent or convertible. If the only figure you can find for the person is \
denominated in another security, set shares to null and explain in note.

Where the filer prints a total column that already reflects 13d-3, use it \
rather than re-adding the components. Where components are in separate \
columns and no total is given, add them.

Also report the total shares outstanding used to compute percentages. It is \
usually stated in the paragraph above the table or in a footnote. Sum all \
classes for a multi-class company. A holding compared against the count \
("these 5,760,367 shares represent less than 1% of shares outstanding") is \
NOT the count.

Reply with JSON only, no prose and no code fences:
{"shares": <integer or null>,
 "column_used": "<the exact column heading you took it from>",
 "name_in_table": "<the person's name exactly as printed>",
 "shares_outstanding": <integer or null>,
 "outstanding_quote": "<the exact sentence stating it, or null>",
 "components": "<how you arrived at the figure, e.g. '356,297 common + \
1,051,370 options = 1,407,667 total column'>",
 "confidence": "high" | "low",
 "note": "<anything ambiguous, or null>"}

If the person is not in the table, set shares to null and say so in note."""


@dataclass
class ModelReading:
    shares: float | None = None
    column_used: str | None = None
    name_in_table: str | None = None
    shares_outstanding: float | None = None
    outstanding_quote: str | None = None
    components: str | None = None
    confidence: str | None = None
    note: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _cache_dir() -> str:
    path = os.path.join(SETTINGS.cache_dir, "readings")
    os.makedirs(path, exist_ok=True)
    return path


def _key(person: str, section: str) -> str:
    h = hashlib.sha256(f"{person}\x00{section}".encode()).hexdigest()[:32]
    return os.path.join(_cache_dir(), f"{h}.json")


def _to_number(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    text = re.sub(r"[^\d.]", "", str(v))
    try:
        return float(text) if text else None
    except ValueError:
        return None


def read_with_model(
    person: str,
    table_text: str,
    introduction: str = "",
    footnotes: str = "",
    model: str | None = None,
    max_chars: int = 14000,
) -> ModelReading:
    """Have the model read the ownership section for one person."""
    section = (
        f"INTRODUCTION (text immediately before the table):\n{introduction[-2500:]}\n\n"
        f"OWNERSHIP TABLE:\n{table_text[:max_chars]}\n\n"
        f"FOOTNOTES (text immediately after the table):\n{footnotes[:3500]}"
    )

    cached = _key(person, section)
    if os.path.exists(cached):
        try:
            with open(cached, encoding="utf-8") as fh:
                return ModelReading(**json.load(fh))
        except Exception:  # noqa: BLE001
            pass

    try:
        from anthropic import Anthropic
    except ImportError:
        return ModelReading(error="anthropic package not installed")
    if not SETTINGS.anthropic_api_key:
        return ModelReading(error="ANTHROPIC_API_KEY not set")

    try:
        client = Anthropic(api_key=SETTINGS.anthropic_api_key)
        resp = client.messages.create(
            model=model or SETTINGS.extraction_model,
            # Three replies came back truncated mid-JSON at 700. The
            # components field is worth the headroom -- it is what makes a
            # disagreement actionable rather than merely alarming.
            max_tokens=1500,
            system=SYSTEM,
            messages=[{
                "role": "user",
                "content": f"Person: {person}\n\n{section}",
            }],
        )
        raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    except Exception as exc:  # noqa: BLE001
        return ModelReading(error=f"{type(exc).__name__}: {exc}")

    text = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return ModelReading(error=f"unparseable reply: {text[:120]}")
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return ModelReading(error=f"unparseable reply: {text[:120]}")

    reading = ModelReading(
        shares=_to_number(data.get("shares")),
        column_used=data.get("column_used"),
        name_in_table=data.get("name_in_table"),
        shares_outstanding=_to_number(data.get("shares_outstanding")),
        outstanding_quote=data.get("outstanding_quote"),
        components=data.get("components"),
        confidence=data.get("confidence"),
        note=data.get("note"),
    )
    try:
        with open(cached, "w", encoding="utf-8") as fh:
            json.dump(reading.as_dict(), fh)
    except OSError:
        pass
    return reading


# ------------------------------------------------------------------ compare


@dataclass
class Agreement:
    shares_agree: bool | None = None
    outstanding_agree: bool | None = None
    shares_delta: float | None = None
    outstanding_delta: float | None = None
    verdict: str = "not_compared"   # agree | disagree | model_only |
                                    # parser_only | neither | not_compared
    detail: str = ""


def compare_readings(
    parser_shares: float | None,
    parser_outstanding: float | None,
    reading: ModelReading | None,
    tolerance: float = 0.005,
) -> Agreement:
    """Compare the two readers. Agreement is the evidence; it is not a vote.

    Neither reader wins on disagreement. The parsed figure stays the reported
    one -- it is the auditable, deterministic path -- and the disagreement is
    surfaced for review. Silently preferring the model would replace one
    unverified number with another.
    """
    a = Agreement()
    if reading is None or reading.error:
        a.detail = reading.error if reading else "no model reading"
        return a

    if parser_shares and reading.shares:
        a.shares_delta = abs(parser_shares - reading.shares) / max(parser_shares, 1)
        a.shares_agree = a.shares_delta <= tolerance
    if parser_outstanding and reading.shares_outstanding:
        a.outstanding_delta = (abs(parser_outstanding - reading.shares_outstanding)
                               / max(parser_outstanding, 1))
        a.outstanding_agree = a.outstanding_delta <= tolerance

    if parser_shares and not reading.shares:
        a.verdict = "parser_only"
        a.detail = f"model found no figure: {reading.note or 'no reason given'}"
    elif reading.shares and not parser_shares:
        a.verdict = "model_only"
        a.detail = (f"model read {reading.shares:,.0f} from "
                    f"{reading.column_used!r}; parser found nothing")
    elif not parser_shares and not reading.shares:
        a.verdict = "neither"
        a.detail = "neither reader found a figure"
    elif a.shares_agree:
        a.verdict = "agree"
        a.detail = (f"both read {parser_shares:,.0f}"
                    + (f"; denominators differ by {a.outstanding_delta:.1%}"
                       if a.outstanding_agree is False else ""))
    else:
        a.verdict = "disagree"
        a.detail = (
            f"parser {parser_shares:,.0f} vs model {reading.shares:,.0f} "
            f"({a.shares_delta:.1%}). Model took {reading.column_used!r}"
            + (f": {reading.components}" if reading.components else "")
        )

    if a.outstanding_agree is False and a.verdict in ("agree", "disagree"):
        a.detail += (f" | outstanding: parser {parser_outstanding:,.0f} vs "
                     f"model {reading.shares_outstanding:,.0f}")
    return a


# ---------------------------------------------------------------------------
# Reading the share count from candidate text.
#
# The parser is good at finding WHERE the count is stated. In a hundred
# companies it located the right region 97 times: the paragraph introducing
# the table, its footnotes, the "how many shares are outstanding" question,
# or the record-date paragraph. That is the hard part, and it is exactly the
# kind of structural work a parser should do.
#
# What it is bad at is deciding what a number in that text MEANS. Every
# denominator failure has been a real figure with the wrong meaning attached:
#
#   Enova        1,023,200      shares directors may ACQUIRE within 60 days
#   Exxon        9,000,000,000  AUTHORIZED capital under the charter
#   Johnson & J  5,760,367      insiders' holding COMPARED TO the count
#   Palantir     158,217,849    an institution's POSITION
#   ServiceNow   3,566,103      the GROUP ROW
#   Capital One  5,448,236      a CELL of the ownership table
#
# Each was answered with another exclusion pattern, written after the company
# had already been reported wrong. That list only grows, and it sits on the
# critical path: a number must survive six patterns and a class heuristic
# before it is reported.
#
# So the text goes to the model and the number comes back. The regex is out
# of the path entirely. The reply must quote the sentence it used, and that
# sentence must appear in the text we sent -- an answer that cannot be traced
# to the document is rejected.
# ---------------------------------------------------------------------------

COUNT_SYSTEM = """You are given excerpts from an SEC proxy statement (DEF \
14A). Find the TOTAL SHARES OUTSTANDING as of the record date -- the \
denominator used to compute beneficial ownership percentages.

For a company with several classes of stock, SUM every class. If the excerpt \
states a total and also lists the classes, check that they agree and report \
the total.

These are NOT the answer, even though they appear in similar language:
  - shares a person may acquire within 60 days (options, RSUs, rights)
  - shares AUTHORIZED under the charter (a ceiling, not a count)
  - shares held by any person, institution, or by directors as a group
  - a holding measured against the count: "these 5,760,367 shares represent
    less than 1% of the shares outstanding"
  - shares held in treasury
  - a number of VOTES rather than a number of shares
  - shares reserved for issuance under a plan

Reply with JSON only, no prose and no code fences:
{"shares_outstanding": <integer or null>,
 "quote": "<the exact sentence from the excerpt, copied verbatim>",
 "per_class": {"<class name>": <integer>, ...} or null,
 "as_of": "<the date it is stated as of, or null>",
 "confidence": "high" | "low",
 "note": "<why, if low or null>"}

If the excerpt does not state the total shares outstanding, return null and \
say so in note. Do NOT infer or calculate a figure that is not stated."""


@dataclass
class CountReading:
    shares_outstanding: float | None = None
    quote: str | None = None
    per_class: dict | None = None
    as_of: str | None = None
    confidence: str | None = None
    note: str | None = None
    quote_verified: bool = False
    error: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def read_share_count(
    regions: list[tuple[str, str]],
    model: str | None = None,
    max_chars_per_region: int = 4000,
) -> CountReading:
    """Read the outstanding share count from the parser's candidate regions.

    `regions` is [(name, text), ...] in the order the parser ranks them --
    the whole document is deliberately excluded by the caller, since sending
    two million characters would reintroduce the needle-in-a-haystack problem
    the parser already solves.
    """
    if not regions:
        return CountReading(error="no candidate regions")

    payload = "\n\n".join(
        f"=== {name} ===\n{text.strip()[:max_chars_per_region]}"
        for name, text in regions if text and text.strip()
    )
    if not payload:
        return CountReading(error="candidate regions were empty")

    cached = _key("sharecount", payload)
    if os.path.exists(cached):
        try:
            with open(cached, encoding="utf-8") as fh:
                return CountReading(**json.load(fh))
        except Exception:  # noqa: BLE001
            pass

    try:
        from anthropic import Anthropic
    except ImportError:
        return CountReading(error="anthropic package not installed")
    if not SETTINGS.anthropic_api_key:
        return CountReading(error="ANTHROPIC_API_KEY not set")

    try:
        client = Anthropic(api_key=SETTINGS.anthropic_api_key)
        resp = client.messages.create(
            model=model or SETTINGS.classifier_model,
            max_tokens=500,
            system=COUNT_SYSTEM,
            messages=[{"role": "user", "content": payload}],
        )
        raw = "".join(b.text for b in resp.content
                      if getattr(b, "type", "") == "text")
    except Exception as exc:  # noqa: BLE001
        return CountReading(error=f"{type(exc).__name__}: {exc}")

    text = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return CountReading(error=f"unparseable reply: {text[:120]}")
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return CountReading(error=f"unparseable reply: {text[:120]}")

    per_class = data.get("per_class")
    if isinstance(per_class, dict):
        per_class = {k: _to_number(v) for k, v in per_class.items()}
    else:
        per_class = None

    reading = CountReading(
        shares_outstanding=_to_number(data.get("shares_outstanding")),
        quote=data.get("quote"),
        per_class=per_class,
        as_of=data.get("as_of"),
        confidence=data.get("confidence"),
        note=data.get("note"),
    )

    # The quote must actually be in the text we sent. A figure that cannot be
    # traced to a place in the filing is not auditable, and auditability is
    # the whole claim of this project.
    if reading.quote:
        reading.quote_verified = _normalise(reading.quote)[:120] in _normalise(payload)
        if not reading.quote_verified:
            reading.note = ((reading.note or "") +
                            " [quote not found in the text provided]").strip()

    try:
        with open(cached, "w", encoding="utf-8") as fh:
            json.dump(reading.as_dict(), fh)
    except OSError:
        pass
    return reading
