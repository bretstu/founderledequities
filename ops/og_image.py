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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def numbers(panel_p, sp_p, prices_p, founders_p):
    """The hero's numbers over the whole universe (one tree, 2026-09-23);
    sp_p rides in the signature so every caller passes the same files."""
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
    # THE HERO'S OWN STRIP, BY THE HERO'S OWN RULES: everything over every
    # company, so the card says exactly what a visitor then sees.
    total = open_n = above5 = led = 0
    led_value = all_value = 0.0
    for r in csv.DictReader(open(panel_p, encoding="utf-8-sig")):
        t = (r.get("ticker") or "").upper()
        # WHAT THE PAGE COUNTS. Its list keeps a company only when it has a
        # measured stake and a share count (mapPanel's filter); 35 of the
        # 2,135 do not, and the hero says 2,100. A stamp that counted every
        # row said 2,135 for the first second and 2,100 after.
        try:
            pct = float(r.get("pct") or "")
            sh = float(r.get("shares") or 0)
        except ValueError:
            continue
        total += 1
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
        # strip only a decimal's trailing zeros: "1.30" -> "1.3", never "370" -> "37"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return "$" + s + suf
    return f"${v:,.0f}"


def draw(n, out, fonts_dir):
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1200, 630
    # design b (2026-09-29): the company cards' palette and faces
    from company_cards import Fonts, INK, BLUE, MUT, FAINT, LINE, PAPER, PANEL
    F = Fonts(fonts_dir)
    disp, ui, mono = F.disp, F.ui, F.mono

    im = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(im)
    # wordmark
    d.text((72, 60), "Founder Led", font=disp(30, 700), fill=INK)
    wm = d.textlength("Founder Led ", font=disp(30, 700))
    d.text((72 + wm, 60), "Equities", font=disp(30, 700), fill=INK)
    d.text((W - 72, 68), "founderledequities.com", font=ui(18, 500), fill=FAINT, anchor="ra")

    # the purpose, the hero's own sentence
    big = disp(72, 700)
    y = 150
    d.text((72, y), "What every ", font=big, fill=INK)
    x = 72 + d.textlength("What every ", font=big)
    d.text((x, y), "CEO", font=big, fill=INK)
    x += d.textlength("CEO ", font=big)
    d.text((x, y), "owns", font=big, fill=INK)
    d.text((72, y + 84), "of the company they run.", font=big, fill=INK)
    d.text((72, y + 190), "Computed from their SEC filings, never estimated.", font=ui(24, 500), fill=MUT)

    # the hero's stat strip, the same three numbers in the same order
    d.rounded_rectangle((60, 440, W - 60, 552), radius=14, fill=PANEL)
    facts = [(f"{n['above5']}", "CEOs own more than 5%", BLUE),
             (f"{n['led']}", "Founder-led companies", INK),
             (money(n["led_value"]), "Held by those founders", INK),
             (f"{n['share']}%", "Of all CEO wealth", INK)]
    x = 84
    for val, lab, col in facts:
        d.text((x, 462), val, font=disp(34, 700), fill=col)
        d.text((x, 510), lab.upper(), font=ui(12, 600), fill=MUT)
        x += max(d.textlength(val, font=disp(34, 700)), d.textlength(lab.upper(), font=ui(12, 600))) + 56
    # the footer: how much is measured, and where it comes from
    d.text((72, 578), f"{n['total']:,} US public companies · every number computed from SEC EDGAR, never estimated",
           font=ui(14, 500), fill=FAINT)
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
