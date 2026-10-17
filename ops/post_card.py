#!/usr/bin/env python3
"""THE POST CARD (2026-09-18): the image for an X post about one founder
move, 1200x560, from the same facts the alert uses. The brand line, the
company, the person with the founder badge, the kind in its colour with the
amount and the date, the stake before and after as the largest thing on the
card, and a sparkline of the last year's closes with the day marked.
    python3 ops/post_card.py TICKER out.png [--event ACCESSION]
Drawn by ops/live.py when the watcher finds a founder move, attached to the
owner's copy beside the post text. Fonts and palette are the company card's
(ops/company_cards.py). Nothing here touches the site.
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from company_cards import Fonts, read_series, compact, INK, MUT, FAINT, LINE, PAPER, PANEL, BUY, SELL, ACCENT, ACCENT_L  # noqa: E402

W, H = 1200, 630
KIND_WORD = {"disc": "DISCRETIONARY SALE", "plan": "PLANNED SALE", "bought": "OPEN-MARKET BUY", "sold": "SALE (plan not stated)"}
KIND_COLOR = {"disc": SELL, "plan": SELL, "bought": BUY, "sold": SELL}   # a planned sale is a sale (2026-09-29)


def post_kind(e) -> str:
    """The tape's kind for a trade event, from the site's own taxonomy
    (ops/kinds.py): bought / disc / plan / sold."""
    import kinds
    k = kinds.kind_of(e)
    return k if k in ("bought", "disc", "plan", "sold") else "sold"


def short_name(company: str, tk: str) -> str:
    import re
    n = (company or "").strip()
    for _ in range(2):
        n = re.sub(r"[,\s]+(inc\.?|incorporated|corp\.?|corporation|co\.?|company|ltd\.?|limited|plc|holdings?|group)\s*$", "", n, flags=re.I).strip(" ,")
    return n or tk


def mdy(iso):
    try:
        y, m, d = (iso or "")[:10].split("-")
        return f"{m}/{d}/{y}"
    except ValueError:
        return iso or ""


def money(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    if v >= 999.5e6:
        return f"${v / 1e9:.1f}B".replace(".0B", "B")
    if v >= 999.5e3:
        return f"${v / 1e6:.1f}M".replace(".0M", "M")
    if v >= 1e3:
        return f"${v / 1e3:.0f}K"
    return f"${v:,.0f}"


def draw(out, tk, company, ceo, founder, kind, amount, when, pct_before, pct_after, series, fonts_dir=None, height=None, value=None):
    """1200x630, the link-card ratio. Top to bottom: the company and the
    person; a year of closes across the full width, the day marked; the
    newest trade in its colour; the stake before and after, large. No brand
    line and no address (X prints the site under the card), no sales line
    (a company with no settled figure simply shows no stake), and nothing in the bottom
    70px, where X lays the page title over the image."""
    from PIL import Image, ImageDraw
    H = height or 630
    fonts = Fonts(fonts_dir or os.path.join(HERE, "fonts"))
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    pad = 56
    # the company and the person
    name = short_name(company, tk)
    size = 64 if len(name) <= 18 else 54 if len(name) <= 26 else 44
    d.text((pad, 40), name, font=fonts.disp(size, 650), fill=INK)
    y = 40 + size + 10
    line = f"{ceo}  ·  CEO"
    d.text((pad, y), line, font=fonts.ui(26, 500), fill=MUT)
    if founder:
        x = pad + d.textlength(line, font=fonts.ui(26, 500)) + 16
        bw, bh = 110, 28
        d.rounded_rectangle((x, y + 2, x + bw, y + 2 + bh), radius=bh // 2, fill=ACCENT_L)
        d.text((x + bw / 2, y + 2 + bh / 2), "FOUNDER", font=fonts.ui(14, 600), fill=ACCENT, anchor="mm")
    # the chart, full width, in the middle band
    top, bottom = y + 56, H - 250
    if series:
        pts = series[-260:]
        vals = [c for _, c in pts]
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1.0
        x0, x1 = pad, W - pad
        poly = []
        for i, (_, c) in enumerate(pts):
            x = x0 + (x1 - x0) * i / max(len(pts) - 1, 1)
            yy = bottom - (bottom - top) * (c - lo) / span
            poly.append((x, yy))
        d.polygon(poly + [(x1, bottom + 2), (x0, bottom + 2)], fill=PANEL)
        d.line(poly, fill=INK, width=3)
        lx, ly = poly[-1]
        color = KIND_COLOR.get(kind, MUT) if kind else INK
        d.ellipse((lx - 8, ly - 8, lx + 8, ly + 8), fill=color)
        d.text((x0, bottom + 12), pts[0][0][:4], font=fonts.ui(15, 500), fill=FAINT)
        d.text((x1, bottom + 12), pts[-1][0][:4], font=fonts.ui(15, 500), fill=FAINT, anchor="ra")
    # the trade line and the stake, above the title overlay
    f = lambda x: f"{x:.3f}%" if x < 1 else f"{x:.2f}%"  # noqa: E731
    color = KIND_COLOR.get(kind, MUT)
    if kind:
        kl = KIND_WORD.get(kind, "TRADE") + (f"  ·  {money(amount)}" if amount else "") + (f"  ·  {mdy(when)}" if when else "")
        # a card with no stake to show carries the trade line larger,
        # where the stake would sit, so the card reads whole
        if pct_after is None:
            d.text((pad, H - 176), kl, font=fonts.ui(34, 600), fill=color)
        else:
            d.text((pad, H - 200), kl, font=fonts.ui(24, 600), fill=color)
    if pct_after is not None or pct_before is not None:
        if pct_before is not None and pct_after is not None and abs(pct_before - pct_after) > 0.0005 and kind:
            stake = f"{f(pct_before)}  →  {f(pct_after)}"
        elif pct_after is not None:
            # the company card (2026-10-17): the stake today, and what it is worth
            stake = f"Owns {f(pct_after)}" + (f"  \u00b7  {money(value)}" if value else "")
        else:
            stake = ""
        d.text((pad, H - 166), stake, font=fonts.disp(72, 700), fill=ACCENT)
    im.save(out, "PNG", optimize=True)
    return out


def from_event(tk, out, accession=None, root=ROOT, store=None):
    """Draw the card for a company's newest trade event (or the given accession)."""
    P = {r["ticker"]: r for r in csv.DictReader(open(os.path.join(root, "panel.csv"), encoding="utf-8-sig"))}
    F = {r["ticker"].upper(): (r.get("founder") or "").lower() == "yes" for r in csv.DictReader(open(os.path.join(root, "founders.csv"), encoding="utf-8-sig"))} if os.path.exists(os.path.join(root, "founders.csv")) else {}
    E = [e for e in csv.DictReader(open(os.path.join(root, "events.csv"), encoding="utf-8-sig")) if e["ticker"] == tk and (e.get("code") or "") in ("P", "S")]
    if accession:
        E = [e for e in E if e.get("accession") == accession]
    if not E:
        return None
    e = max(E, key=lambda x: (x.get("filed") or "", x.get("traded") or ""))
    p = P.get(tk, {})
    after = float(e["pct_after"]) if e.get("pct_after") else None
    before = None
    try:
        h, n, o = float(e.get("holding_after") or 0), float(e.get("net_change") or 0), float(e.get("outstanding") or 0)
        if o:
            before = (h - n) / o * 100
    except ValueError:
        pass
    series = read_series(store or os.path.join(root, "price-history"), tk)
    return draw(out, tk, p.get("company", ""), p.get("ceo", ""), F.get(tk, False), post_kind(e),
                e.get("value") or "", e.get("traded") or e.get("filed"), before, after, series)


MANNER = {"bought": "on the open market", "plan": "on a plan", "disc": "at their own discretion", "sold": ""}   # a pre-2023 sale states no plan box


def trade_days(traded_from, traded) -> str:
    """The transaction date as a post says it: "Oct 13", or "Oct 9\u201313" when
    the form covers several days, "Sep 29\u2013Oct 2" across a month."""
    def md(iso):
        try:
            y, m, d = (iso or "")[:10].split("-")
            return ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(m) - 1], int(d)
        except (ValueError, IndexError):
            return None
    a, b = md(traded_from), md(traded)
    if not b:
        return ""
    if not a or a == b:
        return f"{b[0]} {b[1]}"
    if a[0] == b[0]:
        return f"{a[0]} {a[1]}\u2013{b[1]}"
    return f"{a[0]} {a[1]}\u2013{b[0]} {b[1]}"


def post_text(tk, ceo, founder, kind, amount, pct_of_holding, pct_after, filed_minutes=None, pct_before=None, when=None) -> str:
    """TWO LINES (2026-10-15): who did what, how, and the day; then the stake
    before and after, which is the fact the site has and other sites do
    not. The kind's own line and "Filed today" left: the manner is three
    words inside the sentence, and a post made the hour of the filing says
    when it was filed by its own timestamp, so the date given is the
    trade's. When the arrow would show no change the line says the move as
    a share of the holding instead, or that the holding was unchanged. No
    his or her anywhere (the filing does not say). `filed_minutes` is kept
    for the callers and no longer printed."""
    who = ("Founder " if founder else "CEO ") + ceo
    verb = "bought" if kind == "bought" else "sold"
    amt = f" {money(amount)}" if amount else ""
    manner = MANNER.get(kind, "")
    line1 = f"{who} {verb}{amt} of ${tk}{' ' + manner if manner else ''}{', ' + when if when else ''}."
    f = lambda x: f"{x:.3f}%" if x < 1 else f"{x:.2f}%"  # noqa: E731
    try:
        a = float(pct_after) if pct_after not in (None, "") else None
    except ValueError:
        a = None
    try:
        b = float(pct_before) if pct_before not in (None, "") else None
    except ValueError:
        b = None
    try:
        m = float(pct_of_holding) if pct_of_holding not in (None, "") else None
    except ValueError:
        m = None
    if a is None:
        return line1
    if b is not None and f(b) != f(a):
        line2 = f"Stake {f(b)} \u2192 {f(a)}."
    elif m:
        mag = abs(m)
        mag_s = f"{mag:.0f}%" if mag >= 10 else f"{mag:.1f}%" if mag >= 1 else f"{mag:.2f}%"
        line2 = f"Stake {f(a)}, {'up' if m > 0 else 'down'} {mag_s} of the holding."
    elif m == 0 or b is not None:
        line2 = f"Stake {f(a)}, unchanged."
    else:
        line2 = f"Stake {f(a)}."
    return f"{line1}\n{line2}"


if __name__ == "__main__":
    tk = sys.argv[1].upper()
    out = sys.argv[2]
    acc = sys.argv[sys.argv.index("--event") + 1] if "--event" in sys.argv else None
    r = from_event(tk, out, acc)
    print(r or "no trade event for that ticker")
