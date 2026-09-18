#!/usr/bin/env python3
"""Build the site's data files from the pipeline's staging output.

    python3 ops/build_site_data.py _staging/u-panel.csv _staging/u-history.csv \
        _staging/u-events.csv _staging/u-founders.csv \
        universe/sp500-<date>.csv site-data/

Layout produced (paths relative to the output dir):
    universe.csv            every company, list-page columns; non-S&P rows
                            carry pct only if
GENEROUS, else masked=1, and
                            every row carries its rank by value and by
                            share, so a free page can place a sealed row
                            where it belongs without its number
                            arrows without loading any history
    founders.csv            passthrough (small)
    history/<T>.csv         per-ticker walk shards, S&P tickers
    events/<T>.csv          per-ticker event shards, S&P tickers
    prices/<T>.csv          daily closes for EVERY ticker (public; with
                            --prices <store>)
    pro/universe.csv        every company, nothing masked
    pro/history/<T>.csv     non-S&P shards (serve behind auth)
    pro/events/<T>.csv      non-S&P shards (serve behind auth)

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

GENEROUS = False   # True: public universe.csv carries every pct unmasked
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
             "cover_url", "outstanding_as_of", "shares_tabled", "masked", "sp"]
# THE PLACE WITHOUT THE NUMBER. A free reader sees every company in its
# true rank with its name; the value and the share are the product and
# stay out of the free file. The ranks are computed here over the whole
# panel, before masking, and written to both files.
RANK_COLS = ["rank_value", "rank_pct"]
# THE TOP OF THE BOARD IS EVERYONE'S. The leaderboard is the site's poster,
# and the stakes at its top are the least secret numbers on the site. The
# top 25 by value and by share are open in the free file; the rest of a
# sealed row's numbers stay behind the seal.
OPEN_TOP = 0    # THE SEAL IS THE S&P AND NOTHING ELSE (PLAN.md section 2). The top-25 exception of the free-tier week put the Pro catalog's front page on the home page once the list sorted by share (2026-09-14).
# what a sealed row must not carry: anything that states or bounds the stake
MASKED_COLS = ("pct", "shares", "form4_url", "cover_url",
               "excluded_shares", "excluded_detail", "shares_tabled")


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
    for d in ("", "history", "events", "pro", "pro/history", "pro/events"):
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
        for r in all_rows:
            if r.get("code") not in ("P", "S") or (r.get("label") or "") in UNCHANGED_LABELS:
                continue
            if (r.get("pre_ipo") or "") in ("1", "true", "True"):
                continue
            t = r.get("ticker")
            if r["code"] == "S":
                ever_sold.add(t)
            k = (r.get("filed") or "", r.get("traded") or "")
            if t not in last_move or k > last_move[t][0]:
                last_move[t] = (k, r)
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

    LAST_COLS = ["lt_code", "lt_plan", "lt_value", "lt_flag", "lt_traded", "lt_filed", "never_sold", "pct_12m_ago"]

    def write_list(path, mask_new):
        last_move, ever_sold, has_record = derived_facts()
        ago = change_12m()
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(LIST_COLS + ["ret_1y"] + RANK_COLS + LAST_COLS)
            for r in panel:
                rv, rp = rk.get(r["ticker"], ["", ""])
                on_top = (rv != "" and rv <= OPEN_TOP) or (rp != "" and rp <= OPEN_TOP)
                masked = 1 if (mask_new and r["ticker"] not in sp
                               and not GENEROUS and not on_top) else 0
                row = []
                for c in LIST_COLS[:-2]:
                    v = r.get(c, "") or ""
                    if masked and c in MASKED_COLS:
                        v = ""
                    row.append(v)
                row.append(masked)
                # S&P membership is public; the chart's cohort toggle and
                # the free/Pro seam both read it instead of inferring it
                # from what happens to be masked
                row.append(1 if r["ticker"] in sp else 0)
                rv = rets.get(r["ticker"])
                row.append("" if rv is None else f"{rv:.2f}")
                row.extend(rk.get(r["ticker"], ["", ""]))
                lm = last_move.get(r["ticker"])
                if lm:
                    e = lm[1]
                    # the amount is sealed with the rest outside the S&P
                    row.extend([e.get("code") or "", e.get("plan") or "", "" if masked else (e.get("value") or ""),
                                e.get("price_flag") or "", e.get("traded") or "", e.get("filed") or ""])
                else:
                    row.extend(["", "", "", "", "", ""])
                row.append(1 if (r["ticker"] not in ever_sold and r["ticker"] in has_record) else 0)
                # sealed with the stake outside the S&P: the change gives the stake away
                pa = ago.get(r["ticker"])
                row.append("" if (pa is None or masked) else f"{pa:.4f}")
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
    for path, rows in (("founders.csv", f_rows),
                       (os.path.join("pro", "founders.csv"), f_rows)):
        with open(os.path.join(out_dir, path), "w", newline="",
                  encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=f_cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

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
        # EVERY COMPANY'S RECORD UNDER /pro/history/, the open ones under
        # /history/ as well (2026-09-14): a Pro reader's page asks the Pro
        # path for every company, and an S&P company's record must be there.
        subs = ["pro/history"] + (["history"] if t in sp else [])
        for sub in subs:
            with open(os.path.join(out_dir, sub, f"{t}.csv"), "w",
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

    lite_all, lite_sp = [], []
    for t, rows in sorted(hist_by_t.items()):
        rows.sort(key=lambda r: r.get("date", ""))
        lt = lite(rows)
        lite_all.extend(lt)
        if t in sp:
            lite_sp.extend(lt)
    for path, rows in (("history-free-lite.csv", lite_sp),
                       (os.path.join("pro", "history-lite.csv"), lite_all)):
        with open(os.path.join(out_dir, path), "w", newline="",
                  encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=hist_cols)
            w.writeheader()
            w.writerows(rows)

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
    # A SEALED FILING IS A ROW WITHOUT ITS NUMBERS (see the feed below): the
    # same masking gives every sealed company a free shard of its last year,
    # so its page shows the same table as an open one, dates and kinds
    # visible, every figure a blur.
    newest = max((r.get("filed") or "" for r in ev_rows_shard), default="")
    year_ago = ""
    if newest:
        import datetime as _dt
        year_ago = (_dt.date.fromisoformat(newest) - _dt.timedelta(days=366)).isoformat()
    # THE AMOUNT SHOWS ON EVERY ROW (PLAN.md section 2): it is the Form 4's
    # own number. The stake after the trade, and everything derived from
    # the walk, is the seal. The filing link stays sealed with the record.
    EV_MASK = ("avg_price", "avg_price_adjusted", "shares", "pct_of_holding", "pct_approx",
               "net_change", "day_net", "holding_after", "pct_after", "residue", "url",
               "rows", "unpriced_rows", "securities", "also_shares")   # the other disposition's size is the seal's too
    def masked_row(r):
        m = dict(r)
        for c in EV_MASK:
            if c in m:
                m[c] = ""
        m["masked"] = "1"
        return m
    # THE FREE RECORD IS A YEAR (PLAN.md section 2). An open company's free
    # shard carries its last twelve months with every figure; the archive
    # before that is the Pro shard. A sealed company's free shard carries
    # the same year with the figures blank. The Pro shard, for every
    # company, carries everything since 2016.
    def within_year(r):
        return (r.get("filed") or "") >= year_ago
    for t, rows in sorted(ev_by_t.items()):
        with open(os.path.join(out_dir, "pro", "events", f"{t}.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=ev_cols + ["masked"])
            w.writeheader()
            w.writerows(dict(r, masked="0") for r in rows)
        with open(os.path.join(out_dir, "events", f"{t}.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=ev_cols + ["masked"])
            w.writeheader()
            if t in sp:
                w.writerows(dict(r, masked="0") for r in rows if within_year(r))
            else:
                w.writerows(masked_row(r) for r in rows if within_year(r))

    # ---- the aggregate event files the feed loads ----
    # THE FREE FEED IS THE YEAR (PLAN.md section 2, decided 2026-09-13):
    # the S&P's last twelve months with every figure, the archive in Pro.
    # Pro adds companies and years, never a different lens.
    # A SEALED FILING IS A ROW WITHOUT ITS NUMBERS. The free feed also
    # carries the last year of filings by sealed companies with the ticker,
    # the name, the dates and the kind, and every figure blank (value,
    # shares, prices, the stake and its change, the link). The feed's
    # windows never look past a year, so the file grows by one year of
    # rows, not ten. A masked column says which rows these are.
    cols = ev_cols + ["masked"]
    all_rows = ev_rows_shard
    # the two list files, now that the trades and the record are in hand
    write_list(os.path.join(out_dir, "universe.csv"), mask_new=True)
    write_list(os.path.join(out_dir, "pro", "universe.csv"), mask_new=False)
    # THE FREE FEED IS A YEAR TOO, plus each S&P company's most recent
    # stake-moving trade whatever its date, so the screener's "last trade"
    # column is true for a free reader whose company last traded in 2019.
    last_by_t = {}
    for r in all_rows:
        if r.get("ticker") in sp and r.get("code") in ("P", "S") and (r.get("label") or "") not in UNCHANGED_LABELS:
            k = (r.get("traded") or r.get("filed") or "", r.get("filed") or "")
            if r["ticker"] not in last_by_t or k > last_by_t[r["ticker"]][0]:
                last_by_t[r["ticker"]] = (k, r)
    keep_last = {id(v[1]) for v in last_by_t.values()}
    free_rows = ([dict(r, masked="0") for r in all_rows if r.get("ticker") in sp and (within_year(r) or id(r) in keep_last)]
                 + [masked_row(r) for r in all_rows
                    if r.get("ticker") not in sp and within_year(r)])
    free_rows.sort(key=lambda r: (r.get("filed") or "", r.get("ticker") or ""))
    for path, rows in (("events-free.csv", free_rows),
                       (os.path.join("pro", "events.csv"), [dict(r, masked="0") for r in all_rows])):
        with open(os.path.join(out_dir, path), "w", newline="",
                  encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)

    # ---- THE SCREENER'S COUNTS (PLAN.md section 3, reason three) ----
    # A free reader's filter cannot be applied to a sealed row (its share is
    # not in the file), so the free screener shows the S&P's matches and a
    # line saying how many more match in Pro. That number is computed here,
    # over every company, for every combination of the screener's filters
    # (a share threshold, founders only, never sold), and read by the page.
    founder_yes = {r["ticker"].upper() for r in f_rows if (r.get("founder") or "").lower() == "yes"}
    sold = {r.get("ticker") for r in all_rows
            if r.get("code") == "S" and (r.get("label") or "") not in UNCHANGED_LABELS}
    has_hist = set(hist_by_t)
    counts = {}
    for m in (0, 1, 5, 10):
        for f in (0, 1):
            for h in (0, 1):
                n = 0
                for r in panel:
                    t = r["ticker"]
                    pct = _num(r.get("pct"))
                    if pct is None or (r.get("operating_partnership") or "").lower() == "true":
                        continue
                    if m and pct < m:
                        continue
                    if f and t not in founder_yes:
                        continue
                    if h and (t in sold or t not in has_hist):
                        continue
                    n += 1
                counts[f"m{m}f{f}h{h}"] = n
    # THE NAMED SCREENS (PLAN.md section 7, step 6): four questions with a
    # name and a URL each, counted the same way so a free reader's screen
    # says how many more match in Pro.
    last_move = {}
    for r in all_rows:
        if r.get("code") not in ("P", "S") or (r.get("label") or "") in UNCHANGED_LABELS:
            continue
        if (r.get("pre_ipo") or "") in ("1", "true", "True"):
            continue
        k = (r.get("traded") or r.get("filed") or "", r.get("filed") or "")
        t = r.get("ticker")
        if t not in last_move or k > last_move[t][0]:
            last_move[t] = (k, r)
    import datetime as _dt
    year_ago = (_dt.date.today() - _dt.timedelta(days=365)).isoformat()
    def bought_this_year(t):
        lm = last_move.get(t)
        return bool(lm) and lm[1].get("code") == "P" and (lm[1].get("traded") or lm[1].get("filed") or "") >= year_ago
    screens = {
        "never-sold": lambda t, pct: t not in sold and t in has_hist,
        "over-10": lambda t, pct: pct >= 10,
        "bought-this-year": lambda t, pct: bought_this_year(t),
        "hired-under-1": lambda t, pct: t not in founder_yes and pct < 1,
    }
    for name, test in screens.items():
        n = 0
        for r in panel:
            pct = _num(r.get("pct"))
            if pct is None or (r.get("operating_partnership") or "").lower() == "true":
                continue
            if test(r["ticker"], pct):
                n += 1
        counts["s:" + name] = n
    with open(os.path.join(out_dir, "screen-counts.json"), "w", encoding="utf-8") as fh:
        json.dump(counts, fh)

    # ---- manifest ----
    def _n(sub):
        p = os.path.join(out_dir, sub)
        return len(os.listdir(p)) if os.path.isdir(p) else 0
    def _kb(name):
        return os.path.getsize(os.path.join(out_dir, name)) // 1024
    print(f"  universe.csv        {len(panel)} rows, {_kb('universe.csv')} KB "
          f"({sum(1 for r in panel if r['ticker'] not in sp)} maskable)")
    print(f"  events shards       {_n('events')} free + {_n('pro/events')} pro")
    print(f"  history shards      {_n('history')} open (also under pro) + {_n('pro/history')} pro")
    biggest = max(((os.path.getsize(os.path.join(out_dir, s, f)), s + "/" + f)
                   for s in ("history", "pro/history")
                   for f in os.listdir(os.path.join(out_dir, s))),
                  default=(0, "-"))
    print(f"  largest shard       {biggest[1]}  {biggest[0] // 1024} KB")
    print(f"  history-free-lite   {len(lite_sp)} rows, {_kb('history-free-lite.csv')} KB")
    print(f"  pro/history-lite    {len(lite_all)} rows, "
          f"{os.path.getsize(os.path.join(out_dir, 'pro', 'history-lite.csv')) // 1024} KB")
    print(f"  events-free.csv     "
          f"{sum(1 for r in free_rows if r['masked'] == '0')} S&P rows + "
          f"{sum(1 for r in free_rows if r['masked'] == '1')} sealed rows (a year, numbers blank), "
          f"{_kb('events-free.csv')} KB")
    print(f"  pro/events.csv      {len(all_rows)} rows")
    print(f"  GENEROUS={GENEROUS}  (public pct on non-S&P rows)")
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
