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
        events.setdefault(tk, []).append({
            "d": (r.get("traded") or r.get("filed") or "")[:10], "c": r["code"],
            "v": v, "apa": apa, "sh": float(r.get("shares") or 0)})
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
    """The name above, the chart below, and nothing to read in between.

    A card is seen for a second in a feed. The version this replaces
    carried a stake sentence, a value line and a caption; the picture is
    the point, and the page it links to has the words. The percentage
    stays, top right, for an open company: it is the one figure a reader
    would share the card for. A sealed company's card shows the name, the
    person, and the public price line, and no dots."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im, "RGBA")

    # ---- the top: wordmark, address
    d.text((64, 46), "Founder Led Equities", font=fonts.disp(22, 700), fill=INK)
    d.text((W - 64, 50), "founderledequities.com", font=fonts.mono(15), fill=FAINT, anchor="ra")

    # ---- the company and the person
    name_f = fonts.disp(52, 700)
    title = co
    # leave room for the percentage on the right when there is one
    room = W - 128 - (300 if (pct is not None and not sealed) else 0)
    while d.textlength(title, font=name_f) > room and len(title) > 8:
        title = title[:-2].rstrip() + "\u2026"
    d.text((64, 100), title, font=name_f, fill=INK)
    y = 172
    who = ceo or "chief executive not identified"
    d.text((64, y), who, font=fonts.ui(23, 700), fill=INK)
    x = 64 + d.textlength(who, font=fonts.ui(23, 700)) + 10
    d.text((x, y + 1), "\u00b7 CEO", font=fonts.ui(22, 500), fill=MUT)
    x += d.textlength("\u00b7 CEO", font=fonts.ui(22, 500)) + 14
    if founder == "yes":
        bf = fonts.mono(12)
        bw = d.textlength("FOUNDER", font=bf) + 18
        d.rounded_rectangle((x, y + 4, x + bw, y + 25), radius=5, fill=INK)
        d.text((x + 9, y + 8), "FOUNDER", font=bf, fill="white")

    # ---- the answer, top right, only when it is public
    if not sealed and pct is not None:
        d.text((W - 64, 100), f"{pct:.2f}%", font=fonts.disp(52, 700), fill=BLUE, anchor="ra")
        d.text((W - 64, 172), "of the company", font=fonts.ui(20, 500), fill=MUT, anchor="ra")

    # ---- the chart
    top, bottom, left, right = 250, 572, 84, W - 40
    if len(series) < 2:
        d.text((64, 300), "No price record for this company yet.", font=fonts.ui(18), fill=FAINT)
        im.save(out, "PNG", optimize=True)
        return
    t0 = _day(series[0][0])
    t1 = max(_day(series[-1][0]), t0 + 1)
    drawn = [] if sealed else [e for e in evs if series[0][0] <= e["d"] <= series[-1][0]]
    lo = min(c for _, c in series)
    hi = max(c for _, c in series)
    for e in drawn:
        if e["apa"]:
            lo, hi = min(lo, e["apa"]), max(hi, e["apa"])
    lo = max(lo, 1e-3)
    L0 = math.log(lo) - (math.log(hi) - math.log(lo)) * 0.08
    L1 = math.log(hi) + (math.log(hi) - math.log(lo)) * 0.14

    def X(day):
        return left + (_day(day) - t0) / (t1 - t0) * (right - left)

    def Y(v):
        return bottom - (math.log(v) - L0) / ((L1 - L0) or 1) * (bottom - top)

    # gridlines at round prices, at most five
    ticks = []
    for e in range(int(math.floor(math.log10(lo))) - 1, int(math.ceil(math.log10(hi))) + 1):
        for m in (1, 1.5, 2, 3, 5, 7):
            v = m * 10 ** e
            if L0 < math.log(v) < L1:
                ticks.append(v)
    while len(ticks) > 5:
        del ticks[-2::-2]
    for v in ticks:
        yy = Y(v)
        d.line((left, yy, right, yy), fill=LINE, width=1)
        d.text((left - 10, yy), dollars(v), font=fonts.mono(13), fill=FAINT, anchor="rm")
    y0, y1 = int(series[0][0][:4]), int(series[-1][0][:4])
    for yr in range(y0 + 1, y1 + 1):
        xx = X(f"{yr}-01-01")
        if left <= xx <= right:
            d.text((xx, H - 24), str(yr), font=fonts.mono(13), fill=FAINT, anchor="mm")
    # the line, thinned to the pixel, and the shading under it
    pts, lastx = [], -9
    for day, c in series:
        xx = X(day)
        if pts and xx - lastx < 0.8:
            continue
        lastx = xx
        pts.append((xx, Y(c)))
    poly = pts + [(pts[-1][0], bottom), (pts[0][0], bottom)]
    d.polygon(poly, fill=(27, 52, 224, 22))
    d.line(pts, fill=INK, width=2, joint="curve")
    # the trades, largest first so small ones sit on top
    vmax = max([e["v"] for e in drawn] + [1.0])

    def close_at(day):
        v = series[0][1]
        for dd, c in series:
            if dd <= day:
                v = c
            else:
                break
        return v
    for e in sorted(drawn, key=lambda e: -e["v"]):
        yv = e["apa"] if e["apa"] else close_at(e["d"])
        xx, yy = X(e["d"]), Y(yv)
        r = 4 + 7 * math.sqrt(e["v"] / vmax)
        col = BUY if e["c"] == "P" else SELL
        d.ellipse((xx - r - 1.5, yy - r - 1.5, xx + r + 1.5, yy + r + 1.5), fill=PAPER)
        d.ellipse((xx - r, yy - r, xx + r, yy + r), fill=col)
    # the last close
    lx, ly = pts[-1]
    d.text((lx - 4, ly - 12), dollars(series[-1][1]), font=fonts.mono(15), fill=INK, anchor="rs")
    # the key: two words, only when there are dots
    if drawn:
        d.ellipse((left, H - 32, left + 10, H - 22), fill=BUY)
        d.text((left + 16, H - 33), "bought", font=fonts.mono(13), fill=MUT)
        d.ellipse((left + 86, H - 32, left + 96, H - 22), fill=SELL)
        d.text((left + 102, H - 33), "sold", font=fonts.mono(13), fill=MUT)
    im.save(out, "PNG", optimize=True)


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
