"""Rolling the proxy anchor forward to today.

The proxy is annual. By the time someone reads a dashboard in November, an
April figure has had seven months to go stale -- and a CEO can move far more
in seven months than a company can repurchase. Netflix's went from 557,282 to
82,480 in a year; Broadcom's halved.

Both legs of the roll-forward are STRUCTURED data, which is why neither needs
a model:

  numerator    Form 4, XML on a fixed schema, filed within two business days
  denominator  dei:EntityCommonStockSharesOutstanding, XBRL, quarterly

That is the opposite of the proxy. Item 403 mandates content but not format,
and Item 6(a) does not even mandate location, which is why reading a proxy
needs judgment. A Form 4 has a `transactionCode` element. There is nothing to
interpret and nothing for a model to add, so the frequent updates are free
and deterministic while only the annual anchor costs anything.

Two figures are reported, because they answer different questions:

  pct_as_filed   proxy numerator over proxy denominator. One date, defensible
                 line by line against a filing, up to a year old.
  pct_current    anchor plus Form 4 deltas, over the latest cover page.
                 Current to within days; the two dates differ by up to a
                 quarter.

An earlier design held the numerator back to the denominator's date so both
would share one. That was the wrong trade: a quarter of buybacks moves a
denominator under 1%, while a single disposal halves a numerator. Waiting
three months to avoid a sub-1% error costs far more than it saves. The gap is
disclosed instead.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import date

from .edgar import EdgarClient
from .outstanding import outstanding_as_of

# ---------------------------------------------------------------------------
# Section 16 transaction codes.
#
# The subtle one is M. An option exercise converts a derivative into common
# stock, and it LOOKS like an acquisition -- but if the option was exercisable
# within 60 days it was ALREADY counted in the 13d-3 figure. Adding the shares
# would count the same economic interest twice. Under Rule 13d-3 an exercise
# is a wash.
#
# A is skipped for the opposite reason: a grant of restricted stock is not
# beneficially owned until it vests or comes within 60 days of vesting, and a
# Form 4 does not say which. Skipping understates rather than overstates, and
# the flag records it.
# ---------------------------------------------------------------------------
SUBTRACTS = {
    "S": "open-market sale",
    "F": "shares withheld for tax",
    "G": "gift out",
    "D": "disposition to the issuer",
    "U": "disposition in a tender offer",
    "J": "other disposition",          # only when disposed
}
ADDS = {
    "P": "open-market purchase",
    "I": "discretionary transaction in",
}
NEUTRAL = {
    "M": "option exercise -- already counted if exercisable within 60 days",
    "C": "conversion -- already counted if convertible within 60 days",
    "X": "in-the-money option exercise -- already counted",
}
SKIPPED = {
    "A": "award or grant -- vesting date unknown from a Form 4",
}


@dataclass
class Transaction:
    date: str
    code: str
    shares: float
    acquired: bool
    security: str
    direct: bool
    accession: str = ""

    @property
    def effect(self) -> float:
        """Signed effect on a 13d-3 holding, by code."""
        if self.code in NEUTRAL or self.code in SKIPPED:
            return 0.0
        if self.code in SUBTRACTS:
            return -abs(self.shares)
        if self.code in ADDS:
            return abs(self.shares)
        # Unrecognised code: fall back to the acquired/disposed flag, which
        # every Form 4 carries.
        return abs(self.shares) if self.acquired else -abs(self.shares)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class RollForward:
    anchor_shares: float | None = None
    anchor_date: str | None = None
    rolled_shares: float | None = None
    net_delta: float = 0.0
    transactions: list[Transaction] = field(default_factory=list)
    skipped_codes: dict = field(default_factory=dict)
    numerator_as_of: str | None = None
    denominator: float | None = None
    denominator_as_of: str | None = None
    gap_days: int | None = None
    buyback_pace: float | None = None      # last quarter's change in the count
    pct_current: float | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["transactions"] = [t.as_dict() for t in self.transactions]
        return d


COMMON_RE = re.compile(r"common|ordinary|class [a-z]\b", re.I)


def _text(node, tag: str) -> str:
    el = node.find(tag)
    if el is None:
        return ""
    val = el.find("value")
    return (val.text if val is not None and val.text else el.text or "").strip()


def transactions_since(
    client: EdgarClient,
    cik: int,
    owner_cik: int | None,
    since: str,
    until: str | None = None,
    max_filings: int = 40,
) -> list[Transaction]:
    """Form 4 transactions for one insider, after `since`.

    Only non-derivative (Table I) common-stock rows are read. Table II holds
    derivatives, and those are already reflected in the anchor when they are
    exercisable within 60 days.
    """
    import xml.etree.ElementTree as ET

    out: list[Transaction] = []
    try:
        subs = client.submissions(cik)
    except Exception:  # noqa: BLE001
        return out

    forms = [f for f in subs.get("_filings", [])
             if f.get("form") in ("4", "4/A")
             and (f.get("filingDate") or "") > since
             and (until is None or (f.get("filingDate") or "") <= until)]
    forms.sort(key=lambda f: f.get("filingDate", ""))

    for f in forms[:max_filings]:
        acc = f.get("accessionNumber", "")
        try:
            index = client.filing_index(cik, acc)
        except Exception:  # noqa: BLE001
            continue
        xml_name = next(
            (it.get("name") for it in index.get("directory", {}).get("item", [])
             if (it.get("name") or "").lower().endswith(".xml")
             and "form4" not in (it.get("name") or "").lower()[:5]),
            None)
        if not xml_name:
            continue
        try:
            raw = client.primary_document(cik, acc, xml_name)
            root = ET.fromstring(raw)
        except Exception:  # noqa: BLE001
            continue

        # Only this person's filings, when the owner is known.
        if owner_cik:
            owners = {(_text(o, "rptOwnerCik") or "").lstrip("0")
                      for o in root.iter("reportingOwnerId")}
            if owners and str(owner_cik).lstrip("0") not in owners:
                continue

        for txn in root.iter("nonDerivativeTransaction"):
            security = _text(txn, "securityTitle")
            if not COMMON_RE.search(security):
                continue
            amounts = txn.find("transactionAmounts")
            coding = txn.find("transactionCoding")
            if amounts is None or coding is None:
                continue
            try:
                shares = float(_text(amounts, "transactionShares") or 0)
            except ValueError:
                continue
            if not shares:
                continue
            ad = _text(amounts, "transactionAcquiredDisposedCode").upper()
            owner_ship = txn.find("ownershipNature")
            direct = (_text(owner_ship, "directOrIndirectOwnership").upper() == "D"
                      if owner_ship is not None else True)
            out.append(Transaction(
                date=_text(txn, "transactionDate") or f.get("filingDate", ""),
                code=_text(coding, "transactionCode").upper(),
                shares=shares,
                acquired=(ad == "A"),
                security=security,
                direct=direct,
                accession=acc,
            ))
    return out


def _days_between(a: str | None, b: str | None) -> int | None:
    try:
        pa = date(*(int(x) for x in (a or "").split("-")[:3]))
        pb = date(*(int(x) for x in (b or "").split("-")[:3]))
    except (ValueError, TypeError):
        return None
    return abs((pa - pb).days)


def roll_forward(
    client: EdgarClient,
    cik: int,
    anchor_shares: float | None,
    anchor_date: str | None,
    owner_cik: int | None = None,
    as_of: str | None = None,
) -> RollForward:
    """Carry the proxy figure forward with Form 4 deltas and a fresh count."""
    r = RollForward(anchor_shares=anchor_shares, anchor_date=anchor_date)
    if not anchor_shares or not anchor_date:
        r.notes.append("no anchor to roll forward from")
        return r

    txns = transactions_since(client, cik, owner_cik, anchor_date, as_of)
    r.transactions = txns
    r.net_delta = sum(t.effect for t in txns)
    r.rolled_shares = max(0.0, anchor_shares + r.net_delta)
    r.numerator_as_of = max((t.date for t in txns), default=anchor_date)

    from collections import Counter
    skipped = Counter(t.code for t in txns
                      if t.code in NEUTRAL or t.code in SKIPPED)
    r.skipped_codes = dict(skipped)
    for code, n in skipped.items():
        r.notes.append(f"{n} {code} transaction(s) treated as neutral: "
                       f"{NEUTRAL.get(code) or SKIPPED.get(code)}")

    snap = outstanding_as_of(client, cik, as_of=as_of)
    if snap:
        r.denominator = snap.total_shares
        r.denominator_as_of = snap.end_date
        r.gap_days = _days_between(r.numerator_as_of, r.denominator_as_of)
        if r.rolled_shares and r.denominator:
            r.pct_current = 100.0 * r.rolled_shares / r.denominator

        # A denominator gap only matters for companies repurchasing heavily.
        # Measuring last quarter's change turns "the gap is 85 days" into
        # "the gap costs about 0.3%".
        prev = outstanding_as_of(client, cik, as_of=snap.end_date, skip_latest=True)
        if prev and prev.total_shares and snap.total_shares:
            r.buyback_pace = (snap.total_shares - prev.total_shares) / prev.total_shares
            if r.gap_days and abs(r.buyback_pace) > 0.02:
                r.notes.append(
                    f"share count moved {r.buyback_pace:+.1%} last quarter and "
                    f"the denominator is {r.gap_days} days behind the "
                    f"numerator -- the percentage may be off by roughly "
                    f"{abs(r.buyback_pace) * (r.gap_days / 90):.1%}")
    else:
        r.notes.append("no cover-page share count available")
    return r
