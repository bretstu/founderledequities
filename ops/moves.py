#!/usr/bin/env python3
"""THE MOVES OF THE STAKE, the site's ranking, as drafts a person can post
from (2026-09-15; replaces fact.py --today and --monday).

    python3 ops/moves.py today                 # drafts/moves-today.md: every founder filing since yesterday, by the move
    python3 ops/moves.py week [DATE]           # drafts/moves-week.md: the week (Mon-Fri) ending the last Friday on or before DATE
    python3 ops/moves.py stakes [DATE]         # drafts/stakes-month.md: whose stake changed most over 30, 90 and 365 days, and why

THE PIPELINE SUGGESTS; A PERSON PUBLISHES. Nothing here posts anywhere.

ONE RANKING, EVERY KIND. The site exists to say what a founder owns and how
it changes; a purchase, a planned sale, an award, a gift and a forfeiture
are all filings that move the stake, and ops/kinds.py (the page's own
taxonomy) names each. Every line carries the kind and its detail, the
amount when the form states one, the move as a share of the holding, the
stake after, the confidence word when it is not high, whether the company
is outside the S&P (the stake is the site's own number, sealed on the
page), and the company's URL, never the home page.

THE WEEK IS MONDAY TO FRIDAY. EDGAR accepts no filings at the weekend, so
by Saturday morning the week is complete; the week file is written on
Saturday for the week just closed, and a run on any other day reports the
last complete week.

THE GUARDS TRAVEL (index.html, evMove): a pre-IPO catch-up row is not a
move; a filing with no purchase or sale that takes the position on record
to zero is not ranked, and goes under "needs a look"; a conversion or an
"other transaction" says "read the filing", because code J does not say
why; the confidence word rides on the line.

THE TRAJECTORY IS COMPUTED IN SHARES. Percent-of-holding moves do not add
(a stake that sold 60% twice did not sell 120%), so the reason a stake
changed over a window is decomposed from the record: the holding's change
against the share count as the window opened, split by kind from the
filings' own net changes (restated through splits by the history row that
carries the same accession), the share count's own change, and an honest
"unexplained" residual, which is what the walk could not attribute.
"""
import csv
import datetime as dt
import math
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SITE = "https://founderledequities.com"
sys.path.insert(0, HERE)
import kinds  # noqa: E402

THRESHOLDS = (1.0, 5.0, 10.0, 25.0, 50.0)


def num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def nice(d):
    try:
        return dt.date.fromisoformat(d).strftime("%b %-d")
    except (ValueError, TypeError):
        return d or ""


def pct(p):
    return "" if p is None else (f"{p:.3f}%" if p < 1 else f"{p:.2f}%")


def read(root, name):
    p = os.path.join(root, name)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def week_bounds(date):
    """(monday, friday) of the last complete week on or before `date`: a
    Saturday run reports Monday to Friday just closed; a Wednesday run the
    previous week, because this week is not complete."""
    d = dt.date.fromisoformat(date)
    back = (d.weekday() - 4) % 7          # days since the last Friday (0 on a Friday)
    friday = d - dt.timedelta(days=back)
    return (friday - dt.timedelta(days=4)).isoformat(), friday.isoformat()


class Data:
    def __init__(self, root):
        self.root = root
        self.panel = {r["ticker"].upper(): r for r in read(root, "panel.csv") if r.get("ticker")}
        self.founders = {r["ticker"].upper(): (r.get("founder") or "").lower() for r in read(root, "founders.csv") if r.get("ticker")}
        self.prices = {r["ticker"].upper(): num(r.get("close")) for r in read(root, "prices.csv") if r.get("ticker")}
        self.events = [dict(e, tk=(e.get("ticker") or "").upper()) for e in read(root, "events.csv")]
        self.hist = defaultdict(list)
        for h in read(root, "history.csv"):
            if h.get("ticker"):
                self.hist[h["ticker"].upper()].append(h)
        for hs in self.hist.values():
            hs.sort(key=lambda h: (h.get("date") or "", h.get("accession") or ""))
        sp_files = []
        try:
            sp_files = sorted(f for f in os.listdir(os.path.join(root, "universe")) if f.startswith("sp500-") and f.endswith(".csv"))
        except OSError:
            pass
        self.sp = {r["ticker"].upper() for r in read(root, os.path.join("universe", sp_files[-1])) if r.get("ticker")} if sp_files else set()

    def founder(self, tk):
        return self.founders.get(tk) == "yes"

    def sealed(self, tk):
        return tk not in self.sp

    def conf(self, tk):
        return (self.panel.get(tk, {}).get("confidence") or "").lower()

    def rows(self, since, until, founders_only=True):
        """Every filing filed in (since, until], founders only, pre-IPO out."""
        out = []
        for e in self.events:
            if not (since < (e.get("filed") or "") <= until) or kinds._pre(e):
                continue
            if founders_only and not self.founder(e["tk"]):
                continue
            # THE DRAFTS CARRY EVERY NUMBER: the seal is the page's display
            # rule, and here it is a flag on the line (kinds.move_of blanks a
            # row keyed "sealed", so the flag has another name)
            out.append(dict(e, outside_sp=self.sealed(e["tk"])))
        return out

    def first_sale(self, e):
        """No earlier sale that moved the stake by this person: the first."""
        if kinds.group_of(e) != "sold":
            return False
        for x in self.events:
            if x["tk"] == e["tk"] and (x.get("filed") or "") < (e.get("filed") or "") and kinds.group_of(x) == "sold" and not kinds._pre(x):
                return False
        return True


# ---------------------------------------------------------------- one line
def move_words(m):
    """The move in words so it cannot be read as points of the company:
    'sold 23% of the stake', 'added 3.9% to the stake', 'the stake ×2.4'."""
    if m is None:
        return "move not stated"
    v = m[0]
    if abs(v) < 0.05:
        return "the stake unchanged"
    if v >= 100:
        return f"the stake ×{1 + v / 100:.1f}"
    if v <= -100:
        return "the stake sold out"
    mag = f"{abs(v):.0f}%" if abs(v) >= 10 else f"{abs(v):.1f}%" if abs(v) >= 1 else f"{abs(v):.2f}%"
    return f"added {mag} to the stake" if v > 0 else f"cut the stake by {mag}"


def what(e):
    """What happened, in the tape's words: 'bought $2.6M on the open market',
    'sold $7.1M under a pre-set plan', 'was granted shares', 'gave shares
    away', 'exercised options and kept them'."""
    k = kinds.kind_of(e)
    v = num(e.get("value")) if not (e.get("price_flag") or "") else None
    amt = f" {kinds.money(v)}" if v else ""
    lb = e.get("label") or ""
    if k == "bought":
        return f"bought{amt} on the open market" if (e.get("plan") or "") != "plan" else f"bought{amt} under a pre-set plan"
    if k == "disc":
        return f"sold{amt} at their own discretion"
    if k == "plan":
        return f"sold{amt} under a pre-set plan"
    if k == "sold":
        return f"sold{amt} (plan not stated: a pre-2023 form)"
    if k == "comp":
        return {"award granted": "was granted shares", "award granted, tax withheld": "was granted shares, tax withheld",
                "options exercised": "exercised options and kept the shares", "options exercised, tax withheld": "exercised options, tax withheld",
                "shares withheld for tax": "had shares withheld for tax", "forfeited": "forfeited shares",
                "exercise and sell": f"cashed options{amt}", "exercise, part sold": f"cashed options{amt}, part kept",
                "vested and sold": f"vested, part sold{amt}", "convert and sell": f"converted and sold{amt}"}.get(lb, f"compensation: {kinds.detail_of(e)}")
    return {"gift": "gave shares away", "converted": "converted shares (read the filing)"}.get(lb, "other transaction (read the filing)")


def line(d, e, mark=True):
    """One draft line: who, what, the move, the stake after, the flags, the URL."""
    tk, ceo = e["tk"], e.get("ceo") or d.panel.get(e["tk"], {}).get("ceo") or ""
    m = kinds.move_of(e)
    after = num(e.get("pct_after"))
    guard = (e.get("code") or "") not in ("P", "S") and after == 0 and num(e.get("pct_of_holding")) is not None
    parts = [f"{ceo} {what(e)}" + (f" across {e['n']} filings" if e.get("n", 1) > 1 else ""), nice(e.get("traded") or e.get("filed"))]
    if guard:
        parts.append("position on record to zero; not ranked until a filing explains it")
    else:
        parts.append(move_words(m))
    if after is not None and not guard:
        parts.append(f"now owns {pct(after)}")
    flags = []
    if d.conf(tk) and d.conf(tk) != "high":
        flags.append(f"confidence {d.conf(tk)}")
    if e.get("outside_sp"):
        flags.append("outside the S&P: the stake is in Pro")
    if mark:
        if str(e.get("first_buy") or "") == "1":
            flags.append("FIRST BUY EVER")
        if d.first_sale(e):
            flags.append("first sale on record")
        v = num(e.get("value")) if not (e.get("price_flag") or "") else None
        if kinds.kind_of(e) == "disc" and v and v >= 10e6:
            flags.append("$10M+ at discretion")
        if m and after is not None and after > 0 and m[0] > -100:
            before = after / (1 + m[0] / 100)
            for t in THRESHOLDS:
                if before < t <= after:
                    flags.append(f"crossed {t:g}% upward")
                if after < t <= before:
                    flags.append(f"fell below {t:g}%")
    return f"- {tk} · " + " · ".join(p for p in parts if p) + (("  ← " + ", ".join(flags)) if flags else "") + f"\n  {SITE}/company/{tk}/"


def ranked(rows):
    return kinds.sorted_rows(rows)


def collapse(rows):
    """ONE ROW PER PERSON PER KIND, as the letter does: four planned sales by
    one founder in a week are one line (the amounts summed, the moves
    summed, the stake after the last one, the count noted), not four lines
    that crowd out everyone else."""
    out, seen = [], {}
    for e in sorted(rows, key=lambda e: (e.get("traded") or e.get("filed") or "", e.get("filed") or "")):
        key = (e["tk"], e.get("ceo"), kinds.kind_of(e), e.get("label") if kinds.kind_of(e) in ("comp", "xfer") else "")
        if key in seen and not is_guarded(e):
            g = seen[key]
            g["n"] += 1
            v, gv = num(e.get("value")), num(g.get("value"))
            g["value"] = "" if (v is None and gv is None) else str((v or 0) + (gv or 0))
            m, gm = num(e.get("pct_of_holding")), num(g.get("pct_of_holding"))
            g["pct_of_holding"] = "" if (m is None or gm is None) else str(m + gm)
            g["pct_after"] = e.get("pct_after")
            g["traded"], g["filed"] = e.get("traded"), e.get("filed")
            g["first_buy"] = "1" if str(g.get("first_buy") or "") == "1" or str(e.get("first_buy") or "") == "1" else ""
            continue
        g = dict(e, n=1)
        seen[key] = g
        out.append(g)
    return out


def by_move(rows):
    """Every kind together, the largest move first; unranked rows after,
    newest first. The guarded rows are left out (see needs_a_look)."""
    ok = [e for e in rows if not is_guarded(e)]
    r = [e for e in ok if kinds.move_of(e) is not None]
    u = [e for e in ok if kinds.move_of(e) is None]
    r.sort(key=lambda e: -abs(kinds.move_of(e)[0]))
    u.sort(key=lambda e: e.get("filed") or "", reverse=True)
    return r + u


def is_guarded(e):
    return (e.get("code") or "") not in ("P", "S") and num(e.get("pct_after")) == 0 and num(e.get("pct_of_holding")) is not None


def spoken(rows):
    """The weather line as a sentence a person can post."""
    c = kinds.counts(rows)
    s = f"{c['bought']} founder{'' if c['bought'] == 1 else 's'} bought"
    if c["first"]:
        s += f" ({c['first']} for the first time ever)"
    s += f". {c['disc']} sold without a plan. {c['plan']} sale{' was' if c['plan'] == 1 else 's were'} already scheduled."
    if c["paid"]:
        s += f" {c['paid']} {'was' if c['paid'] == 1 else 'were'} paid in shares."
    if c["gave"]:
        s += f" {c['gave']} gave shares away."
    return s


# ---------------------------------------------------------------- today
def today_md(d, since):
    rows = d.rows(since, "9999-12-31")
    head = (f"# Founders' filings since {since} · every move, largest first · pick one, write the sentence, post. "
            f"The pipeline suggests; you publish.\n\n")
    if not rows:
        return head + "(nothing filed)\n"
    out = [line(d, e) for e in by_move(rows)]
    look = [line(d, e, mark=False) for e in rows if is_guarded(e)]
    body = "\n".join(out) + "\n"
    if look:
        body += "\n## Needs a look before anything is said\n\n" + "\n".join(look) + "\n"
    return head + body


# ---------------------------------------------------------------- the week
def week_md(d, date):
    monday, friday = week_bounds(date)
    since = (dt.date.fromisoformat(monday) - dt.timedelta(days=1)).isoformat()
    rows = d.rows(since, friday)
    head = f"# The week of {nice(monday)} to {nice(friday)}, founders only · paste, do not auto-post\n\n"
    if not rows:
        return head + "(nothing filed)\n"
    order = by_move(collapse(rows))
    top = order[:10]
    buys = [e for e in order if kinds.kind_of(e) == "bought"]
    top_buy = max(buys, key=lambda e: num(e.get("value")) or 0) if buys else None
    top_move = order[0] if order and kinds.move_of(order[0]) is not None else None
    out = ["## The thread: three posts, then the tape", "", "1.", "This week: " + spoken(rows), ""]
    n = 2
    if top_move is not None:
        out += [f"{n}.", post_line(d, top_move), ""]; n += 1
    if top_buy is not None and top_buy is not top_move:
        out += [f"{n}.", post_line(d, top_buy), ""]; n += 1
    out += [f"{n}.", f"Every filing of the week, founders first, free: {SITE}/tape/", ""]
    out += ["## The ten largest moves of the week, every kind", ""] + [line(d, e) for e in top] + [""]
    decisions = [e for e in order if kinds.kind_of(e) in ("bought", "disc") and e not in top]
    if decisions:
        out += ["## The other decisions (a purchase or a sale at their own discretion, any size)", ""] + [line(d, e) for e in decisions] + [""]
    look = [line(d, e, mark=False) for e in rows if is_guarded(e)]
    if look:
        out += ["## Needs a look before anything is said", ""] + look + [""]
    # THE LETTER'S SHORTLISTS (2026-09-20). Two lists the issue is built from:
    # the decisions, ranked for the feature and the two shorter moves; and the
    # filings that moved a stake by a percent or more, whatever their kind,
    # plus the largest planned sales, for the "Moved the stake" section.
    out += ["## Candidates for the feature (decisions only, ranked)", "",
            "score = log10(dollars) + 2 × |share of holding, %| (+1 for a buy, +0.5 for a stake over 5%)", ""]
    cands = []
    for e in collapse(rows):
        k = kinds.kind_of(e)
        if k not in ("bought", "disc") or is_guarded(e):
            continue
        v = num(e.get("value")) or 0
        m = kinds.move_of(e)
        share = abs(m[0]) if m else 0.0
        after = num(e.get("pct_after")) or 0
        score = (math.log10(v) if v > 0 else 0) + 2 * share + (1 if k == "bought" else 0) + (0.5 if after >= 5 else 0)
        cands.append((score, e, v, share, after, k))
    cands.sort(key=lambda x: -x[0])
    for score, e, v, share, after, k in cands[:8]:
        out.append(f"- {e['tk']:6} {e.get('ceo') or d.panel.get(e['tk'], {}).get('ceo') or '':24} {'BUY ' if k == 'bought' else 'SALE'} "
                   f"{kinds.money(v):>8}  {share:5.2f}% of holding  stake {pct(after):>7}  score {score:.1f}")
    out.append("")
    out += ["## Moved the stake (a percent of the holding or more, any kind) and the largest planned sales", ""]
    moved = [e for e in collapse(rows) if (m := kinds.move_of(e)) and abs(m[0]) >= 1.0 and not is_guarded(e)]
    moved.sort(key=lambda e: -abs(kinds.move_of(e)[0]))
    for e in moved:
        out.append(f"- {e['tk']:6} {e.get('ceo') or '':24} {kinds.kind_of(e):6} {what(e)[:50]:50} {kinds.money(num(e.get("value")) or 0):>8}  {kinds.move_of(e)[0]:+.2f}% of holding  stake {pct(num(e.get('pct_after')) or 0)}")
    plans = sorted([e for e in collapse(rows) if kinds.kind_of(e) == "plan"], key=lambda e: -(num(e.get("value")) or 0))[:3]
    for e in plans:
        out.append(f"- {e['tk']:6} {e.get('ceo') or '':24} plan   sold on a plan set months ago{'':16} {kinds.money(num(e.get("value")) or 0):>8}  stake {pct(num(e.get('pct_after')) or 0)}")
    out.append("")
    return head + "\n".join(out)


def post_line(d, e):
    """The post: one sentence, the URL. A large cut or a plan is checked
    against both filings on the page before it is public."""
    m = kinds.move_of(e)
    s = line(d, e, mark=False)
    if kinds.kind_of(e) == "plan" or (m and abs(m[0]) >= 10):
        s += "\n  (read both filings on the page before this one is public)"
    return s


# ---------------------------------------------------------------- the trajectory
def split_ratio(d, e):
    """shares today per share as filed, from the history row that carries
    the same accession; 1 when the record has no such row."""
    for h in d.hist.get(e["tk"], []):
        if h.get("accession") and h.get("accession") == e.get("accession"):
            a, b = num(h.get("shares_split_adjusted")), num(h.get("shares"))
            if a and b:
                return a / b
    return 1.0


def at(d, tk, date):
    """The record's last point on or before `date`: (pct, shares, outstanding)."""
    last = None
    for h in d.hist.get(tk, []):
        if (h.get("date") or "") <= date and num(h.get("pct")) is not None:
            last = h
    if last is None:
        return None
    # THE SHARES ARE SPLIT-ADJUSTED IN THE RECORD, THE COUNT IS NOT (Carvana's
    # 5:1: 29.6M shares of 215M became 148M adjusted of 215M unadjusted), so
    # the denominator is restated by the same ratio to keep the units of pct
    raw, adj, out = num(last.get("shares")), num(last.get("shares_split_adjusted")), num(last.get("outstanding"))
    ratio = adj / raw if raw and adj else 1.0
    return num(last.get("pct")), (adj if adj is not None else raw), (out * ratio if out else out)


def trajectory(d, tk, t0, t1):
    """pct then and now, and the reason in shares: {bought, sold, comp,
    xfer, count, unexplained} as % of the holding as the window opened.
    None when the record has no point before the window."""
    a, b = at(d, tk, t0), at(d, tk, t1)
    if not a or not b or not a[0]:
        return None
    p0, s0, o0 = a
    p1, s1, o1 = b
    res = {"then": p0, "now": p1, "change": (p1 - p0) / p0 * 100, "by": {}}
    if not (s0 and o0 and o1) or s1 is None:
        return res
    holding = (s1 - s0) / o0 * 100               # points from the holding changing
    count = p1 - (p0 + holding)                  # points from the share count changing
    by = defaultdict(float)
    for e in d.events:
        if e["tk"] != tk or not (t0 < (e.get("filed") or "") <= t1) or kinds._pre(e):
            continue
        nc = num(e.get("net_change"))
        if nc is None:
            continue
        by[kinds.group_of(e)] += nc * split_ratio(d, e) / o0 * 100
    explained = sum(by.values())
    by["count"] = count
    by["unexplained"] = holding - explained
    res["by"] = {k: v / p0 * 100 for k, v in by.items()}
    return res


def reason(t):
    """'sold 61%, compensation +8%, the share count −12%, unexplained 3%'"""
    if not t or not t.get("by"):
        return "the record has no filing in the window"
    words = {"bought": "bought", "sold": "sold", "comp": "compensation", "xfer": "transfers", "count": "the share count", "unexplained": "unexplained"}
    parts = []
    for k, v in sorted(t["by"].items(), key=lambda x: -abs(x[1])):
        if abs(v) < 1 or (k == "unexplained" and abs(v) < 2):
            continue
        parts.append(f"{words[k]} {v:+.0f}%")
    return ", ".join(parts) or "nothing above 1%"


def year_clause(d, tk, date, days=365):
    """', from 3.1% a year ago (sold −18%, compensation +4%)' or ''."""
    t0 = (dt.date.fromisoformat(date) - dt.timedelta(days=days)).isoformat()
    t = trajectory(d, tk, t0, date)
    if not t:
        return ""
    big = any(abs(v) >= 5 for v in t.get("by", {}).values())
    if abs(t["change"]) < 1:
        # FLAT IS A SENTENCE TOO when it is sales and grants cancelling
        return f", unchanged from {pct(t['then'])} a year ago ({reason(t)})" if big else ""
    return f", from {pct(t['then'])} a year ago ({reason(t)})"


def stakes_md(d, date):
    out = [f"# Whose stake changed most, as of {date} · founders only · the reason computed from the record\n"]
    out.append("The move is a share of the holding, not points of the company. 'The share count' is the company's cover pages; "
               "'unexplained' is what the walk could not attribute to a filing, and a large one is a page to read before anything is said. "
               "A stake outside the S&P is the site's own number and is in Pro.\n")
    founders = [tk for tk in d.panel if d.founder(tk)]
    for days, label in ((30, "30 days"), (90, "90 days"), (365, "12 months")):
        t0 = (dt.date.fromisoformat(date) - dt.timedelta(days=days)).isoformat()
        rows = []
        for tk in founders:
            t = trajectory(d, tk, t0, date)
            if t and t["now"] is not None:
                rows.append((t, tk))
        rows.sort(key=lambda x: x[0]["change"])
        up = sum(1 for t, _ in rows if t["change"] > 1)
        down = sum(1 for t, _ in rows if t["change"] < -1)
        out.append(f"\n## {label}: {len(rows)} founders with a record · {down} down more than 1% · {up} up more than 1% · {len(rows) - up - down} flat\n")
        for title, sel in (("Reduced most", [x for x in rows if x[0]["change"] <= -1][:8]),
                           ("Grew most", [x for x in reversed(rows) if x[0]["change"] >= 1][:8])):
            out.append(f"\n### {title}\n")
            if not sel:
                out.append("(none)")
            for t, tk in sel:
                r = d.panel[tk]
                flags = []
                if d.conf(tk) and d.conf(tk) != "high":
                    flags.append(f"confidence {d.conf(tk)}")
                if d.sealed(tk):
                    flags.append("outside the S&P")
                if t["now"] == 0:
                    flags.append("STAKE TO ZERO: a departure or a misread; read the page")
                out.append(f"- {tk} · {r.get('ceo') or ''} · {pct(t['then'])} → {pct(t['now'])} ({t['change']:+.0f}% of the holding) · {reason(t)}"
                           + (("  ← " + ", ".join(flags)) if flags else "") + f"\n  {SITE}/company/{tk}/")
    out.append(since_last_saturday(d, date))
    # milestones over the last 30 days
    t0 = (dt.date.fromisoformat(date) - dt.timedelta(days=30)).isoformat()
    ms = []
    for tk in founders:
        t = trajectory(d, tk, t0, date)
        if not t:
            continue
        a, b = t["then"], t["now"]
        for th in THRESHOLDS:
            if a < th <= b:
                ms.append(f"- {tk} · {d.panel[tk].get('ceo') or ''} · crossed {th:g}% upward ({pct(a)} → {pct(b)})\n  {SITE}/company/{tk}/")
            if b < th <= a:
                ms.append(f"- {tk} · {d.panel[tk].get('ceo') or ''} · fell below {th:g}% ({pct(a)} → {pct(b)})\n  {SITE}/company/{tk}/")
    out.append("\n## Milestones in the last 30 days\n")
    out += ms or ["(none)"]
    # the cohort
    vals = [num(d.panel[tk].get("shares")) * (d.prices.get(tk) or 0) for tk in founders if num(d.panel[tk].get("shares"))]
    out.append(f"\n## The cohort\n\n{len(founders)} founder-CEOs hold {kinds.money(sum(vals))} of the companies they run; "
               f"{sum(1 for tk in founders if (num(d.panel[tk].get('pct')) or 0) >= 25)} own a quarter or more, "
               f"{sum(1 for tk in founders if (num(d.panel[tk].get('pct')) or 0) >= 10)} a tenth or more.\n")
    return "\n".join(out) + "\n"


def since_last_saturday(d, date):
    """WHAT CHANGED THIS WEEK, FROM THE RECORD (2026-09-15; ops/weekly.py kept
    a snapshot of the panel to say this, and is retired): stakes crossing
    5/10/25/50% between the record's point a week ago and today; never-sold
    streaks that ended (a founder's first stake-moving sale on record);
    companies that began Section 16 reporting (an IPO or a spin, from the
    events' registered date); the board, the ten largest founder stakes by
    value at today's close, ranked against the same holdings a week ago at
    today's close, so a rank move is the holding moving, never the price."""
    t0 = (dt.date.fromisoformat(date) - dt.timedelta(days=7)).isoformat()
    founders = [tk for tk in d.panel if d.founder(tk)]
    items = []
    for tk in founders:
        a, b = at(d, tk, t0), at(d, tk, date)
        if not a or not b or a[0] is None or b[0] is None:
            continue
        for th in THRESHOLDS[1:]:
            if a[0] < th <= b[0]:
                items.append(f"- {tk} · {d.panel[tk].get('ceo') or ''} · crossed {th:g}% upward ({pct(a[0])} → {pct(b[0])})\n  {SITE}/company/{tk}/")
            if b[0] < th <= a[0]:
                items.append(f"- {tk} · {d.panel[tk].get('ceo') or ''} · fell below {th:g}% ({pct(a[0])} → {pct(b[0])})\n  {SITE}/company/{tk}/")
    for e in d.rows(t0, date):
        if d.first_sale(e):
            items.append(f"- {e['tk']} · {e.get('ceo') or ''} · never-sold streak ended: the first stake-moving sale on record, {nice(e.get('traded') or e.get('filed'))}\n  {SITE}/company/{e['tk']}/")
    reg = {}
    for e in d.events:
        if e.get("registered") and t0 < e["registered"] <= date:
            reg[e["tk"]] = e["registered"]
    for tk, r in sorted(reg.items(), key=lambda kv: kv[1], reverse=True):
        items.append(f"- {tk} · {d.panel.get(tk, {}).get('company') or ''} · began Section 16 reporting on {r} (an IPO or a spin)\n  {SITE}/company/{tk}/")
    out = ["\n## Since last Saturday\n"] + (items or ["(nothing crossed a line, no streak ended, no company joined)"])
    # the board
    vals = []
    for tk in founders:
        sh, px = num(d.panel[tk].get("shares")), d.prices.get(tk)
        if sh and px:
            vals.append((sh * px, tk))
    vals.sort(reverse=True)
    prior = []
    for tk in founders:
        a, px = at(d, tk, t0), d.prices.get(tk)
        if a and a[1] and px:
            prior.append((a[1] * px, tk))
    prior.sort(reverse=True)
    prior_rank = {tk: i + 1 for i, (_, tk) in enumerate(prior)}
    out.append("\n## The board: the ten largest founder stakes by value, at today's close\n")
    for i, (v, tk) in enumerate(vals[:10], 1):
        mv = ""
        if prior_rank.get(tk):
            dlt = prior_rank[tk] - i
            mv = f" · ↑{dlt} on the week" if dlt > 0 else f" · ↓{-dlt} on the week" if dlt < 0 else ""
        out.append(f"- {i}. {tk} · {d.panel[tk].get('ceo') or ''} · {kinds.money(v)} · {pct(num(d.panel[tk].get('pct')))} of the company{mv}\n  {SITE}/company/{tk}/")
    # one number, several candidates
    sold = {e["tk"] for e in d.events if kinds.group_of(e) == "sold" and not kinds._pre(e)}
    never = sum(1 for tk in founders if tk not in sold)
    above5 = sum(1 for tk in d.sp if tk in d.panel and (num(d.panel[tk].get("pct")) or 0) > 5)
    out.append("\n## One number (candidates)\n")
    out.append(f"- {above5} of {len(d.sp)} S&P 500 CEOs own more than 5% of the company they run")
    out.append(f"- {never} founder-CEOs have never made a stake-moving sale since the company was public")
    return "\n".join(out)


# ---------------------------------------------------------------- main
def main(argv):
    root = ROOT
    d = Data(root)
    drafts = os.path.join(root, "drafts")
    os.makedirs(drafts, exist_ok=True)
    cmd = argv[0] if argv else ""
    date = argv[1] if len(argv) > 1 else dt.date.today().isoformat()
    if cmd == "today":
        since = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        p = os.path.join(drafts, "moves-today.md")
        text = today_md(d, since)
        open(p, "w", encoding="utf-8").write(text)
        print(f"  {p}: {text.count(chr(10) + '- ')} line(s)")
        return 0
    if cmd == "week":
        p = os.path.join(drafts, "moves-week.md")
        open(p, "w", encoding="utf-8").write(week_md(d, date))
        print(f"  {p}")
        return 0
    if cmd == "stakes":
        p = os.path.join(drafts, "stakes-month.md")
        open(p, "w", encoding="utf-8").write(stakes_md(d, date))
        print(f"  {p}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
