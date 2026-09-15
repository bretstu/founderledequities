#!/usr/bin/env bash
# WHO CAME. The site's own count of visitors (every page carries the same
# beacon; crawlers and unfurlers never fire it), read from the D1 table.
#
#   ops/hits.sh            # the last 7 days
#   ops/hits.sh today
#   ops/hits.sh 30         # the last 30 days
#
# Days are Eastern (the table stores UTC timestamps; the report shifts them
# by four hours, so a visit at 9 p.m. counts as today, not tomorrow). A
# private window is a new visitor every time; the owner's
# usual browser is switched off with ?nohit=1 once in the address bar.
# t.co in the referrer column is X; blank is direct, private, or an app.
set -euo pipefail
cd "$(dirname "$0")/.."

ARG="${1:-7}"
# the visit's day in Eastern time: UTC minus four hours (EDT); five in winter
OFF=$(TZ=America/New_York date +%z | sed -E 's/^([+-])0?([0-9]+)00$/\1\2/')
EDAY="date(ts, '${OFF} hours')"
if [ "$ARG" = "today" ]; then
  WHERE="$EDAY = date('now', '${OFF} hours')"; LABEL="today"
else
  WHERE="$EDAY >= date('now', '${OFF} hours', '-${ARG} days')"; LABEL="last ${ARG} days"
fi

DB="${FLE_HITS_DB:-$(wrangler d1 list --json 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['name'])")}"
Q() {
  wrangler d1 execute "$DB" --remote --json --command "$1" 2>/dev/null | python3 -c '
import sys, json
rows = json.load(sys.stdin)[0]["results"]
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
