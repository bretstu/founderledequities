#!/usr/bin/env bash
# Assemble the public site and push it to Cloudflare Pages.
#
# ONE TREE, NO GATE (the paid tier left the code base 2026-09-23). public/
# carries the pages and every data file at the root; functions/api/ holds
# the watch and subscribe workers and nothing stands in front of the data.
#
# ONE REFRESH, ONE LIST. The nightly rebuilds the whole universe into the
# root files (panel.csv holds every member). The S&P list rides along as a
# data column (universe.csv's sp) and orders a page's neighbour links;
# it gates nothing.
set -euo pipefail
cd "$(dirname "$0")/.."

# the newest S&P list in force; the nightly writes a new dated one weekly
SP_LIST="${FLE_SP_LIST:-$(ls universe/sp500-????-??-??.csv | sort | tail -1)}"
echo "  S&P list: $SP_LIST"

# ---- 0. prices for the chart and the returns, BEFORE the site build reads them ----
# One daily price store (price-history/<TICKER>.csv) feeds the company
# page's price chart and the performance index; perf.csv is its month-ends.
# The nightly `prices` stage appends each day's close, so the full refresh
# (one Polygon call per ticker, ~2,140) runs only with a reason: the store
# is empty, a founder ticker has no series, a month rolled, or
# FLE_PERF_FORCE=1. A failure keeps what is on disk.
if python3 - << 'PYGUARD'
import csv, datetime, os, sys
if os.environ.get("FLE_QUICK") == "1":
    print("  perf: skipped (quick run); closes do not change intraday"); sys.exit(1)
if os.environ.get("FLE_PERF_FORCE") == "1":
    print("  perf: forced"); sys.exit(0)
if not os.path.isdir("price-history") or not os.listdir("price-history"):
    print("  perf: no price store yet; backfilling"); sys.exit(0)
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
  python3 -m fle.cli perf --panel panel.csv --store price-history --out perf.csv \
    || echo "  perf: fetch failed; keeping the existing price store and perf.csv"
fi

# ---- 1. price the whole universe ----
# Polygon's grouped-daily endpoint returns the entire market in ONE call;
# the ticker list only filters the output. Pricing 2,135 costs the same
# request as pricing 500. The same closes are appended to the daily price
# store, which is why this runs BEFORE the site build copies the store's
# files into place. A failure keeps yesterday's file -- the deploy never
# publishes an empty prices.csv over a good one.
if [ "${FLE_QUICK:-0}" = "1" ]; then
  echo "  prices: skipped (quick run); yesterday's close stands"
else
  python3 -m fle.cli prices --panel panel.csv --store price-history --out prices.csv \
    || echo "  prices: fetch failed; keeping the existing prices.csv"
fi

# ---- 1b. the site's data, generated fresh ----
python3 ops/build_site_data.py \
  panel.csv history.csv events.csv founders.csv \
  "$SP_LIST" site-data/ --prices price-history

# ---- 1b'. the card a shared link unfurls into, from tonight's numbers ----
# Pillow lives in the venv; the system python may lack it, and a missing
# picture must never stop a deploy -- the script keeps the last og.png.
OGPY=python3; [ -x .venv/bin/python ] && OGPY=.venv/bin/python
$OGPY ops/og_image.py panel.csv "$SP_LIST" prices.csv founders.csv og.png \
  || echo "  og image: not drawn; keeping the existing og.png"

rm -rf public && mkdir -p public
cp index.html about.html public/   # the about template is replaced by its built page (build_company_pages) further down
# THE FONTS ARE OURS. Inter and Plex Mono (design b, 2026-09-29), Latin-subset, served from the site:
# no third-party round trips before the type renders, and no invisible
# text while a font is on its way (font-display: swap).
mkdir -p public/fonts && cp fonts/*.woff2 public/fonts/
[ -f terms.html ] && cp terms.html public/
# /letter/* went to /alerts/ on 2026-09-29 (the letter left the site; its indexed addresses still land somewhere)
[ -f _redirects ] && cp _redirects public/
[ -f llms.txt ] && cp llms.txt public/    # what the site is, for the models that cite it
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

# ---- 2. the data, at the root: the generator's output plus prices ----
cp -r site-data/. public/
# (2b, the weekly briefing, ops/weekly.py, retired 2026-09-15: its week-over-week
#  section lives in ops/moves.py stakes, computed from the record, no snapshot)
# ---- 2c. THE WEEK'S DRAFTS, SATURDAY (2026-09-29: the letter left the pipeline;
# the site's own letter is over and Substack carries any future one). EDGAR
# accepts no filings at the weekend, so by Saturday the week is complete. The
# thread (drafts/moves-week.md) and the trajectories (drafts/stakes-month.md)
# are written for a person to post from (ops/moves.py); nothing is sent.
if [ "$(date +%u)" = "6" ]; then
  # THE PARTNERSHIP REGISTER, GENERATED FROM THE FILINGS (2026-09-15): the four
  # structured facts per chief executive, keep only what is provable, exclude
  # the rest; the delta is printed, written to drafts/, and mailed. Takes
  # effect at the next nightly, whose diff shows the same companies added or
  # dropped. About half an hour; the site is unaffected until then.
  python3 ops/partnerships_stage.py || echo "  partnerships: the stage failed; last week's register stands"
  python3 ops/moves.py week "$(date +%F)" || echo "  drafts: the week's moves failed"
  python3 ops/moves.py stakes "$(date +%F)" || echo "  drafts: the trajectories failed"
fi
# ---- 2e. THE DAY'S MOVES (distribution): drafts/moves-today.md, every
# founder filing since yesterday, largest move first, for a person to pick
# from. Nothing is posted.
python3 ops/moves.py today || echo "  drafts: today's moves failed"

# ---- 2f. THE FOOTNOTE READER, NIGHTLY (2026-09-20). Companies whose stated
# filings changed tonight have their new lines read; a footnote identical to
# one already read is copied, not asked again, so most nights make no model
# call at all (a ceiling of 80 when they do). A copied reading inherits the
# ruling of the line it was copied from. The register is regenerated from
# the decisions and takes effect at the NEXT walk; anything new that needs a
# person is written to drafts/footnotes-to-review.md and mailed. On Sundays
# the golden set is re-read against its rulings (about a dollar).
python3 ops/footnote_reads.py --nightly || echo "  footnotes: the reader failed; the register stands"
python3 ops/footnote_register.py --quiet || echo "  footnotes: the register was not regenerated"
python3 ops/footnote_review.py --summary || echo "  footnotes: the summary failed"
if [ "$(date +%u)" = "7" ]; then
  python3 ops/footnote_review.py --golden || echo "  footnotes: THE GOLDEN SET FAILED; check the prompt before the next reading"
fi

# ---- 3. the HTML says what the page says ----
# The hero, the stat strip and the top ten of the leaderboard are written
# into public/index.html as real markup, so a fetch without scripts (an
# assistant, a crawler, the first paint) reads tonight's numbers, not the
# placeholder. The script redraws them on load.
python3 ops/stamp_static.py panel.csv "$SP_LIST" prices.csv founders.csv public/index.html events.csv

# ---- 3a. one page per company, at its own address ----
# company.js and site.css are extracted from index.html here, so the pages
# and the home page share one source for every rule; sitemap.xml lists them.
# ---- 3b. one card per company, the price chart with the trades on it ----
# Every company page used to unfurl into the site-wide og.png. The cards
# are drawn from the price store and events.csv (about a minute for the
# universe); a page whose card was not drawn keeps og.png.
$OGPY ops/company_cards.py panel.csv "$SP_LIST" prices.csv founders.csv events.csv price-history og \
  || echo "  company cards: not drawn; pages keep og.png"
if [ -d og ] && [ -n "$(ls og 2>/dev/null)" ]; then mkdir -p public/og && cp og/*.png public/og/; fi
python3 ops/build_company_pages.py panel.csv founders.csv prices.csv "$SP_LIST" public/ events.csv history.csv --og og --prices price-history
# THE DATA HAS A VERSION. The pages fetched every CSV with no-store, so a
# return visit re-downloaded eleven megabytes. Each fetch now carries
# ?v=<this deploy>, so the browser and the edge cache a deploy's files
# until the next deploy changes the key.
DATAV=$(date -u +%Y%m%d%H%M)
# every built script that fetches data carries the key: companies.js was missing (2026-09-21), so the Companies page
# fetched /universe.csv?v=dev and the edge served the first copy it ever cached
for f in public/index.html public/about.html public/company.js public/tape.js public/companies.js public/alerts.js public/search.js; do
  [ -f "$f" ] && sed -i "s|const DATA_V=\"dev\"|const DATA_V=\"$DATAV\"|" "$f"
done
echo "  data version: $DATAV"
# and none may be left unstamped: a script fetching ?v=dev is a page that never sees a new deploy's data
if grep -l 'DATA_V="dev"' public/*.js public/*.html 2>/dev/null | grep -q .; then
  echo "  REFUSING TO PUBLISH -- a built page still carries DATA_V=\"dev\": $(grep -l 'DATA_V="dev"' public/*.js public/*.html | tr '\n' ' ')"; exit 1
fi

[ -s prices.csv ] && cp prices.csv public/
# perf.csv is published by build_site_data, cut to the chart's cohort; the
# full file (every company's closes) stays on disk for the 3-year returns.
# ---- 3. sanity before the world sees it ----
# the root universe.csv is the whole panel with every number: the file
# exists, has every company, and the top rows carry their stakes.
python3 - << 'PYOPEN' || { echo "REFUSING: the public universe.csv is short or missing its numbers"; exit 2; }
import csv, sys
rows = list(csv.DictReader(open("public/universe.csv", encoding="utf-8-sig")))
ok = len(rows) > 1500 and all(r.get("pct") for r in rows[:50])
sys.exit(0 if ok else 1)
PYOPEN

# wrangler bundles the functions/ directory from the project root by itself.
# FLE_BRANCH selects the Pages branch: "production" is aliased to the domain;
# anything else is a preview at https://<branch>.founderledequities.pages.dev
BRANCH="${FLE_BRANCH:-production}"
wrangler pages deploy public --project-name founderledequities --branch="$BRANCH" --commit-dirty=true
# ---- last. THE WATCHES (PLAN.md 5a): once today's pages are live, the day's
# open-market buys and discretionary sales go to /api/watch/run, which holds
# the watches and sends the alerts; the links in them land on pages that
# already carry the filing. The high-water mark keeps a rerun from posting
# a filing twice.
python3 ops/alerts.py || echo "  alerts: failed; the site is unaffected"
[ "$BRANCH" != "production" ] && echo "preview: https://${BRANCH}.founderledequities.pages.dev"
true
