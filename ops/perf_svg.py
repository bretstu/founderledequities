#!/usr/bin/env python3
"""Founders against the index, as one static SVG for the Method page.

    python3 ops/perf_svg.py perf.csv founders.csv universe/sp500-*.csv public/perf.svg

THE CHART IS EVIDENCE, NOT A PRODUCT (PLAN.md; decided 2026-09-14). It
left the home page and the nav because nobody uses it twice: it is the
argument for why founder-led is worth screening, and it lives under
"Why founder-led" on the Method page, drawn once at deploy from the same
numbers the interactive version drew, with the same caveat.

THE SERIES, as the page computed them: equal weight, rebalanced monthly.
Each month's founder return is the plain average of the monthly returns of
every founder-led company in the cohort with a close this month and last.
Companies enter when their prices do; the line starts when at least five
founders and the benchmark have data. Growth of $10,000, against SPY and
the equal-weight RSP. The cohort is the founder-led members of the S&P
500, the chart's default on the page.

SURVIVORSHIP is stated on the chart: the cohort is the founders in the
index today, not those who were in it each year, and a company that was
founder-led in 2018 and is hired-led now is not in the line. The chart is
a portrait of the survivors, not a strategy.
"""
import csv
import sys
from collections import defaultdict

BASE = 10000.0
INK, MUT, FAINT, LINE = "#1A1A1A", "#5F5B55", "#8C8880", "#E8E4DC"


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def series(perf_p, founders_p, sp_p):
    closes = defaultdict(dict)
    for r in read(perf_p):
        try:
            closes[(r["ticker"] or "").upper()][r["month"]] = float(r["close"])
        except (ValueError, KeyError):
            continue
    founders = {r["ticker"].upper() for r in read(founders_p) if (r.get("founder") or "").lower() == "yes"}
    sp = {r["ticker"].upper() for r in read(sp_p)}
    spy = sorted(closes.get("SPY", {}).items())
    if len(spy) < 2:
        return None
    months = [m for m, _ in spy]
    cohort = [t for t in closes if t in founders and t in sp and t not in ("SPY", "RSP")]
    fret = []
    for i in range(1, len(months)):
        a, b = months[i - 1], months[i]
        s, n = 0.0, 0
        for t in cohort:
            ca, cb = closes[t].get(a), closes[t].get(b)
            if ca and cb:
                s += cb / ca - 1
                n += 1
        fret.append((b, s / n if n else None, n))
    s0 = 0
    while s0 < len(fret) and (fret[s0][1] is None or fret[s0][2] < 5):
        s0 += 1
    if len(fret) - s0 < 2:
        return None
    rsp = closes.get("RSP", {})
    out = {"months": [months[s0]], "founders": [BASE], "spy": [BASE], "rsp": [BASE] if rsp else None,
           "count": len(cohort)}
    spymap = dict(spy)
    for i in range(s0, len(fret)):
        m, r, _ = fret[i]
        out["months"].append(m)
        out["founders"].append(out["founders"][-1] * (1 + (r or 0)))
        a, b = months[i], months[i + 1]
        out["spy"].append(out["spy"][-1] * (spymap[b] / spymap[a] if spymap.get(a) and spymap.get(b) else 1))
        if out["rsp"] is not None:
            ra, rb = rsp.get(a), rsp.get(b)
            out["rsp"].append(out["rsp"][-1] * (rb / ra if ra and rb else 1))
    return out


def money(v):
    return "$" + (f"{round(v):,}" if v >= 1000 else f"{v:.0f}")


def svg(d, w=940, h=320):
    pad = {"l": 56, "r": 180, "t": 18, "b": 30}
    n = len(d["months"])
    allv = d["founders"] + d["spy"] + (d["rsp"] or [])
    y0, y1 = min(allv), max(allv)
    yr = (y1 - y0) or 1
    y0, y1 = max(0, y0 - yr * .08), y1 + yr * .08
    X = lambda i: pad["l"] + i / ((n - 1) or 1) * (w - pad["l"] - pad["r"])
    Y = lambda v: h - pad["b"] - (v - y0) / (y1 - y0) * (h - pad["t"] - pad["b"])
    line = lambda a: " ".join(f"{'L' if i else 'M'} {X(i):.1f} {Y(v):.1f}" for i, v in enumerate(a))
    years = sorted({m[:4] for m in d["months"]})
    step = max(1, -(-len(years) // 7))
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" '
             f'aria-label="Founders against the index: growth of $10,000, the founder-led members of the S&amp;P 500 against SPY">']
    for v in (y0 + (y1 - y0) * .1, (y0 + y1) / 2, y1 - (y1 - y0) * .1):
        parts.append(f'<line x1="{pad["l"]}" x2="{w - pad["r"]}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{LINE}"/>'
                     f'<text x="{pad["l"] - 8}" y="{Y(v) + 4:.1f}" text-anchor="end" font-family="IBM Plex Mono,Menlo,monospace" font-size="10" fill="{FAINT}">{money(v)}</text>')
    for j, y in enumerate(years):
        if j % step:
            continue
        i = next((k for k, m in enumerate(d["months"]) if m[:4] == y), -1)
        if i >= 0:
            parts.append(f'<text x="{X(i):.1f}" y="{h - 8}" text-anchor="middle" font-family="IBM Plex Mono,Menlo,monospace" font-size="10" fill="{FAINT}">{y}</text>')
    if d["rsp"]:
        parts.append(f'<path d="{line(d["rsp"])}" fill="none" stroke="#B5B0A6" stroke-width="1.5" stroke-dasharray="4 3" stroke-linejoin="round"/>')
    parts.append(f'<path d="{line(d["spy"])}" fill="none" stroke="{MUT}" stroke-width="1.7" stroke-linejoin="round"/>')
    parts.append(f'<path d="{line(d["founders"])}" fill="none" stroke="{INK}" stroke-width="2.2" stroke-linejoin="round"/>')
    ends = [("F", Y(d["founders"][-1])), ("S", Y(d["spy"][-1]))]
    if d["rsp"]:
        ends.append(("R", Y(d["rsp"][-1])))
    ends.sort(key=lambda e: e[1])
    ys = [e[1] for e in ends]
    for i in range(1, len(ys)):
        if ys[i] - ys[i - 1] < 30:
            ys[i] = ys[i - 1] + 30
    lab = dict(zip([e[0] for e in ends], ys))
    x = w - pad["r"] + 8
    parts.append(f'<text x="{x}" y="{lab["F"] - 2:.1f}" font-family="IBM Plex Mono,Menlo,monospace" font-size="11.5" font-weight="600" fill="{INK}">Founders index</text>'
                 f'<text x="{x}" y="{lab["F"] + 11:.1f}" font-family="IBM Plex Mono,Menlo,monospace" font-size="10.5" fill="{INK}">{money(d["founders"][-1])}</text>')
    parts.append(f'<text x="{x}" y="{lab["S"] - 2:.1f}" font-family="IBM Plex Mono,Menlo,monospace" font-size="11.5" fill="{MUT}">S&amp;P 500 (SPY)</text>'
                 f'<text x="{x}" y="{lab["S"] + 11:.1f}" font-family="IBM Plex Mono,Menlo,monospace" font-size="10.5" fill="{FAINT}">{money(d["spy"][-1])}</text>')
    if d["rsp"]:
        parts.append(f'<text x="{x}" y="{lab["R"] - 2:.1f}" font-family="IBM Plex Mono,Menlo,monospace" font-size="11.5" fill="{FAINT}">S&amp;P equal weight (RSP)</text>'
                     f'<text x="{x}" y="{lab["R"] + 11:.1f}" font-family="IBM Plex Mono,Menlo,monospace" font-size="10.5" fill="#B5B0A6">{money(d["rsp"][-1])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def main(perf_p, founders_p, sp_p, out_p):
    d = series(perf_p, founders_p, sp_p)
    if not d:
        print("  perf.svg: not enough data; nothing written")
        return 1
    with open(out_p, "w", encoding="utf-8") as fh:
        fh.write(svg(d))
    print(f"  perf.svg: {d['count']} S&P founders, {d['months'][0]} to {d['months'][-1]}, "
          f"founders {money(d['founders'][-1])} vs SPY {money(d['spy'][-1])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
