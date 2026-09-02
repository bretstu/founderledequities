#!/usr/bin/env bash
# What real people did on the site: visitors, sessions, sections, clicks.
#
#   ops/hits.sh            # the last 14 days
#   ops/hits.sh 30         # the last 30
#
# Reads the D1 database the page's beacons write (functions/api/hit.js).
# "Session" is one tab; "visitor" is one browser (a random id it keeps).
set -euo pipefail
cd "$(dirname "$0")/.."
DAYS="${1:-14}"
DB="${FLE_HITS_DB:-fle-hits}"
SINCE=$(date -d "-$DAYS days" +%F 2>/dev/null || date -v-"${DAYS}"d +%F)

q() {  # run one query, print as a table
  wrangler d1 execute "$DB" --remote --json --command "$1" 2>/dev/null \
  | python3 -c '
import json,sys
d=json.load(sys.stdin)
rows=(d[0] if isinstance(d,list) else d).get("results",[])
if not rows: print("  (nothing)"); sys.exit()
cols=list(rows[0].keys()); w=[max(len(c),*(len(str(r.get(c,""))) for r in rows)) for c in cols]
print("  "+"  ".join(c.ljust(w[i]) for i,c in enumerate(cols)))
for r in rows: print("  "+"  ".join(str(r.get(c,"")).ljust(w[i]) for i,c in enumerate(cols)))'
}

echo "== visits by day (since $SINCE) =="
q "SELECT day, COUNT(DISTINCT vid) AS visitors, COUNT(DISTINCT sid) AS sessions,
          SUM(kind='view') AS pageviews, SUM(pro)>0 AS any_pro
   FROM hits WHERE day>='$SINCE' GROUP BY day ORDER BY day DESC"

echo; echo "== where they came from (page views) =="
q "SELECT CASE WHEN ref='' THEN '(direct)' ELSE substr(ref,1,60) END AS referrer, COUNT(*) AS views
   FROM hits WHERE kind='view' AND day>='$SINCE' GROUP BY 1 ORDER BY 2 DESC LIMIT 15"

echo; echo "== how far they got: share of sessions that reached each section =="
q "SELECT name AS section,
          ROUND(100.0*COUNT(DISTINCT sid)/(SELECT COUNT(DISTINCT sid) FROM hits WHERE day>='$SINCE'),0) AS pct_of_sessions,
          COUNT(DISTINCT sid) AS sessions
   FROM hits WHERE kind='section' AND day>='$SINCE' GROUP BY name ORDER BY 3 DESC"

echo; echo "== what they did (sessions with at least one) =="
q "SELECT kind||' '||name AS action, COUNT(DISTINCT sid) AS sessions, COUNT(*) AS times
   FROM hits WHERE kind NOT IN ('view','section') AND day>='$SINCE'
   GROUP BY 1 ORDER BY 2 DESC LIMIT 25"

echo; echo "== the details behind the clicks (top 25) =="
q "SELECT kind||' '||name AS action, detail, COUNT(*) AS times
   FROM hits WHERE kind NOT IN ('view','section') AND detail<>'' AND day>='$SINCE'
   GROUP BY 1,2 ORDER BY 3 DESC LIMIT 25"

echo; echo "== the funnel =="
q "SELECT (SELECT COUNT(DISTINCT sid) FROM hits WHERE day>='$SINCE') AS sessions,
          (SELECT COUNT(DISTINCT sid) FROM hits WHERE day>='$SINCE' AND kind='click' AND name='gopro') AS opened_pro_box,
          (SELECT COUNT(DISTINCT sid) FROM hits WHERE day>='$SINCE' AND kind='click' AND name='checkout') AS clicked_checkout,
          (SELECT COUNT(DISTINCT sid) FROM hits WHERE day>='$SINCE' AND kind='click' AND name='signin') AS clicked_sign_in,
          (SELECT COUNT(DISTINCT sid) FROM hits WHERE day>='$SINCE' AND pro=1) AS pro_sessions"

echo; echo "== which Go Pro button opened the box =="
q "SELECT detail AS where_on_page, COUNT(DISTINCT sid) AS sessions, COUNT(*) AS times
   FROM hits WHERE kind='click' AND name='gopro' AND day>='$SINCE' GROUP BY 1 ORDER BY 2 DESC"

echo; echo "== countries and devices =="
q "SELECT country, device, COUNT(DISTINCT sid) AS sessions FROM hits WHERE kind='view' AND day>='$SINCE'
   GROUP BY 1,2 ORDER BY 3 DESC LIMIT 12"
