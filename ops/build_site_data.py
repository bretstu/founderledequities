#!/usr/bin/env python3
"""Build the site's data files from the pipeline's staging output.

    python3 ops/build_site_data.py _staging/u-panel.csv _staging/u-history.csv \
        _staging/u-events.csv _staging/u-founders.csv \
        universe/sp500-<date>.csv site-data/

Layout produced (paths relative to the output dir):
    universe.csv            every company, list-page columns; non-S&P rows
                            carry pct only if GENEROUS, else masked=1, and
                            every row carries its rank by value and by
                            share, so a free page can place a sealed row
                            where it belongs without its number
    trends.csv              ticker, pct_now, pct_1y, direction -- the list's
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
pipeline files, nothing is computed here except the trend comparison.
"""
import csv
import os
import sys
from collections import defaultdict

GENEROUS = False   # True: public universe.csv carries every pct unmasked

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


def write_perf_for_chart(perf_p: str, founders_p: str, out_dir: str) -> int:
    """The published perf.csv is the chart's cohort only (founders plus the
    two benchmarks); every company's closes stay on disk for the returns."""
    yes = set()
    try:
        for r in csv.DictReader(open(founders_p, encoding="utf-8-sig")):
            if (r.get("founder") or "").lower() == "yes" and r.get("ticker"):
                yes.add(r["ticker"].upper())
    except OSError:
        pass
    keep = yes | {"SPY", "RSP"}
    n = 0
    try:
        with open(perf_p, encoding="utf-8-sig", newline="") as fh, \
             open(os.path.join(out_dir, "perf.csv"), "w", newline="", encoding="utf-8") as out:
            rd = csv.DictReader(fh); w = csv.DictWriter(out, fieldnames=rd.fieldnames)
            w.writeheader()
            for r in rd:
                if (r.get("ticker") or "").upper() in keep:
                    w.writerow(r); n += 1
    except OSError:
        return 0
    return n


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

    def write_list(path, mask_new):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(LIST_COLS + ["ret_1y"] + RANK_COLS)
            for r in panel:
                masked = 1 if (mask_new and r["ticker"] not in sp
                               and not GENEROUS) else 0
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
                w.writerow(row)
    write_list(os.path.join(out_dir, "universe.csv"), mask_new=True)
    n_perf = write_perf_for_chart(perf_p, founders_p, out_dir)
    print(f"  perf.csv (chart cohort)  {n_perf} monthly closes -- founders and the two benchmarks only")
    n_px = write_price_shards(prices_dir, out_dir)
    print(f"  prices/<T>.csv       {n_px} daily series (public; the company page's price chart)")
    write_list(os.path.join(out_dir, "pro", "universe.csv"), mask_new=False)

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

    # ---- history shards + trends ----
    hist_rows = list(csv.DictReader(open(hist_p, encoding="utf-8-sig")))
    if fresh_dir:
        hist_rows, fresh["history"] = _overlay(
            hist_rows, os.path.join(fresh_dir, "history.csv"), sp)
    hist_by_t = defaultdict(list)
    hist_cols = None
    for r in hist_rows:
        hist_cols = hist_cols or list(r.keys())
        hist_by_t[r["ticker"]].append(r)
    trend_rows = []
    for t, rows in sorted(hist_by_t.items()):
        rows.sort(key=lambda r: r.get("date", ""))
        sub = "history" if t in sp else "pro/history"
        with open(os.path.join(out_dir, sub, f"{t}.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=hist_cols)
            w.writeheader()
            w.writerows(rows)
        # the trend: newest pct vs the newest pct at least ~1 year older
        def _f(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
        now_r = rows[-1]
        now = _f(now_r.get("pct"))
        year_ago = None
        cutoff = ""
        d = now_r.get("date", "")
        if len(d) == 10:
            cutoff = f"{int(d[:4]) - 1}{d[4:]}"
        for r in reversed(rows):
            if cutoff and r.get("date", "") <= cutoff:
                year_ago = _f(r.get("pct"))
                break
        if now is not None and year_ago is not None:
            direction = ("up" if now > year_ago * 1.02 else
                         "down" if now < year_ago * 0.98 else "flat")
        else:
            direction = ""
        trend_rows.append([t, "" if now is None else f"{now:.4f}",
                           "" if year_ago is None else f"{year_ago:.4f}",
                           direction])
    # THE MASK EXTENDS TO EVERY FILE. trends.csv once carried pct_now for
    # all 2,135 tickers publicly -- the "hidden" stakes readable out of a
    # 46KB file. Public rows outside the free tier keep the direction
    # (real, useful, unpriced); the numbers live behind /pro/.
    with open(os.path.join(out_dir, "trends.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "pct_now", "pct_1y", "direction"])
        for t, now, ago, d in trend_rows:
            if t in sp or GENEROUS:
                w.writerow([t, now, ago, d])
    with open(os.path.join(out_dir, "pro", "trends.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "pct_now", "pct_1y", "direction"])
        w.writerows(trend_rows)

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
    for t, rows in sorted(ev_by_t.items()):
        sub = "events" if t in sp else "pro/events"
        with open(os.path.join(out_dir, sub, f"{t}.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=ev_cols)
            w.writeheader()
            w.writerows(rows)

    # ---- the aggregate event files the feed loads ----
    # THE SEAL IS THE ONLY GATE: the free file is the S&P's ENTIRE event
    # archive -- every sale, every year -- not a windowed teaser. Pro adds
    # companies, never features.
    # A SEALED FILING IS A ROW WITHOUT ITS NUMBERS. The free feed also
    # carries the last year of filings by sealed companies with the ticker,
    # the name, the dates and the kind, and every figure blank (value,
    # shares, prices, the stake and its change, the link). The feed's
    # windows never look past a year, so the file grows by one year of
    # rows, not ten. A masked column says which rows these are.
    cols = ev_cols + ["masked"]
    all_rows = ev_rows_shard
    newest = max((r.get("filed") or "" for r in all_rows), default="")
    year_ago = ""
    if newest:
        import datetime as _dt
        year_ago = (_dt.date.fromisoformat(newest) - _dt.timedelta(days=366)).isoformat()
    EV_MASK = ("value", "avg_price", "avg_price_adjusted", "shares", "pct_of_holding", "pct_approx",
               "net_change", "day_net", "holding_after", "outstanding", "pct_after", "residue", "url",
               "rows", "unpriced_rows", "securities", "price_flag")
    def masked_row(r):
        m = dict(r)
        for c in EV_MASK:
            if c in m:
                m[c] = ""
        m["masked"] = "1"
        return m
    free_rows = ([dict(r, masked="0") for r in all_rows if r.get("ticker") in sp]
                 + [masked_row(r) for r in all_rows
                    if r.get("ticker") not in sp and (r.get("filed") or "") >= year_ago])
    free_rows.sort(key=lambda r: (r.get("filed") or "", r.get("ticker") or ""))
    for path, rows in (("events-free.csv", free_rows),
                       (os.path.join("pro", "events.csv"), [dict(r, masked="0") for r in all_rows])):
        with open(os.path.join(out_dir, path), "w", newline="",
                  encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)

    # ---- manifest ----
    def _n(sub):
        p = os.path.join(out_dir, sub)
        return len(os.listdir(p)) if os.path.isdir(p) else 0
    def _kb(name):
        return os.path.getsize(os.path.join(out_dir, name)) // 1024
    print(f"  universe.csv        {len(panel)} rows, {_kb('universe.csv')} KB "
          f"({sum(1 for r in panel if r['ticker'] not in sp)} maskable)")
    print(f"  trends.csv          {len(trend_rows)} rows, {_kb('trends.csv')} KB")
    print(f"  history shards      {_n('history')} free + {_n('pro/history')} pro")
    print(f"  events shards       {_n('events')} free + {_n('pro/events')} pro")
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
