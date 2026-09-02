#!/usr/bin/env bash
# Assemble the public site and push it to Cloudflare Pages.
#
# LAYOUT IS THE PAYWALL. public/ carries the pages and the free data at the
# root, and the full data under public/pro/ -- where functions/pro/[[path]].js
# stands in front of EVERY request with the subscription check (a catch-all,
# so the sharded tree under pro/ is gated by construction).
#
# THE UNIVERSE SHAPE. universe-data/ holds the full-universe snapshot (the
# staging CSVs, static until the universe gets its own refresh cadence).
# The nightly keeps rebuilding the S&P files exactly as it always has, and
# build_site_data.py overlays those FRESH S&P rows onto the snapshot before
# every deploy: the 500 stay current daily, the remainder is honestly frozen.
set -euo pipefail
cd "$(dirname "$0")/.."

# ---- 1. the site's data, generated fresh ----
python3 ops/build_site_data.py \
  universe-data/u-panel.csv universe-data/u-history.csv \
  universe-data/u-events.csv universe-data/u-founders.csv \
  sp500.csv site-data/ .

# ---- 1b. price the whole universe ----
# Polygon's grouped-daily endpoint returns the entire market in ONE call;
# the ticker list only filters the output. Pricing 2,135 costs the same
# request as pricing 500. A failure keeps yesterday's file -- the deploy
# never publishes an empty prices.csv over a good one.
python3 -m fle.cli prices --panel site-data/pro/universe.csv --out prices.csv \
  || echo "  prices: fetch failed; keeping the existing prices.csv"

# ---- 1c. the founders index, universe-wide ----
# The chart's cohort is founders.csv INTERSECT perf.csv; the generator just
# merged the universe founder labels, so fetching monthly closes for that
# list turns the 47-company S&P index into the ~354-company universe index
# with zero page changes -- the caption's count is computed, and young
# listings enter when their price history begins (the method note already
# says so). One Polygon aggs call per ticker, full history each, and
# merge_history keeps every month ever fetched. A failure keeps the
# existing perf.csv.
# Monthly data earns monthly fetches. The stage re-pulls full history per
# ticker (355 calls), so it runs only with a reason: a founder ticker
# missing from perf.csv (gap-healing -- the cohort can never silently
# lack a line), a month rollover, or FLE_PERF_FORCE=1.
if python3 - << 'PYGUARD'
import csv, datetime, os, sys
if os.environ.get("FLE_PERF_FORCE") == "1":
    print("  perf: forced"); sys.exit(0)
try:
    have = {r["ticker"] for r in csv.DictReader(open("perf.csv", encoding="utf-8-sig"))}
    newest = max(r["month"] for r in csv.DictReader(open("perf.csv", encoding="utf-8-sig")))
except (OSError, ValueError):
    print("  perf: no usable perf.csv; fetching"); sys.exit(0)
want = {r["ticker"] for r in csv.DictReader(open("site-data/founders.csv", encoding="utf-8-sig"))
        if (r.get("founder") or "").lower() == "yes"}
missing = sorted(want - have)
if missing:
    # a ticker Polygon genuinely has nothing for would otherwise trigger
    # the full fetch on EVERY deploy, forever; one attempt per day caps
    # the chase at the old nightly's cost
    marker = ".perf-attempt"
    today = datetime.date.today().isoformat()
    tried = ""
    try:
        tried = open(marker).read().strip()
    except OSError:
        pass
    if tried == today:
        print(f"  perf: {len(missing)} founder(s) still without history "
              f"({', '.join(missing[:6])}); already tried today, skipping")
        sys.exit(1)
    open(marker, "w").write(today)
    print(f"  perf: {len(missing)} founder(s) without price history "
          f"({', '.join(missing[:6])}...); fetching"); sys.exit(0)
if newest < datetime.date.today().strftime("%Y-%m"):
    print(f"  perf: newest stored month {newest}; month rolled; fetching"); sys.exit(0)
print(f"  perf: current through {newest}, cohort complete; skipping"); sys.exit(1)
PYGUARD
then
  python3 -m fle.cli perf --founders site-data/founders.csv --out perf.csv \
    || echo "  perf: fetch failed; keeping the existing perf.csv"
fi

rm -rf public && mkdir -p public
cp index.html about.html public/
[ -f terms.html ] && cp terms.html public/

# ---- 2. free tier, at the root: the generator's output plus prices ----
cp -r site-data/. public/
for f in prices.csv perf.csv; do
  [ -s "$f" ] && cp "$f" public/
done
# legacy names one release longer, so any cached page still finds its files
for f in sp500.csv history-free.csv; do
  [ -s "$f" ] && cp "$f" public/
done

# ---- 3. sanity before the world sees it ----
# the free root must never carry an unmasked universe: the root file and the
# pro file must differ, and the root file must contain masked rows
cmp -s public/universe.csv public/pro/universe.csv \
  && { echo "REFUSING: root universe.csv equals the pro file"; exit 2; }
grep -q ",1$" public/universe.csv \
  || grep -q $',1\r' public/universe.csv \
  || { echo "REFUSING: no masked rows in the public universe.csv"; exit 2; }

# wrangler bundles the functions/ directory from the project root by itself.
# FLE_BRANCH selects the Pages branch: "production" is aliased to the domain;
# anything else is a preview at https://<branch>.founderledequities.pages.dev
BRANCH="${FLE_BRANCH:-production}"
wrangler pages deploy public --project-name founderledequities --branch="$BRANCH" --commit-dirty=true
[ "$BRANCH" != "production" ] && echo "preview: https://${BRANCH}.founderledequities.pages.dev"
true
