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
    # THE HERO'S OWN STRIP, BY THE HERO'S OWN RULES: everything over the
    # open (S&P) set, so the card says exactly what a visitor then sees.
    total = open_n = above5 = led = 0
    led_value = all_value = 0.0
    for r in csv.DictReader(open(panel_p, encoding="utf-8-sig")):
        t = (r.get("ticker") or "").upper()
        try:
            pct = float(r.get("pct") or "")
            sh = float(r.get("shares") or 0)
        except ValueError:
            continue
        total += 1
        if t not in sp:
            continue
        open_n += 1
        if pct > 5:
            above5 += 1
        val = sh * prices[t] if t in prices else 0.0
        all_value += val
        if t in founders:
            led += 1
            led_value += val
    return dict(total=total, open=open_n, above5=above5, led=led,
                led_value=led_value, share=round(100 * led_value / all_value) if all_value else 0)


def money(v):
    """The page's money(): $1.03T, $27.3B, $903M -- same rounding, so the
    card and the hero never disagree by a cent of formatting."""
    for div, suf, dp in ((1e12, "T", 2), (1e9, "B", 1), (1e6, "M", 1)):
        if v < div * 0.9995:
            continue
        x = v / div
        s = f"{x:.0f}" if x >= 100 else f"{x:.{dp}f}"
        if float(s) >= 1000 and div < 1e12:
            continue
        return "$" + s.rstrip("0").rstrip(".") + suf
    return f"${v:,.0f}"


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
    d.text((x, y), f"of {n['open']} CEOs own", font=big, fill=INK)
    d.text((72, y + 88), "more than 5% of the", font=big, fill=INK)
    d.text((72, y + 176), "company they run.", font=big, fill=INK)

    # the hero's stat strip, the same three numbers in the same order
    d.line((72, 452, W - 72, 452), fill=LINE, width=2)
    facts = [(f"{n['led']}", "Founder-led companies", BLUE),
             (money(n["led_value"]), "Held by those founders", INK),
             (f"{n['share']}%", "Of all CEO wealth", INK)]
    x = 72
    for val, lab, col in facts:
        d.text((x, 474), val, font=disp(34, 700), fill=col)
        d.text((x, 522), lab.upper(), font=mono(13), fill=MUT)
        x += max(d.textlength(val, font=disp(34, 700)), d.textlength(lab.upper(), font=mono(13))) + 56
    # the footer: how much is measured, and where it comes from
    d.text((72, 578), f"{n['total']:,} US public companies · every number computed from SEC EDGAR, never estimated",
           font=mono(14), fill=FAINT)
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
    print(f"  og image: {n['above5']} of {n['open']} above 5%; {n['led']} founder-led, "
          f"{money(n['led_value'])}, {n['share']}% of the wealth; {n['total']:,} companies -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:6]))
