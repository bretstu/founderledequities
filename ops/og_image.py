#!/usr/bin/env python3
"""The card a shared link unfurls into, drawn from the site's own numbers.

    python3 ops/og_image.py panel.csv universe/sp500-<date>.csv prices.csv founders.csv og.png

A LINK WITHOUT A CARD IS A LINK NOBODY READS. The page declared a
summary_large_image card and shipped no image, so every shared link
unfurled as a bare title. This draws one at deploy, 1200x630, in the
site's own type, carrying the hero's finding computed from tonight's panel
-- so the card is never a stale poster of a number the site no longer
says. Fonts live in ops/fonts/ (the same three the page loads from Google,
OFL-licensed); if Pillow or the fonts are missing the deploy keeps the
existing og.png rather than shipping a broken one.
"""
import csv
import os
import sys


def numbers(panel_p, sp_p, prices_p, founders_p):
    sp = {r["ticker"] for r in csv.DictReader(open(sp_p, encoding="utf-8-sig"))}
    prices = {}
    try:
        for r in csv.DictReader(open(prices_p, encoding="utf-8-sig")):
            try:
                prices[r["ticker"].upper()] = float(r["close"])
            except (ValueError, KeyError):
                pass
    except OSError:
        pass
    founders = set()
    try:
        for r in csv.DictReader(open(founders_p, encoding="utf-8-sig")):
            if (r.get("founder") or "").lower() == "yes":
                founders.add(r["ticker"].upper())
    except OSError:
        pass
    total = open_n = above5 = 0
    founder_value = 0.0
    for r in csv.DictReader(open(panel_p, encoding="utf-8-sig")):
        t = (r.get("ticker") or "").upper()
        try:
            pct = float(r.get("pct") or "")
            sh = float(r.get("shares") or 0)
        except ValueError:
            continue
        total += 1
        if t in sp:
            open_n += 1
            if pct > 5:
                above5 += 1
        if t in founders and t in prices:
            founder_value += sh * prices[t]
    return dict(total=total, open=open_n, above5=above5, founder_value=founder_value)


def money(v):
    if v >= 1e12:
        return f"${v/1e12:.2f}T"
    if v >= 1e9:
        return f"${v/1e9:.0f}B"
    return f"${v/1e6:.0f}M"


def draw(n, out, fonts_dir):
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1200, 630
    INK, BLUE, MUT, FAINT, LINE = "#0C0D0E", "#1B34E0", "#5D6167", "#8A8E94", "#E6E6E0"

    def font(name, size, weight=None):
        f = ImageFont.truetype(os.path.join(fonts_dir, name), size)
        if weight is not None:
            try:
                # Bricolage's axes run optical size, weight, width -- in that
                # order; Hanken has weight alone
                f.set_variation_by_axes([weight] if name.startswith("Hanken")
                                        else [min(96, max(12, size)), weight, 100])
            except Exception:  # noqa: BLE001 - a static font has no axes
                pass
        return f

    disp = lambda s, w=650: font("BricolageGrotesque[opsz,wdth,wght].ttf", s, w)
    ui = lambda s, w=500: font("HankenGrotesk[wght].ttf", s, w)
    mono = lambda s: font("IBMPlexMono-Medium.ttf", s)

    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    # wordmark
    d.text((72, 60), "Founder Led", font=disp(30, 700), fill=INK)
    wm = d.textlength("Founder Led ", font=disp(30, 700))
    d.text((72 + wm, 60), "Equities", font=disp(30, 700), fill=BLUE)
    d.text((W - 72, 68), "founderledequities.com", font=mono(18), fill=FAINT, anchor="ra")

    # the finding, the hero's sentence
    big = disp(78, 650)
    y = 150
    num = f"{n['above5']}"
    d.text((72, y), num, font=big, fill=BLUE)
    x = 72 + d.textlength(num + " ", font=big)
    d.text((x, y), f"of {n['open']} chief executives", font=big, fill=INK)
    d.text((72, y + 88), "own more than 5% of the", font=big, fill=INK)
    d.text((72, y + 176), "company they run.", font=big, fill=INK)

    # the strip of facts
    d.line((72, 470, W - 72, 470), fill=LINE, width=2)
    facts = [(f"{n['total']:,}", "US public companies"),
             (money(n["founder_value"]), "held by founders who run them"),
             ("SEC EDGAR", "every number computed, never estimated")]
    x = 72
    for val, lab in facts:
        d.text((x, 496), val, font=disp(34, 700), fill=INK)
        d.text((x, 546), lab.upper(), font=mono(14), fill=MUT)
        x += max(d.textlength(val, font=disp(34, 700)), d.textlength(lab.upper(), font=mono(14))) + 64
    im.save(out, "PNG", optimize=True)
    return out


def main(panel_p, sp_p, prices_p, founders_p, out):
    here = os.path.dirname(os.path.abspath(__file__))
    fonts_dir = os.path.join(here, "fonts")
    n = numbers(panel_p, sp_p, prices_p, founders_p)
    try:
        draw(n, out, fonts_dir)
    except Exception as exc:  # noqa: BLE001 - never fail a deploy over a picture
        print(f"  og image: not drawn ({exc.__class__.__name__}: {exc}); keeping the existing one")
        return 0
    print(f"  og image: {n['above5']} of {n['open']} above 5%, {n['total']:,} companies, "
          f"{money(n['founder_value'])} founder-held -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:6]))
