"""HOW THE STAKE IS HELD -- THE EXPORT (2026-09-25). The walk's ledger ends
holding the decomposition the company page's section shows: per class group,
the newest filing's vehicle-by-vehicle balances. This module turns that
final state into display-ready rows -- and nothing else: no re-deriving, no
second reading of the record. The one document it opens per group is the
group's own accession, to recover the filing's VERBATIM nature text
("By Susan Lieberman Dell Separate Property Trust") for the vehicle keys the
ledger normalised away; when that read is unavailable the row falls back to
plain words ("Held directly", "Indirect holding"), never to a squashed key.

The section's warranty is enforced by the CALLER (the page builder): the
rows render only when they sum to the published stake. This module only
promises that the rows ARE the ledger's open groups, whole.
"""
from __future__ import annotations

import datetime as _dt
import re

from .ledger import (SECTION16, SINGLE_CLASS, _parse, _t, closed_groups,
                     displace_amended, vehicle_key)

STALE_DAYS = 730          # a line not restated for two years wears its date
_FOOT = re.compile(r"^\s*see\s+footnotes?\b", re.I)
_REF = re.compile(r"\s*\(\d+\)\s*$")
_JUNK = {"", "i", "d", "n/a", "na", "-"}


def class_label(security: str) -> str:
    """The class as a column entry: short, capitalised, no ceremony."""
    s = (security or "").strip()
    if s.lower() == SINGLE_CLASS.lower():
        return "Common stock"
    m = re.match(r"^(class|series)\s+([a-z0-9]+)\b", s, re.I)
    if m:
        return f"{m.group(1).title()} {m.group(2).upper()}"
    s = re.sub(r"[,.]?\s*(?:\$?[\d.]+\s+)?par\s+value.*$", "", s, flags=re.I).strip(" ,.")
    return (s[:1].upper() + s[1:]) if s else "Common stock"


def vehicle_label(key, raw: str | None) -> str:
    """The row's first column: the filing's own words, or plain ones."""
    di = (key[0] if isinstance(key, tuple) and key else "") or ""
    raw = _REF.sub("", " ".join((raw or "").split())).strip(" ,.")
    if raw and _FOOT.match(raw):
        return "Indirect, per the filing\u2019s footnote"
    if raw and raw.lower() not in _JUNK and not raw.lower().startswith("by by "):
        return raw
    return "Held directly" if di == "D" else "Indirect holding"


def _raw_natures(client, issuer_cik: int, accession: str) -> dict:
    """{vehicle_key -> the filing's verbatim nature text} from one document."""
    if not (client and issuer_cik and accession):
        return {}
    try:
        subs = client.submissions(int(issuer_cik))
        metas = [f for f in displace_amended(
                     [f for f in subs.get("_filings", []) if f.get("form") in SECTION16])
                 if f.get("accessionNumber") == accession]
        if not metas:
            return {}
        root = _parse(client, int(issuer_cik), metas[0])
        if root is None:
            return {}
        out: dict = {}
        for tag in ("nonDerivativeTransaction", "nonDerivativeHolding",
                    "derivativeTransaction", "derivativeHolding"):
            for node in root.iter(tag):
                nat = (_t(node, "natureOfOwnership") or "").strip()
                di = _t(node, "directOrIndirectOwnership") or ""
                k = vehicle_key(di, nat)
                if nat and k not in out:
                    out[k] = nat
        return out
    except Exception:
        return {}


def _days_between(a: str, b: str) -> int:
    try:
        return abs((_dt.date.fromisoformat(a[:10]) - _dt.date.fromisoformat(b[:10])).days)
    except Exception:
        return 0


def holdings_rows(led, client=None, issuer_cik: int | None = None) -> list[dict]:
    """The ledger's open groups as display rows, largest line first."""
    closed = {k for k, _g, _c in closed_groups(led.groups, getattr(led, "retired", None) or {}, "")}
    total = float(getattr(led, "total", 0.0) or 0.0)
    newest = max((g.as_of or g.filed or "" for k, g in led.groups.items() if k not in closed),
                 default="")
    rows: list[dict] = []
    for key, g in led.groups.items():
        if key in closed:
            continue
        when = g.as_of or g.filed or ""
        raws = _raw_natures(client, issuer_cik, g.accession)
        for veh, amt in g.vehicles().items():
            if not amt or amt <= 0:
                continue
            rows.append({
                "vehicle": vehicle_label(veh, raws.get(veh)),
                "klass": class_label(g.security),
                "di": (veh[0] if isinstance(veh, tuple) and veh else getattr(g, "direct", "") or ""),
                "shares": int(round(amt)),
                "pct_of_stake": round(amt / total * 100, 1) if total else "",
                "as_of": when,
                "accession": g.accession or "",
                "stale": 1 if (newest and when and _days_between(when, newest) > STALE_DAYS) else 0,
            })
    rows.sort(key=lambda r: -r["shares"])
    return rows
