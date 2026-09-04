#!/usr/bin/env bash
# Assemble the public site and push it to Cloudflare Pages.
#
# LAYOUT IS THE PAYWALL. public/ carries the pages and the free data at the
# root, and the full data under public/pro/ -- where functions/pro/[[path]].js
# stands in front of EVERY request with the subscription check (a catch-all,
# so the sharded tree under pro/ is gated by construction).
#
# ONE REFRESH, ONE LIST. The nightly rebuilds the whole universe into the
# root files (panel.csv holds every member). The S&P list is passed here
# for ONE purpose: deciding which rows
# are open at the root and which sit sealed under /pro/. The overlay of a
# fresh S&P onto a frozen snapshot is gone with the snapshot.
set -euo pipefail
cd "$(dirname "$0")/.."

# the newest S&P list in force; the nightly writes a new dated one weekly
SP_LIST="${FLE_SP_LIST:-$(ls universe/sp500-????-??-??.csv | sort | tail -1)}"
echo "  S&P list: $SP_LIST"

# ---- 0. prices for the chart and the returns, BEFORE the site build reads them ----
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
want = {r["ticker"] for r in csv.DictReader(open("founders.csv", encoding="utf-8-sig"))
        if (r.get("founder") or "").lower() == "yes"}
want |= {"SPY", "RSP"}   # both benchmarks must be on file
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
  python3 -m fle.cli perf --founders founders.csv --out perf.csv \
    || echo "  perf: fetch failed; keeping the existing perf.csv"
fi

# ---- 1. the site's data, generated fresh ----
python3 ops/build_site_data.py \
  panel.csv history.csv events.csv founders.csv \
  "$SP_LIST" site-data/

# ---- 1b. price the whole universe ----
# Polygon's grouped-daily endpoint returns the entire market in ONE call;
# the ticker list only filters the output. Pricing 2,135 costs the same
# request as pricing 500. A failure keeps yesterday's file -- the deploy
# never publishes an empty prices.csv over a good one.
python3 -m fle.cli prices --panel site-data/pro/universe.csv --out prices.csv \
  || echo "  prices: fetch failed; keeping the existing prices.csv"

# ---- 1b'. the card a shared link unfurls into, from tonight's numbers ----
# Pillow lives in the venv; the system python may lack it, and a missing
# picture must never stop a deploy -- the script keeps the last og.png.
OGPY=python3; [ -x .venv/bin/python ] && OGPY=.venv/bin/python
$OGPY ops/og_image.py panel.csv "$SP_LIST" prices.csv founders.csv og.png \
  || echo "  og image: not drawn; keeping the existing og.png"

rm -rf public && mkdir -p public
cp index.html about.html public/
[ -f terms.html ] && cp terms.html public/
# the universe page: every member, the snapshot date, the rules. The About
# page has linked to it since the promotion; it deploys now.
[ -f universe.html ] && cp universe.html public/
# THE CARD'S ADDRESS CHANGES WHEN THE CARD DOES. X and the other unfurlers
# cache an image by its URL for days -- including a failed fetch -- so a
# card redrawn nightly at the same address would be shown stale or not at
# all. The published pages point at og.png?v=<hash of the file>: a new
# picture is a new URL, and a cached miss never sticks.
if [ -s og.png ]; then
  cp og.png public/
  OGV=$(sha256sum og.png | cut -c1-10)
  sed -i "s|founderledequities.com/og.png\"|founderledequities.com/og.png?v=$OGV\"|g" public/index.html public/about.html
  echo "  og image: published as og.png?v=$OGV"
fi

# ---- 2. free tier, at the root: the generator's output plus prices ----
cp -r site-data/. public/
# ---- 3. the HTML says what the page says ----
# The hero, the stat strip and the top ten of the leaderboard are written
# into public/index.html as real markup, so a fetch without scripts (an
# assistant, a crawler, the first paint) reads tonight's numbers, not the
# placeholder. The script redraws them on load.
python3 ops/stamp_static.py panel.csv "$SP_LIST" prices.csv founders.csv public/index.html

# ---- 3a. one page per company, at its own address ----
# company.js and site.css are extracted from index.html here, so the pages
# and the home page share one source for every rule; sitemap.xml lists them.
python3 ops/build_company_pages.py panel.csv founders.csv prices.csv "$SP_LIST" public/ events.csv history.csv
[ -s prices.csv ] && cp prices.csv public/
# perf.csv is published by build_site_data, cut to the chart's cohort; the
# full file (every company's closes) stays on disk for the 3-year returns.
# NO ROOT COPY OF THE PANEL. It is the whole unmasked universe, and a copy
# at the root would publish every sealed stake. The page reads universe.csv.

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
