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
