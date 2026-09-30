#!/usr/bin/env bash
# WHO CAME. The site's own count of visitors (every page carries the same
# beacon; crawlers and unfurlers never fire it), read from the D1 table.
#
#   ops/hits.sh            # the last 7 days
#   ops/hits.sh today
#   ops/hits.sh 30         # the last 30 days
#   ops/hits.sh visitors   # today, one line per visit: when, who (a short id), where from, country, what they did
#
# Below the daily counts: new or returning by source, pages per visitor, and
# each visitor's landing page (2026-09-29). A returning direct visitor is the
# closest thing here to a bookmark.
#
# Days are Eastern (the table stores UTC timestamps; the report shifts them
# by four hours, so a visit at 9 p.m. counts as today, not tomorrow). A
# private window is a new visitor every time; the owner's
# usual browser is switched off with ?nohit=1 once in the address bar.
# t.co in the referrer column is X; blank is direct, private, or an app.
set -euo pipefail
cd "$(dirname "$0")/.."

ARG="${1:-7}"
VISITORS=0
if [ "$ARG" = "visitors" ]; then VISITORS=1; ARG="today"; fi
# the visit's day in Eastern time: UTC minus four hours (EDT); five in winter
OFF=$(TZ=America/New_York date +%z | sed -E 's/^([+-])0?([0-9]+)00$/\1\2/')
EDAY="date(ts, '${OFF} hours')"
if [ "$ARG" = "today" ]; then
  WHERE="$EDAY = date('now', '${OFF} hours')"; LABEL="today"; START="date('now', '${OFF} hours')"
else
  WHERE="$EDAY >= date('now', '${OFF} hours', '-${ARG} days')"; LABEL="last ${ARG} days"; START="date('now', '${OFF} hours', '-${ARG} days')"
fi
# WHERE THEY CAME FROM, IN FOUR WORDS (2026-09-29): a referrer is a URL; a
# reader wants to know search, X, direct or elsewhere. Direct is a bucket
# (typed, a bookmark, an app, a private window, a browser that strips the
# referrer), never a source.
SRC="CASE WHEN ref LIKE '%google.%' OR ref LIKE '%bing.com%' OR ref LIKE '%duckduckgo%' OR ref LIKE '%yahoo.%' OR ref LIKE '%ecosia%' OR ref LIKE '%brave.com%' THEN 'search' WHEN ref LIKE '%t.co/%' OR ref LIKE '%twitter.com%' OR ref LIKE '%x.com%' THEN 'x' WHEN ref='' OR ref IS NULL THEN 'direct' ELSE 'other' END"

DB="${FLE_HITS_DB:-$(wrangler d1 list --json 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['name'])")}"
Q() {
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

if [ "$VISITORS" = "1" ]; then
  echo "== today's visits, one line each (Eastern) =="
  Q "SELECT substr(datetime(ts, '${OFF} hours'), 12, 5) AS at, substr(vid, 1, 6) AS who, country, path, COALESCE(NULLIF(ref,''),'(direct)') AS came_from, COALESCE(NULLIF(device,''),'') AS device, CASE WHEN pro=1 THEN 'pro' ELSE '' END AS pro FROM hits WHERE kind='view' AND $WHERE ORDER BY ts"
  echo "== and what each did (clicks, pages opened) =="
  Q "SELECT substr(datetime(ts, '${OFF} hours'), 12, 5) AS at, substr(vid, 1, 6) AS who, kind, name, COALESCE(detail,'') AS detail, path FROM hits WHERE kind IN ('click','open','switch','sort') AND $WHERE ORDER BY ts"
  exit 0
fi
echo "== views per day ($LABEL) =="
Q "SELECT $EDAY AS day, COUNT(DISTINCT vid) AS visitors, COUNT(*) AS views FROM hits WHERE kind='view' AND $WHERE GROUP BY 1 ORDER BY 1"
echo "== by page ($LABEL) =="
Q "SELECT path, COUNT(DISTINCT vid) AS visitors, COUNT(*) AS views FROM hits WHERE kind='view' AND $WHERE GROUP BY path ORDER BY views DESC LIMIT 20"
echo "== by referrer ($LABEL): t.co is X; (direct) is typed, private, or an app =="
Q "SELECT COALESCE(NULLIF(ref,''),'(direct)') AS ref, COUNT(DISTINCT vid) AS visitors, COUNT(*) AS views FROM hits WHERE kind='view' AND $WHERE GROUP BY ref ORDER BY views DESC LIMIT 12"
echo "== by country ($LABEL) =="
Q "SELECT country, COUNT(DISTINCT vid) AS visitors FROM hits WHERE kind='view' AND $WHERE GROUP BY country ORDER BY visitors DESC LIMIT 8"
echo "== what they did ($LABEL) =="
Q "SELECT kind || ' ' || name AS what, COUNT(*) AS n FROM hits WHERE kind IN ('click','open') AND $WHERE GROUP BY what ORDER BY n DESC LIMIT 10"
# WHO CAME BACK (2026-09-29): the beacon keeps one visitor id per browser,
# so a person who returns is the same id on another day, and a crawler that
# keeps no storage is a new id every time. Counted within the window (days
# visited per visitor) so the answer does not depend on how far back the
# table goes; a visitor on two or more days from direct is the nearest
# thing this table has to a bookmark. On "today" the window is one day, so
# the second query asks instead whether today's visitors were seen before.
if [ "$ARG" = "today" ]; then
  echo "== seen before today, by where they came from (today) =="
  Q "WITH v AS (SELECT vid, $SRC AS src FROM hits WHERE kind='view' AND $WHERE GROUP BY vid), seen AS (SELECT DISTINCT vid FROM hits WHERE kind='view' AND $EDAY < $START) SELECT v.src AS came_from, SUM(CASE WHEN seen.vid IS NULL THEN 1 ELSE 0 END) AS first_time, SUM(CASE WHEN seen.vid IS NOT NULL THEN 1 ELSE 0 END) AS seen_before FROM v LEFT JOIN seen ON seen.vid = v.vid GROUP BY v.src ORDER BY COUNT(*) DESC"
else
  echo "== days visited per visitor, by where they first came from ($LABEL): 2+ days is a person who came back =="
  Q "WITH v AS (SELECT vid, COUNT(DISTINCT $EDAY) AS days, MIN(ts) AS first_ts FROM hits WHERE kind='view' AND $WHERE GROUP BY vid), f AS (SELECT vid, $SRC AS src FROM hits WHERE kind='view' AND $WHERE) SELECT (SELECT src FROM f WHERE f.vid = v.vid LIMIT 1) AS came_from, SUM(CASE WHEN days=1 THEN 1 ELSE 0 END) AS one_day, SUM(CASE WHEN days=2 THEN 1 ELSE 0 END) AS two_days, SUM(CASE WHEN days>=3 THEN 1 ELSE 0 END) AS three_plus FROM v GROUP BY came_from ORDER BY COUNT(*) DESC"
fi
# HOW DEEP (2026-09-29): one page and gone is a bounce, whoever it was; two
# or more is a person reading. The count of visitors who clicked anything at
# all is the number the home page is judged by.
echo "== how deep ($LABEL): pages viewed per visitor, and how many clicked anything =="
Q "WITH d AS (SELECT vid, COUNT(*) AS pages FROM hits WHERE kind='view' AND $WHERE GROUP BY vid), c AS (SELECT DISTINCT vid FROM hits WHERE kind IN ('click','open','switch','sort') AND $WHERE) SELECT CASE WHEN pages=1 THEN '1 page' WHEN pages<=3 THEN '2-3 pages' ELSE '4+ pages' END AS depth, COUNT(*) AS visitors, SUM(CASE WHEN c.vid IS NOT NULL THEN 1 ELSE 0 END) AS clicked FROM d LEFT JOIN c ON c.vid = d.vid GROUP BY depth ORDER BY MIN(pages)"
# WHERE THEY LANDED (2026-09-29): the first page of each visit, with its
# source; a company page from search is the SEO working, the home page
# direct is a link or a bot.
echo "== where they landed ($LABEL): each visitor's first page, by source =="
Q "WITH f AS (SELECT vid, path, $SRC AS src, ROW_NUMBER() OVER (PARTITION BY vid ORDER BY ts) AS rn FROM hits WHERE kind='view' AND $WHERE) SELECT path, src AS came_from, COUNT(*) AS visitors FROM f WHERE rn=1 GROUP BY path, src ORDER BY visitors DESC LIMIT 12"
