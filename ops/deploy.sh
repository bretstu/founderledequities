#!/usr/bin/env bash
# Assemble the public site and push it to Cloudflare Pages.
#
# LAYOUT IS THE PAYWALL. public/ carries the pages and the free data at the
# root, and the full data under public/pro/ -- where functions/pro/[[path]].js
# stands in front of every request with the subscription check. The pipeline,
# tests and cache never ship.
set -euo pipefail
cd "$(dirname "$0")/.."

rm -rf public && mkdir -p public/pro
cp index.html about.html public/
[ -f terms.html ] && cp terms.html public/
[ -f universe.html ] && cp universe.html public/

# free tier, at the root
for f in sp500.csv prices.csv founders.csv perf.csv events-free.csv history-free.csv; do
  [ -s "$f" ] && cp "$f" public/
done
# full data, behind the gate
for f in events.csv history.csv; do
  [ -s "$f" ] && cp "$f" public/pro/
done

# wrangler bundles the functions/ directory from the project root by itself.
# FLE_BRANCH selects the Pages branch: "production" is aliased to the domain;
# anything else is a preview at https://<branch>.founderledequities.pages.dev
BRANCH="${FLE_BRANCH:-production}"
wrangler pages deploy public --project-name founderledequities --branch="$BRANCH" --commit-dirty=true
[ "$BRANCH" != "production" ] && echo "preview: https://${BRANCH}.founderledequities.pages.dev"
true
