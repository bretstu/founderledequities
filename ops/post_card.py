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
from company_cards import Fonts, read_series, compact, INK, MUT, FAINT, LINE, PAPER, BUY, SELL  # noqa: E402

W, H = 1200, 630
KIND_WORD = {"disc": "DISCRETIONARY SALE", "plan": "PLANNED SALE", "bought": "OPEN-MARKET BUY", "sold": "SALE (plan not stated)"}
KIND_COLOR = {"disc": SELL, "plan": MUT, "bought": BUY, "sold": SELL}


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


def draw(out, tk, company, ceo, founder, kind, amount, when, pct_before, pct_after, series, fonts_dir=None, height=None, sealed=False):
    """1200x630, the link-card ratio. Top to bottom: the company and the
    person; a year of closes across the full width, the day marked; the
    newest trade in its colour; the stake before and after, large. No brand
    line and no address (X prints the site under the card), no sales line
    (a sealed company simply shows no stake), and nothing in the bottom
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
        d.rounded_rectangle((x, y + 2, x + bw, y + 2 + bh), radius=4, fill=INK)
        d.text((x + bw / 2, y + 2 + bh / 2), "FOUNDER", font=fonts.mono(15), fill=PAPER, anchor="mm")
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
        d.polygon(poly + [(x1, bottom + 2), (x0, bottom + 2)], fill="#E9E5DB")
        d.line(poly, fill=INK, width=3)
        lx, ly = poly[-1]
        color = KIND_COLOR.get(kind, MUT) if kind else INK
        d.ellipse((lx - 8, ly - 8, lx + 8, ly + 8), fill=color)
        d.text((x0, bottom + 12), pts[0][0][:4], font=fonts.mono(15), fill=FAINT)
        d.text((x1, bottom + 12), pts[-1][0][:4], font=fonts.mono(15), fill=FAINT, anchor="ra")
    # the trade line and the stake, above the title overlay
    f = lambda x: f"{x:.3f}%" if x < 1 else f"{x:.2f}%"  # noqa: E731
    color = KIND_COLOR.get(kind, MUT)
    if kind:
        kl = KIND_WORD.get(kind, "TRADE") + (f"  ·  {money(amount)}" if amount else "") + (f"  ·  {mdy(when)}" if when else "")
        # a sealed card (no stake: the OG images are public files, and the
        # stake is what a subscription buys) carries the trade line larger,
        # where the stake would sit, so the card reads whole
        if sealed:
            d.text((pad, H - 176), kl, font=fonts.mono(34), fill=color)
        else:
            d.text((pad, H - 200), kl, font=fonts.mono(24), fill=color)
    if not sealed:
        if pct_before is not None and pct_after is not None and abs(pct_before - pct_after) > 0.0005 and kind:
            stake = f"{f(pct_before)}  →  {f(pct_after)}"
        elif pct_after is not None:
            stake = f"Owns {f(pct_after)}"
        else:
            stake = ""
        d.text((pad, H - 166), stake, font=fonts.disp(72, 500), fill=INK)
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


def post_text(tk, ceo, founder, kind, amount, pct_of_holding, pct_after, filed_minutes=None, pct_before=None) -> str:
    """The three lines, in the site's words, no pronoun anywhere. When the
    trade's share of the holding is not asserted (a day the record cannot
    add up: Ambarella, 2026-09-17), the stake before and after still are,
    and the line says them instead."""
    who = ("Founder " if founder else "CEO ") + ceo
    verb = "bought" if kind == "bought" else "sold"
    amt = f" {money(amount)}" if amount else ""
    line1 = f"{KIND_WORD.get(kind, 'TRADE')}\n{who} {verb}{amt} of ${tk}."
    mv = ""
    try:
        m = abs(float(pct_of_holding)) if pct_of_holding not in (None, "") else None
        mv = (f"{m:.2f}% of the stake. " if m is not None and m < 1 else f"{m:.1f}% of the stake. " if m is not None else "")
    except ValueError:
        pass
    f = lambda x: f"{x:.3f}%" if x < 1 else f"{x:.2f}%"  # noqa: E731
    if not mv and pct_before not in (None, "") and pct_after not in (None, ""):
        line2 = f"Stake {f(float(pct_before))} \u2192 {f(float(pct_after))}."
    else:
        line2 = f"{mv}Now owns {f(float(pct_after))}." if pct_after not in (None, "") else mv.strip()
    line3 = f"Filed {filed_minutes} minutes ago." if filed_minutes is not None else "Filed today."
    return f"{line1}\n{line2}\n{line3}"


if __name__ == "__main__":
    tk = sys.argv[1].upper()
    out = sys.argv[2]
    acc = sys.argv[sys.argv.index("--event") + 1] if "--event" in sys.argv else None
    r = from_event(tk, out, acc)
    print(r or "no trade event for that ticker")
