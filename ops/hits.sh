#!/usr/bin/env bash
# WHO CAME. The site's own count of visitors (every page carries the same
# beacon; crawlers and unfurlers never fire it), read from the D1 table.
#
#   ops/hits.sh            # the last 7 days
#   ops/hits.sh today
#   ops/hits.sh 30         # the last 30 days
#
# Days are UTC. A private window is a new visitor every time; the owner's
# usual browser is switched off with ?nohit=1 once in the address bar.
# t.co in the referrer column is X; blank is direct, private, or an app.
set -euo pipefail
cd "$(dirname "$0")/.."

ARG="${1:-7}"
if [ "$ARG" = "today" ]; then
  WHERE="day = date('now')"; LABEL="today"
else
  WHERE="day >= date('now','-${ARG} days')"; LABEL="last ${ARG} days"
fi

DB="${FLE_HITS_DB:-$(wrangler d1 list --json 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['name'])")}"
Q() {
  wrangler d1 execute "$DB" --remote --json --command "$1" 2>/dev/null \
    | python3 -c "import sys,json;r=json.load(sys.stdin)[0]['results'];[print('  '+'  '.join(f'{v}' for v in x.values())) for x in r] if r else print('  (none)')"
}

echo "== views per day ($LABEL): day · visitors · views =="
Q "SELECT day, COUNT(DISTINCT vid) AS visitors, COUNT(*) AS views FROM hits WHERE kind='view' AND $WHERE GROUP BY day ORDER BY day"
echo "== by page ($LABEL): path · visitors · views =="
Q "SELECT path, COUNT(DISTINCT vid) AS visitors, COUNT(*) AS views FROM hits WHERE kind='view' AND $WHERE GROUP BY path ORDER BY views DESC LIMIT 20"
echo "== by referrer ($LABEL): t.co is X; (direct) is typed, private or an app =="
Q "SELECT COALESCE(NULLIF(ref,''),'(direct)') AS ref, COUNT(DISTINCT vid) AS visitors, COUNT(*) AS views FROM hits WHERE kind='view' AND $WHERE GROUP BY ref ORDER BY views DESC LIMIT 12"
echo "== by country ($LABEL) =="
Q "SELECT country, COUNT(DISTINCT vid) AS visitors FROM hits WHERE kind='view' AND $WHERE GROUP BY country ORDER BY visitors DESC LIMIT 8"
echo "== what they did ($LABEL): filings opened, company pages opened, Go Pro =="
Q "SELECT kind || ' ' || name AS what, COUNT(*) AS n FROM hits WHERE kind IN ('click','open') AND $WHERE GROUP BY what ORDER BY n DESC LIMIT 10"
