#!/usr/bin/env python3
"""The weekly briefing: everything the week produced that a person might
write about, ranked, with receipts.

    python3 ops/weekly.py                       # the last 7 days, to weekly/<date>.md and .json
    python3 ops/weekly.py --since 2026-08-30    # a longer window when a week was skipped
    python3 ops/weekly.py --out /tmp/brief.md

NOT A NEWSLETTER TEMPLATE. The structure of what gets written may change
every week; this script's job is to notice, rank and cite, and then get
out of the way. Every section is present even when empty ("none this
week"), because absence is information too. Every item carries the company
page and, where there is one, the filing.

It reads only what the nightly already publishes -- events.csv, panel.csv,
founders.csv, prices.csv, history.csv, perf.csv, the S&P list -- and one
thing it keeps for itself: a snapshot of the panel each time it runs, so
the next run can say what CHANGED (a stake crossing 10%, a never-sold
streak ending, a new name in the top ten). The first run has no prior.

The rules are the site's rules: a trade "moved the stake" unless the
events stage labelled it kept apart (options cashed, units converted,
position unchanged) or pre-registration; a founder is a founder because
the proxy says so; nothing here is computed differently from the page.
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys

SITE = "https://founderledequities.com"
KEPT_APART = {"exercise and sell", "convert and sell", "sale, position unchanged",
              "purchase, position unchanged"}
THRESHOLDS = (5.0, 10.0, 25.0, 50.0)


# ---------------------------------------------------------------- helpers
def num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def money(v):
    if v is None:
        return "—"
    a = abs(v)
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            x = v / div
            s = f"{x:.2f}" if abs(x) < 10 else f"{x:.1f}" if abs(x) < 100 else f"{x:.0f}"
            return f"${s}{suf}"
    return f"${v:,.0f}"


def read(path):
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def page(tk):
    return f"{SITE}/company/{tk}/"


def moved(e):
    """The site's rule: a trade moved the stake unless kept apart or pre-registration."""
    if e.get("code") not in ("P", "S"):
        return False
    if (e.get("label") or "") in KEPT_APART:
        return False
    if (e.get("pre_ipo") or "").strip() in ("1", "true", "True"):
        return False
    return True


def pct_of_stake(e):
    p = num(e.get("pct_of_holding"))
    if p is None:
        return "share of stake not stated"
    approx = "≈" if (e.get("pct_approx") or "").strip() in ("1", "true", "True") else ""
    sign = "+" if e.get("code") == "P" else "−"
    return f"{approx}{sign}{p:.1f}% of stake" if p >= 1 else f"{approx}{sign}{p:.2f}% of stake"


def plan_word(e):
    return {"plan": "planned", "discretionary": "discretionary"}.get((e.get("plan") or "").strip(), "")


def line(e, extra=""):
    tk = e["ticker"].upper()
    v = num(e.get("value"))
    what = money(v) if v and (e.get("price_flag") or "") != "unpriced" else f"{num(e.get('shares')) or 0:,.0f} sh"
    when = e.get("traded") or e.get("filed") or ""
    filed = e.get("filed") or ""
    lag = f", filed {filed}" if filed and filed != when else ""
    url = e.get("url") or ""
    return (f"- **{e.get('ceo') or ''}**, {tk} — {what} · {pct_of_stake(e)} · {plan_word(e)} · traded {when}{lag}"
            f"{(' · ' + extra) if extra else ''} · [page]({page(tk)})" + (f" · [filing]({url})" if url else ""))


# ---------------------------------------------------------------- the briefing
def build(root, since, until, out_md, out_json):
    events = read(os.path.join(root, "events.csv"))
    panel = {r["ticker"].upper(): r for r in read(os.path.join(root, "panel.csv")) if r.get("ticker")}
    founders = {r["ticker"].upper(): (r.get("founder") or "").lower() for r in read(os.path.join(root, "founders.csv")) if r.get("ticker")}
    prices = {r["ticker"].upper(): num(r.get("close")) for r in read(os.path.join(root, "prices.csv")) if r.get("ticker")}
    sp = set()
    try:
        cands = sorted(f for f in os.listdir(os.path.join(root, "universe")) if f.startswith("sp500-") and f.endswith(".csv"))
        if cands:
            sp = {r["ticker"].upper() for r in read(os.path.join(root, "universe", cands[-1]))}
    except OSError:
        pass
    is_founder = lambda tk: founders.get(tk) == "yes"

    week = [e for e in events if since <= (e.get("filed") or "") <= until]
    week_moved = [e for e in week if moved(e)]
    fw = [e for e in week_moved if is_founder(e["ticker"].upper())]
    by_val = lambda e: -(num(e.get("value")) or 0)

    B = {"window": {"since": since, "until": until}, "sections": {}}
    md = [f"# Weekly briefing — filings {since} to {until}", "",
          f"_Generated {dt.date.today().isoformat()} from the site's own files. Every line links its page and its filing. "
          f"Founders are founders because the proxy says so; a trade moved the stake unless the site kept it apart._", ""]

    def section(title, items, note=None, key=None):
        md.append(f"## {title}")
        if note:
            md.append(f"_{note}_")
        if items:
            md.extend(items)
        else:
            md.append("- none this week")
        md.append("")
        if key is not None:
            B["sections"][key] = items

    # 1. founders who bought
    buys = sorted([e for e in fw if e["code"] == "P"], key=by_val)
    items = []
    for e in buys:
        tk = e["ticker"].upper(); px = num(e.get("avg_price")); now = prices.get(tk)
        since_buy = f"paid ${px:,.2f}, now ${now:,.2f} ({(now / px - 1) * 100:+.1f}%)" if px and now else ""
        items.append(line(e, since_buy))
    section("Founders who bought (open market)", items, key="founder_buys")

    # 2. founders who sold, discretionary; with flags
    hist_by = {}
    for e in events:
        if moved(e) and e["code"] == "S":
            hist_by.setdefault(e["ticker"].upper(), []).append(e)
    sells_d = sorted([e for e in fw if e["code"] == "S" and (e.get("plan") or "") == "discretionary"], key=by_val)
    items = []
    for e in sells_d:
        tk = e["ticker"].upper(); flags = []
        prior = [x for x in hist_by.get(tk, []) if (x.get("filed") or "") < since]
        if not prior:
            flags.append("FIRST SALE ON RECORD")
        three = [x for x in prior if (x.get("filed") or "") >= (dt.date.fromisoformat(until) - dt.timedelta(days=1095)).isoformat()]
        v = num(e.get("value")) or 0
        if three and v > max(num(x.get("value")) or 0 for x in three):
            flags.append("largest sale in 3 years")
        p = num(e.get("pct_of_holding"))
        if p and p >= 5:
            flags.append(f"{p:.0f}% of the stake")
        items.append(line(e, " · ".join(flags)))
    section("Founders who sold, discretionary", items, key="founder_sells_discretionary")

    # 3. planned sales, summarised then listed
    sells_p = sorted([e for e in fw if e["code"] == "S" and (e.get("plan") or "") == "plan"], key=by_val)
    tot = sum(num(e.get("value")) or 0 for e in sells_p)
    section("Founders who sold on a plan", [line(e) for e in sells_p],
            note=f"{len(sells_p)} planned sales, {money(tot)} in total — context, not news, unless one is unusual",
            key="founder_sells_planned")

    # 4. headline vs filing: kept apart
    kept = sorted([e for e in week if e.get("code") in ("P", "S") and not moved(e) and is_founder(e["ticker"].upper())], key=by_val)
    items = []
    for e in kept[:12]:
        tk = e["ticker"].upper(); lab = e.get("label") or ""
        pre = (e.get("pre_ipo") or "").strip() in ("1", "true", "True")
        what = "pre-registration trade" if pre else lab
        items.append(line(e, f"KEPT APART: {what}; stake unchanged" + (f" at {num(panel[tk].get('pct')):.2f}%" if tk in panel and num(panel[tk].get("pct")) is not None else "")))
    section("Headline vs. filing (trades that did not move the stake)", items,
            note="the '$50M sale' that was options cashed or units converted — the correction is the story", key="kept_apart")

    # 5. streaks and clusters
    thirty = (dt.date.fromisoformat(until) - dt.timedelta(days=30)).isoformat()
    year = (dt.date.fromisoformat(until) - dt.timedelta(days=365)).isoformat()
    items = []
    for tk in sorted({e["ticker"].upper() for e in buys}):
        recent = [e for e in events if e["ticker"].upper() == tk and moved(e) and e["code"] == "P" and thirty <= (e.get("filed") or "") <= until]
        older = [e for e in events if e["ticker"].upper() == tk and moved(e) and e["code"] == "P" and (e.get("filed") or "") < since]
        last_older = max((e.get("filed") or "" for e in older), default="")
        if len(recent) >= 2:
            items.append(f"- **{recent[0].get('ceo')}**, {tk}: {len(recent)} purchases in 30 days, {money(sum(num(e.get('value')) or 0 for e in recent))} · [page]({page(tk)})")
        if older and last_older < year:
            items.append(f"- **{buys[0].get('ceo') if buys and buys[0]['ticker'].upper()==tk else recent[0].get('ceo')}**, {tk}: first purchase since {last_older} · [page]({page(tk)})")
        if not older:
            items.append(f"- **{recent[0].get('ceo')}**, {tk}: first open-market purchase on record · [page]({page(tk)})")
    section("Streaks and firsts", items, key="streaks")

    # 6. milestones from the snapshot
    snap_dir = os.path.join(root, "weekly", "snapshots")
    os.makedirs(snap_dir, exist_ok=True)
    priors = sorted(f for f in os.listdir(snap_dir) if f.endswith(".csv") and f < f"{until}.csv")
    prior = {r["ticker"].upper(): r for r in read(os.path.join(snap_dir, priors[-1]))} if priors else {}
    items = []
    sold_tickers = {e["ticker"].upper() for e in hist_by if any((x.get("filed") or "") < since for x in hist_by[e])} if False else set()
    if prior:
        for tk, r in panel.items():
            if not is_founder(tk):
                continue
            p0 = num(prior.get(tk, {}).get("pct")); p1 = num(r.get("pct"))
            if p0 is None or p1 is None:
                continue
            for t in THRESHOLDS:
                if p0 < t <= p1:
                    items.append(f"- **{r.get('ceo')}**, {tk}: stake crossed above {t:.0f}% ({p0:.2f}% → {p1:.2f}%) · [page]({page(tk)})")
                if p1 < t <= p0:
                    items.append(f"- **{r.get('ceo')}**, {tk}: stake fell below {t:.0f}% ({p0:.2f}% → {p1:.2f}%) · [page]({page(tk)})")
        # never-sold streaks that ended this week: a founder's first stake-moving sale ever
        for e in fw:
            if e["code"] == "S":
                tk = e["ticker"].upper()
                if not any((x.get("filed") or "") < since for x in hist_by.get(tk, [])):
                    items.append(f"- **{e.get('ceo')}**, {tk}: never-sold streak ended — first stake-moving sale on record · [page]({page(tk)})")
        new = [tk for tk in panel if tk not in prior]
        for tk in new[:15]:
            items.append(f"- {tk} ({panel[tk].get('company')}) joined the universe · [page]({page(tk)})")
    else:
        items.append("- (no prior snapshot yet; from next week this section shows stakes crossing 5/10/25/50%, never-sold streaks ending, and companies joining)")
    # newly registered issuers this week, from the events' registered date
    reg = {e["ticker"].upper(): e.get("registered") for e in events if e.get("registered")}
    for tk, d in sorted(reg.items(), key=lambda kv: kv[1], reverse=True):
        if since <= d <= until:
            items.append(f"- {tk} ({panel.get(tk, {}).get('company', '')}) began Section 16 reporting on {d} (an IPO or a spin) · [page]({page(tk)})")
    section("Milestones", items, key="milestones")

    # 7. the board and its moves
    vals = []
    for tk, r in panel.items():
        sh = num(r.get("shares")); px = prices.get(tk)
        if sh and px and is_founder(tk):
            vals.append((sh * px, tk, r))
    vals.sort(reverse=True)
    items = []
    prior_rank = {}
    if prior:
        pv = []
        for tk, r in prior.items():
            sh = num(r.get("shares")); px = num(r.get("_close"))
            if sh and px:
                pv.append((sh * px, tk))
        pv.sort(reverse=True)
        prior_rank = {tk: i + 1 for i, (_, tk) in enumerate(pv)}
    for i, (v, tk, r) in enumerate(vals[:10], 1):
        mv = ""
        if prior_rank.get(tk):
            d = prior_rank[tk] - i
            mv = f" (↑{d})" if d > 0 else f" (↓{-d})" if d < 0 else ""
        items.append(f"- {i}. **{r.get('ceo')}**, {tk} — {money(v)} · {num(r.get('pct')) or 0:.2f}% of the company{mv} · [page]({page(tk)})")
    section("The board: top ten founder stakes by value", items, key="top_ten")

    # 8. non-founder trades worth knowing (for comparison only)
    nf = sorted([e for e in week_moved if not is_founder(e["ticker"].upper()) and e["code"] == "P"], key=by_val)[:5]
    section("Non-founder CEOs who bought (comparison only — not the account's subject)",
            [line(e, "NON-FOUNDER") for e in nf], key="non_founder_buys")

    # 9. one number, several candidates
    above5 = sum(1 for tk in sp if tk in panel and (num(panel[tk].get("pct")) or 0) > 5)
    led = sum(1 for tk in panel if is_founder(tk))
    never = 0
    for tk in panel:
        if is_founder(tk) and not any(moved(e) and e["code"] == "S" for e in events if e["ticker"].upper() == tk):
            never += 1
    wealth = sum(v for v, _, _ in vals)
    musk = sum(v for v, tk, r in vals if (r.get("ceo") or "").lower().startswith("elon"))
    items = [
        f"- {above5} of {len(sp)} S&P 500 CEOs own more than 5% of the company they run",
        f"- {led} founder-led companies worth $1B or more; their founders hold {money(wealth)}",
        f"- {never} founder-CEOs have never made a stake-moving sale since the company was public",
        f"- Musk's two stakes are {money(musk)}, {100 * musk / wealth if wealth else 0:.0f}% of all founder wealth on the site",
        f"- this week: {len(buys)} founder purchases, {len(sells_d)} discretionary sales, {len(sells_p)} planned sales, {len(kept)} trades kept apart",
    ]
    section("One number (candidates)", items, key="numbers")

    # snapshot for next week (the panel plus the close, so value ranks can be compared)
    snap = os.path.join(snap_dir, f"{until}.csv")
    with open(snap, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["ticker", "pct", "shares", "_close", "founder"])
        for tk, r in panel.items():
            w.writerow([tk, r.get("pct", ""), r.get("shares", ""), prices.get(tk) or "", founders.get(tk, "")])

    with open(out_md, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(B, fh, indent=1)
    return {"buys": len(buys), "sells_d": len(sells_d), "sells_p": len(sells_p), "kept": len(kept), "md": out_md}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=".")
    ap.add_argument("--since", default=None, help="first filing date to include (default: 7 days ago)")
    ap.add_argument("--until", default=None, help="last filing date to include (default: today)")
    ap.add_argument("--out", default=None, help="markdown path (default: weekly/<until>.md)")
    a = ap.parse_args()
    until = a.until or dt.date.today().isoformat()
    since = a.since or (dt.date.fromisoformat(until) - dt.timedelta(days=7)).isoformat()
    os.makedirs(os.path.join(a.dir, "weekly"), exist_ok=True)
    out_md = a.out or os.path.join(a.dir, "weekly", f"{until}.md")
    out_json = os.path.splitext(out_md)[0] + ".json"
    r = build(a.dir, since, until, out_md, out_json)
    print(f"  briefing {since}..{until}: {r['buys']} founder purchases, {r['sells_d']} discretionary sales, "
          f"{r['sells_p']} planned, {r['kept']} kept apart -> {r['md']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
