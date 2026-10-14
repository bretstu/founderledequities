#!/usr/bin/env bash
# WHO CAME. The site's own count of visitors (every page carries the same
# beacon; crawlers and unfurlers never fire it), read from the D1 table.
#
#   ops/hits.sh                        # the last 7 days
#   ops/hits.sh today
#   ops/hits.sh yesterday
#   ops/hits.sh 30                     # the last 30 days
#   ops/hits.sh 2026-10-10             # that day (Eastern), any day the table has
#   ops/hits.sh 2026-10-06..2026-10-10 # those days inclusive
#   ops/hits.sh visitors               # today: one row per visitor, then each reader's journey as a table
#   ops/hits.sh visitors 2026-10-10    # the same for any window above (a day, a range, a count of days)
#
# FOUR QUESTIONS, IN ORDER (2026-10-14): how many came, how they found the
# site, what they looked at, what they did. The summary answers each once;
# the earlier report asked "how they found it" three ways (referrer, seen
# before, landed) and listed the site's own pages as referrers, which was
# a reader's navigation, not a source. Every view counts: nothing is
# classified or hidden, a scraping night reads as what it was.
#
# A WINDOW IS A WINDOW (2026-10-11): every section runs over whatever the
# first argument names, so a spike can be read on the day it happened,
# weeks later, with the same report and the same visitor list.
#
# Days are Eastern (the table stores UTC timestamps; the report shifts them
# by four hours, so a visit at 9 p.m. counts as today, not tomorrow). A
# private window is a new visitor every time; the owner's
# usual browser is switched off with ?nohit=1 once in the address bar.
set -euo pipefail
cd "$(dirname "$0")/.."

ARG="${1:-7}"
VISITORS=0
if [ "$ARG" = "visitors" ]; then VISITORS=1; ARG="${2:-today}"; fi
# the visit's day in Eastern time: UTC minus four hours (EDT); five in winter
OFF=$(TZ=America/New_York date +%z | sed -E 's/^([+-])0?([0-9]+)00$/\1\2/')
EDAY="date(ts, '${OFF} hours')"
TODAY="date('now', '${OFF} hours')"
# the window: SINGLE=1 is one day; START is the window's first day, for the
# question of who was seen on an earlier day
SINGLE=0
case "$ARG" in
  today)      WHERE="$EDAY = $TODAY"; LABEL="today"; START="$TODAY"; SINGLE=1 ;;
  yesterday)  WHERE="$EDAY = date('now', '${OFF} hours', '-1 days')"; LABEL="yesterday"; START="date('now', '${OFF} hours', '-1 days')"; SINGLE=1 ;;
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]..[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9])
              A="${ARG%%..*}"; B="${ARG##*..}"
              WHERE="$EDAY BETWEEN '$A' AND '$B'"; LABEL="$A to $B"; START="'$A'" ;;
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9])
              WHERE="$EDAY = '$ARG'"; LABEL="$ARG"; START="'$ARG'"; SINGLE=1 ;;
  ''|*[!0-9]*) echo "usage: ops/hits.sh [today|yesterday|N|YYYY-MM-DD|YYYY-MM-DD..YYYY-MM-DD]  or  ops/hits.sh visitors [window]" >&2; exit 2 ;;
  *)          WHERE="$EDAY >= date('now', '${OFF} hours', '-${ARG} days')"; LABEL="last ${ARG} days"; START="date('now', '${OFF} hours', '-${ARG} days')" ;;
esac
# the clock: a time of day on a single day, the date and time otherwise
if [ "$SINGLE" = "1" ]; then AT="substr(datetime(ts, '${OFF} hours'), 12, 5)"; else AT="substr(datetime(ts, '${OFF} hours'), 1, 16)"; fi
AT_FIRST="${AT//ts,/f.first_ts,}"

# WHERE A VISITOR CAME FROM, AS A SOURCE (2026-10-14): the host of the
# referrer on their FIRST page, with the site's own pages (navigation) and
# an empty referrer both reading as direct. Direct is a bucket (typed, a
# bookmark, an app, a private window, a link in an AI answer, a browser
# that strips the referrer), never a source.
HOST="CASE WHEN ref IS NULL OR ref='' OR ref LIKE '%founderledequities.com%' THEN 'direct' ELSE replace(CASE WHEN instr(substr(ref, instr(ref,'://')+3), '/')>0 THEN substr(substr(ref, instr(ref,'://')+3), 1, instr(substr(ref, instr(ref,'://')+3), '/')-1) ELSE substr(ref, instr(ref,'://')+3) END, 'www.', '') END"
# a visitor's first view in the window, and the source it carried
FIRST="(SELECT vid, MIN(ts) AS first_ts FROM hits WHERE kind='view' AND $WHERE GROUP BY vid)"
SOURCE="(SELECT h.vid, $HOST AS src, h.path AS landed FROM hits h JOIN $FIRST f ON f.vid=h.vid AND f.first_ts=h.ts WHERE h.kind='view' AND $WHERE)"
# what a visitor DID: the page's own controls (a sort, a filing opened, a
# switch, a chip, the watch form), and a filter on the companies page, which
# is a page address with a query and the most telling thing a reader does
ACTIONS="kind IN ('click','open','switch','sort')"
FILTER_OF="CASE WHEN path LIKE '/companies/?%' THEN 'filter ' || replace(substr(path, instr(path,'?')+1), '&', ', ') ELSE '' END"
DID_ACTS="SELECT vid, ts, path, name || CASE WHEN COALESCE(detail,'')<>'' THEN ' ' || detail ELSE '' END AS did FROM hits WHERE $ACTIONS AND $WHERE"
DID_ROW="$DID_ACTS UNION ALL SELECT vid, ts, path, $FILTER_OF FROM hits WHERE kind='view' AND path LIKE '/companies/?%' AND $WHERE"

# THE DATABASE BY NAME (2026-10-14). Asking `wrangler d1 list` for it meant the
# first run after wrangler refreshed its login printed a notice before the
# JSON and the script died on the parse; the second run worked. The name is
# fle-hits (ops/hits-schema.sql); FLE_HITS_DB overrides it.
DB="${FLE_HITS_DB:-fle-hits}"
Q() {   # a query, printed as a table
  wrangler d1 execute "$DB" --remote --json --command "$1" 2>/dev/null | python3 -c '
import sys, json
out = json.load(sys.stdin)
if not isinstance(out, list):          # wrangler reports an error as an object, not a result list (2026-09-29)
    print("  (query failed: " + str(out.get("error") or out.get("errors") or out)[:300] + ")"); sys.exit()
rows = out[0]["results"]
if not rows:
    print("  (none)"); sys.exit()
cols = list(rows[0].keys())
num = {c: all(isinstance(r[c], (int, float)) for r in rows) for c in cols}
w = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
w = {c: min(v, 72) for c, v in w.items()}
def cell(c, v):
    t = str(v)[:72]
    return t.rjust(w[c]) if num[c] else t.ljust(w[c])
print("  " + "  ".join(c.rjust(w[c]) if num[c] else c.ljust(w[c]) for c in cols))
for r in rows:
    print("  " + "  ".join(cell(c, r[c]) for c in cols))
'
}
R() {   # a query, one row per line, tab-separated, for the script itself to read
  wrangler d1 execute "$DB" --remote --json --command "$1" 2>/dev/null | python3 -c '
import sys, json
out = json.load(sys.stdin)
if not isinstance(out, list): sys.exit()
for r in out[0]["results"]:
    print("\t".join(str(v) for v in r.values()))
'
}

# ------------------------------------------------------------ the visitors
if [ "$VISITORS" = "1" ]; then
  echo "== visitors ($LABEL), one row each: when they arrived, where from, the page they landed on, pages seen, what they did =="
  Q "WITH f AS $FIRST, s AS $SOURCE, p AS (SELECT vid, COUNT(*) AS pages, MIN(country) AS country FROM hits WHERE kind='view' AND $WHERE GROUP BY vid), d AS (SELECT vid, GROUP_CONCAT(did || CASE WHEN n > 1 THEN ' x' || n ELSE '' END, ', ') AS did FROM (SELECT vid, did, COUNT(*) AS n, MIN(ts) AS first_ts FROM ($DID_ROW) GROUP BY vid, did ORDER BY first_ts) GROUP BY vid) SELECT $AT_FIRST AS first, substr(f.vid, 1, 6) AS who, p.country, s.src AS came_from, s.landed AS landed_on, p.pages, COALESCE(d.did, '') AS did FROM f JOIN p ON p.vid=f.vid LEFT JOIN s ON s.vid=f.vid LEFT JOIN d ON d.vid=f.vid ORDER BY f.first_ts"
  # then each reader who saw more than one page: the journey in order, with
  # what they did on the row where they did it (at most 40 such readers); a
  # one-page visitor is their row above, landing page included
  R "WITH f AS $FIRST, s AS $SOURCE, p AS (SELECT vid, COUNT(*) AS pages, MIN(country) AS country FROM hits WHERE kind='view' AND $WHERE GROUP BY vid) SELECT f.vid, substr(f.vid,1,6), p.country, s.src, p.pages FROM f JOIN p ON p.vid=f.vid LEFT JOIN s ON s.vid=f.vid WHERE p.pages > 1 ORDER BY f.first_ts LIMIT 40" | while IFS=$'\t' read -r vid who country src pages; do
    echo
    echo "== $who, $country, from $src: $pages pages =="
    Q "SELECT at, path, did FROM (SELECT ts, $AT AS at, path, $FILTER_OF AS did FROM hits WHERE kind='view' AND vid='$vid' AND $WHERE UNION ALL SELECT ts, $AT AS at, path, did FROM ($DID_ACTS) WHERE vid='$vid') ORDER BY ts"
  done
  exit 0
fi

# ------------------------------------------------------------- the summary
# 1. how many came
if [ "$SINGLE" = "1" ]; then
  echo "== $LABEL: how many came =="
  Q "WITH v AS (SELECT vid, COUNT(*) AS pages FROM hits WHERE kind='view' AND $WHERE GROUP BY vid), seen AS (SELECT DISTINCT vid FROM hits WHERE kind='view' AND $EDAY < $START), d AS (SELECT DISTINCT vid FROM ($DID_ROW)) SELECT COUNT(*) AS visitors, COALESCE(SUM(pages), 0) AS views, (SELECT COUNT(*) FROM v JOIN seen ON seen.vid=v.vid) AS seen_on_an_earlier_day, (SELECT COUNT(*) FROM v JOIN d ON d.vid=v.vid) AS did_anything FROM v"
else
  echo "== $LABEL: how many came, by day =="
  Q "SELECT $EDAY AS day, COUNT(DISTINCT vid) AS visitors, COUNT(*) AS views FROM hits WHERE kind='view' AND $WHERE GROUP BY 1 ORDER BY 1"
  echo "== and over the whole window: a visitor seen on 2+ days is a person who came back =="
  Q "WITH v AS (SELECT vid, COUNT(*) AS pages, COUNT(DISTINCT $EDAY) AS days FROM hits WHERE kind='view' AND $WHERE GROUP BY vid), d AS (SELECT DISTINCT vid FROM ($DID_ROW)) SELECT COUNT(*) AS visitors, COALESCE(SUM(pages), 0) AS views, SUM(CASE WHEN days>=2 THEN 1 ELSE 0 END) AS came_back, (SELECT COUNT(*) FROM v JOIN d ON d.vid=v.vid) AS did_anything FROM v"
fi
echo "== by country ($LABEL) =="
Q "SELECT country, COUNT(DISTINCT vid) AS visitors FROM hits WHERE kind='view' AND $WHERE GROUP BY country ORDER BY visitors DESC LIMIT 8"

# 2. how they found it: one row per visitor, the source of their first page
echo "== how they found it ($LABEL): each visitor's source, and the page they landed on =="
Q "WITH s AS $SOURCE SELECT src AS came_from, COUNT(*) AS visitors, CASE WHEN COUNT(DISTINCT landed) > 3 THEN COUNT(DISTINCT landed) || ' different pages' ELSE GROUP_CONCAT(DISTINCT landed) END AS landed_on FROM s GROUP BY src ORDER BY visitors DESC"

# 3. what they looked at
echo "== what they looked at ($LABEL) =="
Q "SELECT path, COUNT(DISTINCT vid) AS visitors, COUNT(*) AS views FROM hits WHERE kind='view' AND $WHERE GROUP BY path ORDER BY views DESC LIMIT 20"

# 4. how deep, and what they did. One page and gone is a bounce, whoever
# it was; two or more is a person reading.
echo "== how deep ($LABEL): pages viewed per visitor, and how many did anything =="
Q "WITH v AS (SELECT vid, COUNT(*) AS pages FROM hits WHERE kind='view' AND $WHERE GROUP BY vid), d AS (SELECT DISTINCT vid FROM ($DID_ROW)) SELECT CASE WHEN pages=1 THEN '1 page' WHEN pages<=3 THEN '2-3 pages' ELSE '4+ pages' END AS depth, COUNT(*) AS visitors, SUM(CASE WHEN d.vid IS NOT NULL THEN 1 ELSE 0 END) AS did_anything FROM v LEFT JOIN d ON d.vid=v.vid GROUP BY depth ORDER BY MIN(pages)"
echo "== what they did ($LABEL): the page's controls, the watch form, a filter on the companies page =="
Q "SELECT did AS what, COUNT(*) AS n, COUNT(DISTINCT vid) AS visitors FROM ($DID_ROW) GROUP BY did ORDER BY n DESC LIMIT 15"
