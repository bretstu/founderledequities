#!/usr/bin/env python3
"""The account's banner and avatar, in the site's type, from the site's numbers.

    python3 ops/brand.py panel.csv universe/sp500-<date>.csv prices.csv founders.csv out_dir/

Writes banner.png (1500x500, X's size) and avatar-*.png (400x400). The banner
carries the thesis sentence and the hero's strip; the bottom-left quarter is
left empty because X lays the avatar over it.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from og_image import numbers, money  # noqa: E402


def fonts(fonts_dir):
    from PIL import ImageFont

    def font(name, size, weight=None):
        f = ImageFont.truetype(os.path.join(fonts_dir, name), size)
        if weight is not None:
            try:
                f.set_variation_by_axes([weight] if name.startswith("Hanken")
                                        else [min(96, max(12, size)), weight, 100])
            except Exception:  # noqa: BLE001
                pass
        return f
    return (lambda s, w=650: font("BricolageGrotesque[opsz,wdth,wght].ttf", s, w),
            lambda s: font("IBMPlexMono-Medium.ttf", s))


INK, BLUE, MUT, FAINT, LINE = "#0C0D0E", "#1B34E0", "#5D6167", "#8A8E94", "#E6E6E0"


def banner(n, out, fonts_dir):
    from PIL import Image, ImageDraw
    disp, mono = fonts(fonts_dir)
    W, H = 1500, 500
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    # the thesis, top left, clear of the avatar (which sits bottom-left)
    big = disp(64, 650)
    d.text((80, 70), "What every CEO owns", font=big, fill=INK)
    d.text((80, 144), "of the company they run.", font=big, fill=INK)
    d.text((80, 232), f"{n['total']:,} US public companies · computed from SEC filings, never estimated",
           font=mono(19), fill=MUT)
    # the strip, bottom right, the hero's own numbers
    facts = [(f"{n['above5']} of {n['open']}", "S&P 500 CEOs own over 5%", BLUE),
             (f"{n['led']}", "founder-led companies", INK),
             (money(n["led_value"]), "held by those founders", INK)]
    x = 560
    d.line((560, 330, W - 80, 330), fill=LINE, width=2)
    for val, lab, col in facts:
        d.text((x, 356), val, font=disp(40, 700), fill=col)
        d.text((x, 410), lab.upper(), font=mono(13), fill=MUT)
        x += max(d.textlength(val, font=disp(40, 700)), d.textlength(lab.upper(), font=mono(13))) + 56
    d.text((W - 80, 452), "founderledequities.com", font=mono(16), fill=FAINT, anchor="ra")
    im.save(out, "PNG", optimize=True)


def avatar(out, fonts_dir, style):
    from PIL import Image, ImageDraw
    disp, mono = fonts(fonts_dir)
    S = 400
    bg, fg = {"ink": (INK, "white"), "blue": (BLUE, "white"), "white": ("white", INK)}[style]
    im = Image.new("RGB", (S, S), bg)
    d = ImageDraw.Draw(im)
    if style == "white":
        d.ellipse((6, 6, S - 6, S - 6), outline=INK, width=6)
    f = disp(150, 750)
    # "FLE", the E in the site's blue on the dark discs
    x = (S - d.textlength("FLE", font=f)) / 2
    y = S / 2 - 100
    d.text((x, y), "FL", font=f, fill=fg)
    d.text((x + d.textlength("FL", font=f), y), "E", font=f, fill=BLUE if style == "white" else "#9FB0FF")
    im.save(out, "PNG", optimize=True)


def main(panel_p, sp_p, prices_p, founders_p, out_dir):
    here = os.path.dirname(os.path.abspath(__file__))
    fonts_dir = os.path.join(here, "fonts")
    os.makedirs(out_dir, exist_ok=True)
    n = numbers(panel_p, sp_p, prices_p, founders_p)
    banner(n, os.path.join(out_dir, "banner.png"), fonts_dir)
    for style in ("ink", "blue", "white"):
        avatar(os.path.join(out_dir, f"avatar-{style}.png"), fonts_dir, style)
    print(f"  wrote banner.png and avatar-ink/blue/white.png to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:6]))
