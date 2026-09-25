#!/usr/bin/env python3
"""Build the site's data files from the pipeline's staging output.

    python3 ops/build_site_data.py _staging/u-panel.csv _staging/u-history.csv \
        _staging/u-events.csv _staging/u-founders.csv \
        universe/sp500-<date>.csv site-data/

Layout produced (paths relative to the output dir) -- ONE TREE, EVERY
NUMBER IN IT (the free/Pro split left with the paid tier, 2026-09-23):
    universe.csv            every company, list-page columns, nothing masked
    founders.csv            passthrough (small)
    history/<T>.csv         per-ticker walk shards, every company
    events/<T>.csv          per-ticker event shards, every company, since 2016
    history-lite.csv        monthly-resolution history, the page's first load
    events.csv              the feed: the last year of filings, plus each
                            company's most recent stake-moving trade
    prices/<T>.csv          daily closes for EVERY ticker (with --prices)

The generator only reads and reshapes -- every number comes from the
pipeline files, nothing is computed here.
"""
import csv
import json
import os
import sys

from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kinds  # noqa: E402

# the compensation kinds, as the page defines them: a sale that did not move the stake
UNCHANGED_LABELS = kinds.COMP_LABELS  # the page's set (ops/kinds.py), one copy for every script

# EVERY COLUMN THE PAGE READS, OR THE PAGE READS A HOLE. The universe
# promotion moved the page from the raw panel to this list, and
# the first cut of this list dropped five columns mapPanel consumes:
# shares_as_of (every "As of" cell became "—"), operating_partnership
# (Blackstone printed 0.000% instead of "partnership units"), cautions (the
# drawer's raw flags lost half their text), and the two exclusion columns
# (the curated-exclusion note vanished). They are back. The mask below
# decides which of them a sealed row may carry.
LIST_COLS = ["ticker", "cik", "company", "ceo", "pct", "shares",
             "outstanding", "shares_as_of", "confidence", "stake_source",
             "problems", "cautions", "excluded_shares", "excluded_detail",
             "operating_partnership", "flags", "error", "form4_url",
             "cover_url", "outstanding_as_of", "shares_tabled", "sp"]
# the row's place over the whole panel, by value and by share, for any
# page that wants a rank without recomputing one
RANK_COLS = ["rank_value", "rank_pct"]


def _overlay(base_rows, fresh_path, sp, key="ticker"):
    """Rows for S&P tickers come from the FRESH file when one is given.

    The universe snapshot is static until its own refresh cadence exists;
    the S&P rebuilds nightly. Serving a fresh S&P beside a frozen
    remainder is the promotion's honest shape -- this merge is where it
    happens: fresh rows win for S&P tickers, the snapshot fills the rest."""
    if not fresh_path or not os.path.exists(fresh_path):
        return base_rows, False
    fresh = [r for r in csv.DictReader(open(fresh_path, encoding="utf-8-sig"))
             if r.get(key) in sp]
    if not fresh:
        return base_rows, False
    keep = [r for r in base_rows if r.get(key) not in sp]
    return keep + fresh, True


def one_year_returns(store: str, tickers) -> dict:
    """TICKER -> the stock's price return over the last twelve months, from
    the daily store: the newest close against the last close on or before
    365 days earlier. None when the series is shorter than a year. Public
    for every company: a price return is nobody's stake."""
    import datetime as dt
    out = {}
    if not store or not os.path.isdir(store):
        return out
    for tk in tickers:
        p = os.path.join(store, f"{tk}.csv")
        try:
            with open(p, encoding="utf-8", newline="") as fh:
                rd = csv.reader(fh)
                next(rd, None)
                pts = [(d, float(c)) for d, c in rd if d]
        except (OSError, ValueError):
            continue
        if len(pts) < 2:
            continue
        last_d, last_c = pts[-1]
        try:
            cut = (dt.date.fromisoformat(last_d) - dt.timedelta(days=365)).isoformat()
        except ValueError:
            continue
        base = None
        for d, c in pts:
            if d <= cut:
                base = c
            else:
                break
        if base and base > 0 and pts[0][0] <= cut:
            out[tk] = (last_c / base - 1.0) * 100.0
    return out


def write_price_shards(store: str, out_dir: str) -> int:
    """One prices/<TICKER>.csv per ticker, straight from the daily store.

    PRICES ARE PUBLIC. The seal is on the stake, never on the market; a
    close is the same number on every finance site, so every company's
    price file sits at the root, and a sealed page still draws the line.
    """
    import shutil
    if not store or not os.path.isdir(store):
        return 0
    dest = os.path.join(out_dir, "prices")
    os.makedirs(dest, exist_ok=True)
    n = 0
    for name in os.listdir(store):
        if name.endswith(".csv"):
            shutil.copyfile(os.path.join(store, name), os.path.join(dest, name))
            n += 1
    return n


def latest_closes(store, tickers) -> dict:
    """TICKER -> the last close in the price store; empty without a store."""
    out = {}
    if not store:
        return out
    for tk in tickers:
        p = os.path.join(store, f"{tk}.csv")
        try:
            with open(p, encoding="utf-8", newline="") as fh:
                last = None
                for row in csv.reader(fh):
                    if row and row[0] != "date":
                        last = row
                if last:
                    out[tk] = float(last[1])
        except (OSError, ValueError, IndexError):
            continue
    return out


def _num(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def ranks(panel, closes) -> dict:
    """TICKER -> (rank by stake value, rank by share), 1-based, over every
    row with a figure; rows without one get blanks."""
    def num(v):
        try:
            return float(v) if v not in (None, "") else None
        except ValueError:
            return None
    withv, withp = [], []
    for r in panel:
        pct, sh = num(r.get("pct")), num(r.get("shares"))
        if pct is None or sh is None:
            continue
        withp.append((pct, r["ticker"]))
        c = closes.get(r["ticker"])
        if c:
            withv.append((sh * c, r["ticker"]))
    out = {}
    for i, (_, t) in enumerate(sorted(withv, key=lambda x: -x[0]), 1):
        out.setdefault(t, ["", ""])[0] = i
    for i, (_, t) in enumerate(sorted(withp, key=lambda x: -x[0]), 1):
        out.setdefault(t, ["", ""])[1] = i
    return out


def main(panel_p, hist_p, events_p, founders_p, sp_p, out_dir,
         fresh_dir=None, perf_p="perf.csv", prices_dir=None) -> int:
    sp = {r["ticker"] for r in csv.DictReader(open(sp_p, encoding="utf-8-sig"))}
    # THE SEAL IS OFF (2026-09-18). The site is a reference with a live feed:
    # a company page that blurs its own number does not answer the query it
    # is titled with, does not rank, and sends the reader who arrived from a
    # post back out. Every company is open; what Pro keeps is the alerts,
    # the watches and the exports. The S&P set still names the S&P (the
    # sp column); it no longer decides what a page shows.
    # the S&P set is a data column now; it no longer decides what any file carries
    panel = list(csv.DictReader(open(panel_p, encoding="utf-8-sig")))
    # THE PARTNERSHIP REGISTER WINS (fle/partnerships.py, 2026-09-15): an
    # excluded company leaves the universe at the next panel run; until
    # then its stale row must not reach the site's lists
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from fle.partnerships import excluded as _excluded
        drop = _excluded(os.path.join(os.path.dirname(os.path.abspath(sp_p)), "partnerships.csv"))
        if drop:
            panel = [r for r in panel if (r.get("ticker") or "").upper() not in drop]
    except Exception:  # noqa: BLE001 - no register, no change
        pass

    fresh = {}
    if fresh_dir:
        panel, fresh["panel"] = _overlay(
            panel, os.path.join(fresh_dir, "panel.csv"), sp)
    for d in ("", "history", "events"):
        os.makedirs(os.path.join(out_dir, d), exist_ok=True)

    # ---- the two list files ----
    rets = one_year_returns(prices_dir, [r["ticker"] for r in panel])
    closes = latest_closes(prices_dir, [r["ticker"] for r in panel])
    if not closes:   # no store: the pipeline's prices.csv beside the panel
        try:
            for r in csv.DictReader(open(os.path.join(os.path.dirname(os.path.abspath(panel_p)), "prices.csv"), encoding="utf-8-sig")):
                closes[(r.get("ticker") or "").upper()] = float(r["close"])
        except (OSError, ValueError, KeyError):
            pass
    rk = ranks(panel, closes)


    def derived_facts():
        # THE TABLE'S TWO DERIVED FACTS, COMPUTED ONCE (2026-09-14): the newest
        # trade that moved each stake, and whether the person ever reduced one.
        # The screener used to download the whole history and events files
        # (12 MB and 69,000 rows for a Pro reader, four seconds) to derive
        # these; now the list carries them and the page loads nothing else.
        # Same rule as the page's lastTrades()/soldTickers(): codes P and S,
        # labels that moved the stake, no pre-IPO catch-ups; newest by filing.
        last_move = {}
        ever_sold = set()
        # THE TWO DATES THE CONTROLS ASK ABOUT (2026-09-21): the last sale at
        # the person's own discretion (a sale not on a Rule 10b5-1 plan) and
        # the last open-market buy, from every filing since 2016. The
        # Companies page's "years since" chips read these; "None" means none
        # on record, and the page says the record starts in 2016.
        last_disc, last_buy = {}, {}
        for r in all_rows:
            if r.get("code") not in ("P", "S") or (r.get("label") or "") in UNCHANGED_LABELS:
                continue
            if (r.get("pre_ipo") or "") in ("1", "true", "True"):
                continue
            t = r.get("ticker")
            day = r.get("traded") or r.get("filed") or ""
            if r["code"] == "S":
                ever_sold.add(t)
                if (r.get("plan") or "") != "plan" and day > last_disc.get(t, ""):
                    last_disc[t] = day
            elif day > last_buy.get(t, ""):
                last_buy[t] = day
            k = (r.get("filed") or "", r.get("traded") or "")
            if t not in last_move or k > last_move[t][0]:
                last_move[t] = (k, r)
        derived_facts.last_disc, derived_facts.last_buy = last_disc, last_buy
        return last_move, ever_sold, set(hist_by_t)

    def change_12m():
        """THE OWNERSHIP TABLE'S OWN NUMBER (2026-09-17): the stake twelve
        months ago, so the table can say +0.4 pts / -2.1 pts. The last row of
        the record on or before a year ago; blank when the record is younger
        than a year. In percentage points of the company, the same unit as
        the stake beside it."""
        import datetime as _dt
        cut = (_dt.date.today() - _dt.timedelta(days=365)).isoformat()
        # THIS PERSON'S ROWS ONLY (Palvella): the company's history keeps the
        # previous chief executive's rows under their own filer id, and the
        # stake a year ago must be the same person's, or a change of CEO
        # reads as accumulation
        owner_of = {r["ticker"]: (r.get("owner_cik") or "") for r in panel}
        shares_of = {r["ticker"]: r.get("shares") for r in panel}
        # NO FIGURE WHERE THE CHAIN FAILS (fle/grade, 2026-09-17): a record with
        # an open step this year cannot say what the stake was a year ago;
        # Palvella's 2025 rows carried one line of the holding and 2026's all
        # of it, and the column read the difference as accumulation
        chain_fails = {r["ticker"] for r in panel if (r.get("chain") or "").startswith("fail")}
        out = {}
        for t, rows in hist_by_t.items():
            if t in chain_fails:
                continue
            owner = owner_of.get(t, "")
            mine = [r for r in rows if (not owner or (r.get("owner_cik") or owner) == owner)]
            # NO FIGURE WHERE THE TWO WALKS DISAGREE (fle/grade.disagreement): a
            # history that reads the newest filing differently from the panel
            # cannot say what the stake was a year ago either
            filings = [r for r in mine if (r.get("form") or "").startswith(("3", "4", "5"))]
            try:
                ps = float(shares_of.get(t) or 0)
                _last = max(filings, key=lambda r: r.get("date", "")) if filings else None
                hs = float((_last.get("shares_split_adjusted") or _last.get("shares") or 0)) if _last else ps
            except (ValueError, TypeError):
                ps, hs = 0.0, 0.0
            if ps and abs(hs - ps) / ps > 0.01:
                continue
            prior = [r for r in mine if (r.get("date") or "") <= cut and r.get("pct") not in ("", None)]
            if not prior:
                continue
            try:
                out[t] = float(max(prior, key=lambda r: r.get("date", ""))["pct"])
            except ValueError:
                pass
        return out

    LAST_COLS = ["lt_code", "lt_plan", "lt_value", "lt_flag", "lt_traded", "lt_filed", "never_sold", "pct_12m_ago", "last_disc", "last_buy"]

    def write_list(path):
        last_move, ever_sold, has_record = derived_facts()
        ago = change_12m()
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(LIST_COLS + ["ret_1y"] + RANK_COLS + LAST_COLS)
            for r in panel:
                row = [r.get(c, "") or "" for c in LIST_COLS[:-1]]
                row.append(1 if r["ticker"] in sp else 0)   # S&P membership, a fact the pages may show
                rv = rets.get(r["ticker"])
                row.append("" if rv is None else f"{rv:.2f}")
                row.extend(rk.get(r["ticker"], ["", ""]))
                lm = last_move.get(r["ticker"])
                if lm:
                    e = lm[1]
                    row.extend([e.get("code") or "", e.get("plan") or "", e.get("value") or "",
                                e.get("price_flag") or "", e.get("traded") or "", e.get("filed") or ""])
                else:
                    row.extend(["", "", "", "", "", ""])
                row.append(1 if (r["ticker"] not in ever_sold and r["ticker"] in has_record) else 0)
                pa = ago.get(r["ticker"])
                row.append("" if pa is None else f"{pa:.4f}")
                row.append(derived_facts.last_disc.get(r["ticker"], ""))
                row.append(derived_facts.last_buy.get(r["ticker"], ""))
                w.writerow(row)
    n_px = write_price_shards(prices_dir, out_dir)
    print(f"  prices/<T>.csv       {n_px} daily series (public; the company page's price chart)")

    # ---- founders: fresh S&P labels over the snapshot ----
    f_rows = list(csv.DictReader(open(founders_p, encoding="utf-8-sig")))
    f_cols = list(f_rows[0].keys()) if f_rows else ["ticker", "founder"]
    if fresh_dir:
        f_rows, fresh["founders"] = _overlay(
            f_rows, os.path.join(fresh_dir, "founders.csv"), sp)
    # FOUNDER LABELS ARE PUBLIC, EVERYWHERE. A sealed company's page shows
    # the badge, and perf.csv at the root lists the cohort's tickers, so
    # the label was never behind the seal; only the stake is. Both files
    # carry every label, and the chart's "all founder-led" cohort draws
    # the same for a free reader as for a subscriber.
    with open(os.path.join(out_dir, "founders.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=f_cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(f_rows)

    # ---- history shards ----
    hist_rows = list(csv.DictReader(open(hist_p, encoding="utf-8-sig")))
    if fresh_dir:
        hist_rows, fresh["history"] = _overlay(
            hist_rows, os.path.join(fresh_dir, "history.csv"), sp)
    hist_by_t = defaultdict(list)
    hist_cols = None
    for r in hist_rows:
        hist_cols = hist_cols or list(r.keys())
        hist_by_t[r["ticker"]].append(r)
    for t, rows in sorted(hist_by_t.items()):
        rows.sort(key=lambda r: r.get("date", ""))
        with open(os.path.join(out_dir, "history", f"{t}.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=hist_cols)
            w.writeheader()
            w.writerows(rows)

    # ---- the lite history files: the page's synchronous brain ----
    # Monthly resolution plus each series' first point, record low, and
    # restated rows -- the lens math and sparklines need the shape, not
    # every filing; the focus view fetches the full shard on demand.
    def lite(rows):
        keep, seen = [], set()
        best_min, best_v = None, None
        for r in rows:
            v = None
            try:
                v = float(r.get("pct") or "")
            except ValueError:
                pass
            if v is not None and (best_v is None or v < best_v):
                best_min, best_v = r, v
        by_month = {}
        for r in rows:
            by_month[r.get("date", "")[:7]] = r     # last of each month wins
        chosen = [rows[0], rows[-1]] + list(by_month.values())
        chosen += [r for r in rows if (r.get("restated") or "").strip()]
        if best_min is not None:
            chosen.append(best_min)
        for r in sorted(chosen, key=lambda r: r.get("date", "")):
            k = (r.get("date"), r.get("accession"))
            if k not in seen:
                seen.add(k)
                keep.append(r)
        return keep

    lite_all = []
    for t, rows in sorted(hist_by_t.items()):
        rows.sort(key=lambda r: r.get("date", ""))
        lite_all.extend(lite(rows))
    with open(os.path.join(out_dir, "history-lite.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=hist_cols)
        w.writeheader()
        w.writerows(lite_all)

    # ---- event shards ----
    ev_rows_shard = list(csv.DictReader(open(events_p, encoding="utf-8-sig")))
    if fresh_dir:
        ev_rows_shard, fresh["events"] = _overlay(
            ev_rows_shard, os.path.join(fresh_dir, "events.csv"), sp)
    ev_by_t = defaultdict(list)
    ev_cols = None
    for r in ev_rows_shard:
        ev_cols = ev_cols or list(r.keys())
        ev_by_t[r["ticker"]].append(r)
    newest = max((r.get("filed") or "" for r in ev_rows_shard), default="")
    year_ago = ""
    if newest:
        import datetime as _dt
        year_ago = (_dt.date.fromisoformat(newest) - _dt.timedelta(days=366)).isoformat()

    def within_year(r):
        return (r.get("filed") or "") >= year_ago
    # EVERY SHARD IS THE WHOLE RECORD SINCE 2016 (2026-09-23; the tiers are
    # gone): a company page's table is every filing, no archive.
    for t, rows in sorted(ev_by_t.items()):
        with open(os.path.join(out_dir, "events", f"{t}.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=ev_cols)
            w.writeheader()
            w.writerows(rows)

    # ---- the aggregate feed the home page and /tape/ load ----
    # THE FEED IS A YEAR, for its size (the shards carry the full record),
    # plus each company's most recent stake-moving trade whatever its date.
    all_rows = ev_rows_shard
    write_list(os.path.join(out_dir, "universe.csv"))
    last_by_t = {}
    for r in all_rows:
        if r.get("code") in ("P", "S") and (r.get("label") or "") not in UNCHANGED_LABELS:
            k = (r.get("traded") or r.get("filed") or "", r.get("filed") or "")
            if r["ticker"] not in last_by_t or k > last_by_t[r["ticker"]][0]:
                last_by_t[r["ticker"]] = (k, r)
    keep_last = {id(v[1]) for v in last_by_t.values()}
    feed_rows = [r for r in all_rows if within_year(r) or id(r) in keep_last]
    feed_rows.sort(key=lambda r: (r.get("filed") or "", r.get("ticker") or ""))
    with open(os.path.join(out_dir, "events.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ev_cols)
        w.writeheader()
        w.writerows(feed_rows)

    # ---- HOW THE STAKE IS HELD (2026-09-25) ----
    # The walk writes u-holdings.csv beside u-history.csv; here it passes
    # through, filtered to the panel's tickers. No file, or an unreadable
    # one, means no sections anywhere and nothing else changes.
    _hd, _hb = os.path.split(hist_p)
    hold_p = os.path.join(_hd, _hb.replace("history", "holdings")) if "history" in _hb else ""
    held_rows = []
    if hold_p and os.path.exists(hold_p):
        try:
            tks = {r["ticker"] for r in panel}
            held_rows = [r for r in csv.DictReader(open(hold_p, encoding="utf-8-sig"))
                         if r.get("ticker") in tks]
        except Exception:
            held_rows = []
    if held_rows:
        hcols = ["ticker", "ceo", "vehicle", "klass", "di", "shares",
                 "pct_of_stake", "as_of", "accession", "stale"]
        with open(os.path.join(out_dir, "holdings.csv"), "w", newline="",
                  encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=hcols, extrasaction="ignore")
            w.writeheader()
            w.writerows(held_rows)

    # ---- THE SCREENER'S COUNTS (PLAN.md section 3, reason three) ----
    # A free reader's filter cannot be applied to a sealed row (its share is
    # not in the file), so the free screener shows the S&P's matches and a
    # line saying how many more match in Pro. That number is computed here,
    # over every company, for every combination of the screener's filters
    # (a share threshold, founders only, never sold), and read by the page.
    # THE PRESETS, COUNTED (2026-09-21): the five screen pages are presets of
    # the Companies page's controls (who runs it, the index, owns at least,
    # years since the last discretionary sale, years since the last
    # open-market buy). One rule here, the same rule in the page's
    # `passes()`, so a screen page and its chips never disagree.
    founder_yes = {r["ticker"].upper() for r in f_rows if (r.get("founder") or "").lower() == "yes"}
    has_hist = set(hist_by_t)
    if not hasattr(derived_facts, "last_disc"):
        derived_facts()
    last_disc, last_buy = derived_facts.last_disc, derived_facts.last_buy
    import datetime as _dt
    today = _dt.date.today()
    def years_since(day):
        if not day:
            return None
        try:
            d = _dt.date.fromisoformat(day[:10])
        except ValueError:
            return None
        return (today - d).days / 365.25
    def bucket(y, edges):
        # None -> "none"; else the first edge it is under, then "<last>plus"
        if y is None:
            return "none"
        for lo, hi, name in edges:
            if (lo is None or y >= lo) and (hi is None or y < hi):
                return name
        return "none"
    SOLD = [(None, 1, "lt1"), (1, 5, "1to5"), (5, None, "5plus")]
    BUY = [(None, 1, "lt1"), (1, 5, "1to5"), (5, None, "5plus")]   # the same windows as the sale group (2026-09-21)
    PRESETS = {
        "founder-led": {"who": "founders"},
        "never-sold": {"sold": "none"},
        "over-10": {"min": 10},
        "bought-this-year": {"buy": "lt1"},
        "hired-under-1": {"who": "hired", "max": 1},
    }
    def passes(r, f):
        t = r["ticker"]
        pct = _num(r.get("pct"))
        if pct is None or (r.get("operating_partnership") or "").lower() == "true":
            return False
        who = f.get("who", "all")
        if who == "founders" and t not in founder_yes:
            return False
        if who == "hired" and t in founder_yes:
            return False
        if f.get("sp") and t not in sp:
            return False
        if pct < f.get("min", 0):
            return False
        if f.get("max") is not None and pct >= f["max"]:
            return False
        want = f.get("sold", "any")
        if want != "any":
            b = bucket(years_since(last_disc.get(t)), SOLD)
            if b == "none" and t not in has_hist:
                return False        # no record at all is not "none since 2016"
            if b != want:
                return False
        want = f.get("buy", "any")
        if want != "any":
            if bucket(years_since(last_buy.get(t)), BUY) != want:
                return False
        return True
    counts = {}
    for name, f in PRESETS.items():
        counts["s:" + name] = sum(1 for r in panel if passes(r, f))
    counts["s:"] = sum(1 for r in panel if passes(r, {}))
    with open(os.path.join(out_dir, "screen-counts.json"), "w", encoding="utf-8") as fh:
        json.dump(counts, fh)

    # ---- manifest ----
    def _n(sub):
        p = os.path.join(out_dir, sub)
        return len(os.listdir(p)) if os.path.isdir(p) else 0
    def _kb(name):
        return os.path.getsize(os.path.join(out_dir, name)) // 1024
    print(f"  universe.csv        {len(panel)} rows, {_kb('universe.csv')} KB")
    print(f"  events shards       {_n('events')}")
    print(f"  history shards      {_n('history')}")
    print(f"  history-lite.csv    {len(lite_all)} rows, {_kb('history-lite.csv')} KB")
    print(f"  events.csv (feed)   {len(feed_rows)} rows, {_kb('events.csv')} KB")
    if fresh_dir:
        got = ", ".join(k for k, v in fresh.items() if v) or "none"
        print(f"  fresh S&P overlay   {got}  (from {fresh_dir})")
    return 0


if __name__ == "__main__":
    argv = list(sys.argv[1:])
    prices_dir = None
    if "--prices" in argv:
        i = argv.index("--prices")
        prices_dir = argv[i + 1]
        del argv[i:i + 2]
    raise SystemExit(main(*argv[:7], prices_dir=prices_dir))
