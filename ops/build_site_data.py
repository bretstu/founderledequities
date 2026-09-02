#!/usr/bin/env python3
"""Build the site's data files from the pipeline's staging output.

    python3 ops/build_site_data.py _staging/u-panel.csv _staging/u-history.csv \
        _staging/u-events.csv _staging/u-founders.csv \
        ../founderledequities/sp500.csv site-data/

Layout produced (paths relative to the output dir):
    universe.csv            every company, list-page columns; non-S&P rows
                            carry pct only if GENEROUS, else masked=1
    trends.csv              ticker, pct_now, pct_1y, direction -- the list's
                            arrows without loading any history
    founders.csv            passthrough (small)
    history/<T>.csv         per-ticker walk shards, S&P tickers
    events/<T>.csv          per-ticker event shards, S&P tickers
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

LIST_COLS = ["ticker", "cik", "company", "ceo", "pct", "shares",
             "outstanding", "confidence", "stake_source", "problems",
             "flags", "error", "form4_url", "cover_url", "masked"]


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


def main(panel_p, hist_p, events_p, founders_p, sp_p, out_dir,
         fresh_dir=None) -> int:
    sp = {r["ticker"] for r in csv.DictReader(open(sp_p, encoding="utf-8-sig"))}
    panel = list(csv.DictReader(open(panel_p, encoding="utf-8-sig")))
    fresh = {}
    if fresh_dir:
        panel, fresh["panel"] = _overlay(
            panel, os.path.join(fresh_dir, "sp500.csv"), sp)
    for d in ("", "history", "events", "pro", "pro/history", "pro/events"):
        os.makedirs(os.path.join(out_dir, d), exist_ok=True)

    # ---- the two list files ----
    def write_list(path, mask_new):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(LIST_COLS)
            for r in panel:
                masked = 1 if (mask_new and r["ticker"] not in sp
                               and not GENEROUS) else 0
                row = []
                for c in LIST_COLS[:-1]:
                    v = r.get(c, "") or ""
                    if masked and c in ("pct", "shares", "form4_url", "cover_url"):
                        v = ""
                    row.append(v)
                row.append(masked)
                w.writerow(row)
    write_list(os.path.join(out_dir, "universe.csv"), mask_new=True)
    write_list(os.path.join(out_dir, "pro", "universe.csv"), mask_new=False)

    # ---- founders: fresh S&P labels over the snapshot ----
    f_rows = list(csv.DictReader(open(founders_p, encoding="utf-8-sig")))
    f_cols = list(f_rows[0].keys()) if f_rows else ["ticker", "founder"]
    if fresh_dir:
        f_rows, fresh["founders"] = _overlay(
            f_rows, os.path.join(fresh_dir, "founders.csv"), sp)
    # free labels for the free companies; the sealed remainder's founder
    # status is itself part of what the seal covers
    for path, rows in (("founders.csv",
                        [r for r in f_rows if r.get("ticker") in sp or GENEROUS]),
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
    cols = ev_cols
    all_rows = ev_rows_shard
    for path, rows in (("events-free.csv",
                        [r for r in all_rows if r.get("ticker") in sp]),
                       (os.path.join("pro", "events.csv"), all_rows)):
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
          f"{sum(1 for r in all_rows if r.get('ticker') in sp)} rows, "
          f"{_kb('events-free.csv')} KB (full S&P archive)")
    print(f"  pro/events.csv      {len(all_rows)} rows")
    print(f"  GENEROUS={GENEROUS}  (public pct on non-S&P rows)")
    if fresh_dir:
        got = ", ".join(k for k, v in fresh.items() if v) or "none"
        print(f"  fresh S&P overlay   {got}  (from {fresh_dir})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:8]))
