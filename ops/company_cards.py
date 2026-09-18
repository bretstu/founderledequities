#!/usr/bin/env python3
"""One link card per company: the price, with the chief executive's
trades on it, drawn from the site's own files.

    python3 ops/company_cards.py panel.csv universe/sp500-<date>.csv prices.csv \\
        founders.csv events.csv price-history og

A SHARED PAGE SHOULD UNFURL INTO ITS OWN PICTURE. Every company page
pointed at the site-wide og.png, so a post about Bill.com's founder
selling on the way down showed a card that said "19 of 500". The chart on
the page is drawn by the browser after load, and an unfurler reads only
the meta tags. This draws the same chart at deploy, 1200x630, with the
same rules as the page: daily closes from the price store, split-adjusted;
each purchase and sale at the price on its filing, restated in today's
shares; grants, gifts and withholding left out.

THE SEAL HOLDS ON THE CARD. A company outside the free tier shows its
name, its chief executive, the founder badge and the public price line.
No percentage, no trades, since those are what a subscription buys.

Cheap enough to run every deploy: Pillow draws a card in a few tens of
milliseconds, so the universe takes about a minute and each card is a
fresh URL (the page points at og/<T>.png?v=<hash>), which is what the
unfurlers' caches need to notice a new picture.
"""
import csv
import hashlib
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from og_image import money  # noqa: E402  (one formatter, shared)

W, H = 1200, 630
# the site's tokens: paper, ink as the accent, green for bought
INK, BLUE, MUT, FAINT, LINE, PANEL = "#0C0D0E", "#0C0D0E", "#5D6167", "#8A8E94", "#E0DBCF", "#FBFAF6"
PAPER, BUY = "#F3F0E8", "#1F6B3A"
SELL = "#C22A2A"
MOVING = {"P", "S"}


def compact(n):
    n = float(n or 0)
    a = abs(n)
    if a >= 1e9:
        return f"{n/1e9:.2f}B"
    if a >= 1e6:
        return f"{n/1e6:.1f}M"
    if a >= 1e3:
        return f"{n/1e3:.0f}K"
    return f"{n:.0f}"


def dollars(v):
    if abs(v - round(v)) < 1e-9 and v >= 1:
        return f"${v:,.0f}"
    if v >= 100:
        return f"${v:.0f}"
    if v >= 10:
        return f"${v:.1f}"
    return f"${v:.2f}"


def load_inputs(panel_p, sp_p, prices_p, founders_p, events_p):
    sp = {r["ticker"].upper() for r in csv.DictReader(open(sp_p, encoding="utf-8-sig"))}
    prices = {}
    for r in csv.DictReader(open(prices_p, encoding="utf-8-sig")):
        try:
            prices[r["ticker"].upper()] = float(r["close"])
        except (ValueError, KeyError):
            pass
    founders = {}
    for r in csv.DictReader(open(founders_p, encoding="utf-8-sig")):
        founders[(r.get("ticker") or "").upper()] = (r.get("founder") or "").lower()
    # the moving trades, the way the page counts them: P and S only, and
    # only when the trade changed the stake (a residue-free exercise-and-
    # sell is "kept apart" and never drawn)
    events = {}
    for r in csv.DictReader(open(events_p, encoding="utf-8-sig")):
        if r.get("code") not in MOVING:
            continue
        if (r.get("label") or "").startswith("exercise and sell") or "unchanged" in (r.get("label") or ""):
            continue
        tk = (r.get("ticker") or "").upper()
        try:
            v = float(r.get("value") or 0)
        except ValueError:
            v = 0.0
        try:
            apa = float(r.get("avg_price_adjusted") or 0) or None
        except ValueError:
            apa = None
        try:
            h, n, o = float(r.get("holding_after") or 0), float(r.get("net_change") or 0), float(r.get("outstanding") or 0)
            before = (h - n) / o * 100 if o else None
        except ValueError:
            before = None
        events.setdefault(tk, []).append({
            "d": (r.get("traded") or r.get("filed") or "")[:10], "c": r["code"],
            "v": v, "apa": apa, "sh": float(r.get("shares") or 0),
            # for the trade line on the card (2026-09-18): the kind, the stake before and after
            "plan": r.get("plan") or "", "label": r.get("label") or "", "pre_ipo": r.get("pre_ipo") or "",
            "filed": (r.get("filed") or "")[:10],
            "after": float(r["pct_after"]) if r.get("pct_after") else None, "before": before})
    panel = list(csv.DictReader(open(panel_p, encoding="utf-8-sig")))
    return sp, prices, founders, events, panel


def read_series(store, tk):
    try:
        with open(os.path.join(store, f"{tk}.csv"), encoding="utf-8", newline="") as fh:
            rd = csv.reader(fh)
            next(rd, None)
            return [(d, float(c)) for d, c in rd if d]
    except (OSError, ValueError):
        return []


class Fonts:
    def __init__(self, fonts_dir):
        from PIL import ImageFont
        self.dir = fonts_dir
        self.ImageFont = ImageFont
        self._cache = {}

    def _get(self, name, size, weight=None):
        key = (name, size, weight)
        if key not in self._cache:
            f = self.ImageFont.truetype(os.path.join(self.dir, name), size)
            if weight is not None:
                try:
                    f.set_variation_by_axes([weight] if name.startswith("Hanken")
                                            else [min(96, max(12, size)), weight, 100])
                except Exception:  # noqa: BLE001
                    pass
            self._cache[key] = f
        return self._cache[key]

    def disp(self, s, w=650):
        return self._get("BricolageGrotesque[opsz,wdth,wght].ttf", s, w)

    def ui(self, s, w=500):
        return self._get("HankenGrotesk[wght].ttf", s, w)

    def mono(self, s):
        return self._get("IBMPlexMono-Medium.ttf", s)


def draw_card(out, fonts, tk, co, ceo, founder, sealed, pct, value, shares, series, evs, price_asof):
    """THE LINK CARD IS THE POST CARD (2026-09-18). A card is seen for a
    second in a feed, most often under an X post about a founder move; it
    shows the company, the person, the newest trade in its colour with the
    amount and the date, the stake before and after as the largest thing
    on it, and a year of closes as a sparkline with the day marked. A
    sealed company's card shows the name, the person and the price line,
    no stake and no trade: those are what a subscription buys."""
    import post_card
    latest = None
    if evs:
        trades = [e for e in evs if e.get("c") in ("P", "S") and not e.get("pre_ipo")]
        if trades:
            latest = max(trades, key=lambda e: (e.get("filed") or "", e.get("d") or ""))
    kind = post_card.post_kind({"code": latest["c"], "plan": latest.get("plan", ""), "label": latest.get("label", ""), "pre_ipo": ""}) if latest else None
    return post_card.draw(out, tk, co, ceo, bool(founder), kind, latest["v"] if latest else None,
                          latest["d"] if latest else None,
                          latest.get("before") if latest else None,
                          (latest.get("after") if latest and latest.get("after") is not None else pct) if not sealed else None,
                          series, fonts_dir=fonts.dir, height=H, sealed=sealed)


def _day(s):
    y, m, dd = int(s[:4]), int(s[5:7]), int(s[8:10])
    return y * 372 + (m - 1) * 31 + dd     # ordinal enough for a scale


def main(panel_p, sp_p, prices_p, founders_p, events_p, store, out_dir, only=None):
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("  company cards: Pillow missing; none drawn")
        return 0
    here = os.path.dirname(os.path.abspath(__file__))
    fonts = Fonts(os.path.join(here, "fonts"))
    sp, prices, founders, events, panel = load_inputs(panel_p, sp_p, prices_p, founders_p, events_p)
    price_asof = ""
    try:
        price_asof = next(csv.DictReader(open(prices_p, encoding="utf-8-sig"))).get("as_of", "")
    except Exception:  # noqa: BLE001
        pass
    os.makedirs(out_dir, exist_ok=True)
    n = 0
    only = {t.upper() for t in only} if only else None
    for r in panel:
        tk = (r.get("ticker") or "").upper()
        if not tk or (only and tk not in only):
            continue
        try:
            pct = float(r.get("pct")) if r.get("pct") else None
            shares = float(r.get("shares")) if r.get("shares") else None
        except ValueError:
            pct, shares = None, None
        value = (shares * prices[tk]) if (shares and tk in prices) else None
        series = read_series(store, tk)
        try:
            draw_card(os.path.join(out_dir, f"{tk}.png"), fonts, tk, r.get("company") or tk,
                      r.get("ceo") or "", founders.get(tk, ""), tk not in sp, pct, value, shares,
                      series, events.get(tk, []), price_asof)
            n += 1
        except Exception as exc:  # noqa: BLE001 - one bad card never stops the rest
            print(f"  company cards: {tk} not drawn ({exc.__class__.__name__}: {exc})")
    print(f"  company cards: {n} drawn -> {out_dir}/")
    return 0


def card_version(out_dir, tk):
    """The hash the page appends to the card's URL, so a redrawn card is a
    new address to every unfurler's cache. Empty when there is no card."""
    p = os.path.join(out_dir, f"{tk}.png")
    try:
        with open(p, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()[:10]
    except OSError:
        return ""


if __name__ == "__main__":
    args = sys.argv[1:]
    only = None
    if "--only" in args:
        i = args.index("--only")
        only = args[i + 1].split(",")
        del args[i:i + 2]
    raise SystemExit(main(*args[:7], only=only))
