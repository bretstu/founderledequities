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


def main(panel_p, hist_p, events_p, founders_p, sp_p, out_dir) -> int:
    sp = {r["ticker"] for r in csv.DictReader(open(sp_p, encoding="utf-8-sig"))}
    panel = list(csv.DictReader(open(panel_p, encoding="utf-8-sig")))
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

    # ---- founders passthrough ----
    with open(founders_p, encoding="utf-8-sig") as src, \
         open(os.path.join(out_dir, "founders.csv"), "w",
              encoding="utf-8") as dst:
        dst.write(src.read())

    # ---- history shards + trends ----
    hist_by_t = defaultdict(list)
    hist_cols = None
    for r in csv.DictReader(open(hist_p, encoding="utf-8-sig")):
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
    with open(os.path.join(out_dir, "trends.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["ticker", "pct_now", "pct_1y", "direction"])
        w.writerows(trend_rows)

    # ---- event shards ----
    ev_by_t = defaultdict(list)
    ev_cols = None
    for r in csv.DictReader(open(events_p, encoding="utf-8-sig")):
        ev_cols = ev_cols or list(r.keys())
        ev_by_t[r["ticker"]].append(r)
    for t, rows in sorted(ev_by_t.items()):
        sub = "events" if t in sp else "pro/events"
        with open(os.path.join(out_dir, sub, f"{t}.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=ev_cols)
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
    print(f"  GENEROUS={GENEROUS}  (public pct on non-S&P rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:7]))
