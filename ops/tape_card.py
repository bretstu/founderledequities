#!/usr/bin/env python3
"""The tape's card (1200x630) for X, Slack and iMessage: the week in one
sentence, the three biggest decisions, the address. Drawn at every deploy
from the same rows the page and the letter use, so the Monday link
unfurls to this week rather than to the site's general picture.

    python3 ops/tape_card.py og/tape.png
"""
import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)


def draw(out):
    from PIL import Image, ImageDraw, ImageFont
    import letter  # noqa: E402
    W, H = 1200, 630
    PAPER, INK, MUT, FAINT, LINE = "#F7F4EE", "#1A1A1A", "#5F5B55", "#8C8880", "#D6D1C7"
    GREEN, RED, GRAY = "#1F6B3A", "#B23428", "#6E6A64"
    fonts = os.path.join(HERE, "fonts")

    def var(f, w):
        try:
            axes = f.get_variation_axes()
            vals = []
            for a in axes:
                nm = (a["name"].decode() if isinstance(a["name"], bytes) else a["name"]).lower()
                vals.append(w if nm.startswith("weight") else a["default"])
            f.set_variation_by_axes(vals)
        except Exception:  # noqa: BLE001 - a static font has no axes
            pass
        return f

    def serif(size, w=500):
        p = os.path.join(fonts, "Fraunces.ttf")
        if not os.path.exists(p):
            p = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
        f = ImageFont.truetype(p, size)
        try:
            axes = f.get_variation_axes()
            vals = []
            for a in axes:
                nm = (a["name"].decode() if isinstance(a["name"], bytes) else a["name"]).lower()
                vals.append(w if nm.startswith("weight") else min(max(size, 9), 144) if nm.startswith("optical") else a["default"])
            f.set_variation_by_axes(vals)
        except Exception:  # noqa: BLE001
            pass
        return f

    ui = lambda s, w=500: var(ImageFont.truetype(os.path.join(fonts, "HankenGrotesk[wght].ttf"), s), w)
    mono = lambda s: ImageFont.truetype(os.path.join(fonts, "IBMPlexMono-Medium.ttf"), s)

    date = dt.date.today().isoformat()
    rows, since = letter.week_rows(ROOT, date)
    if not rows:
        # the file's newest filing day, when the run is older than a week (a rebuild from an old file)
        import csv
        newest = max((r.get("filed") or "" for r in csv.DictReader(open(os.path.join(ROOT, "events.csv"), encoding="utf-8-sig"))), default=date)
        date = newest
        rows, since = letter.week_rows(ROOT, date)
    c = letter.collapse(rows)
    who = lambda k: len({(r["tk"], r["ceo"]) for r in rows if r["kind"] == k})
    b, d, p = who("bought"), who("disc"), who("plan")

    im = Image.new("RGB", (W, H), PAPER)
    g = ImageDraw.Draw(im)
    g.text((72, 56), "FOUNDER LED EQUITIES", font=mono(16), fill=FAINT)
    g.text((W - 72, 56), f"{letter.nice_day(since)} to {letter.nice_day(date)}", font=mono(16), fill=FAINT, anchor="ra")
    g.text((72, 100), "This week's tape.", font=serif(64), fill=INK)
    line1 = f"{b} founder{'s' if b != 1 else ''} bought. {d} sold without a plan."
    line2 = f"{p} sale{' was' if p == 1 else 's were'} already scheduled."
    g.text((72, 196), line1, font=ui(30, 500), fill=INK)
    g.text((72, 236), line2, font=ui(30, 500), fill=MUT)
    g.line((72, 296, W - 72, 296), fill=INK, width=2)

    # the three biggest decisions: buys by amount, then discretionary sales
    buys = sorted([r for r in c if r["kind"] == "bought"], key=lambda r: -(r["value"] or 0))
    discs = sorted([r for r in c if r["kind"] == "disc"], key=lambda r: -(r["value"] or 0))
    picks = (buys[:2] + discs[:1]) if len(buys) >= 2 else (buys + discs)[:3]
    y = 322
    for r in picks[:3]:
        kind, col = ("BOUGHT", GREEN) if r["kind"] == "bought" else ("DISCRETIONARY", RED)
        g.text((72, y + 6), kind, font=mono(15), fill=col)
        g.text((260, y), r["tk"], font=ui(24, 600), fill=INK)
        name = r["ceo"]
        g.text((360, y), name[:34] + ("…" if len(name) > 34 else ""), font=ui(24, 400), fill=INK)
        amt = letter.money(r["value"]) if r["value"] and not r["flag"] else ""
        g.text((930, y), amt, font=mono(22), fill=INK, anchor="ra")
        g.text((1128, y), letter.pct(r["after"]) if r["after"] is not None else "", font=mono(22), fill=MUT, anchor="ra")
        y += 54
        g.line((72, y - 10, W - 72, y - 10), fill=LINE, width=1)
    g.text((72, H - 70), "Every filing of the week, founders first, free.", font=ui(20, 500), fill=MUT)
    g.text((W - 72, H - 70), "founderledequities.com/tape", font=mono(18), fill=FAINT, anchor="ra")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    im.save(out)
    print(f"  tape card: {b} bought, {d} discretionary, {p} planned; {len(picks[:3])} rows")
    return 0


if __name__ == "__main__":
    sys.exit(draw(sys.argv[1] if len(sys.argv) > 1 else "og/tape.png"))
