#!/usr/bin/env bash
# WHO GETS ALERTS (2026-09-17; rebuilt 2026-10-14). Everything lives in the
# D1 database the hits share: the `watches` table is one row per address per
# name (FOUNDERS meaning every founder), confirmed or still waiting on the
# click, and `alerts_sent` is one row per email that went out. Three
# questions, three tables: who gets alerts (one row per address), what is
# watched, and what was sent. The Resend contact list left with the letter
# (no letter since 2026-09-29) and is no longer reported.
#
# A "reader" was counted wrong before: the old readers count took in an
# address that asked for three watches and never confirmed any. Now an
# address that gets alerts is one with a confirmed watch; the ones that asked
# and never confirmed are their own short table, so a stranger who tried is
# seen and not mistaken for a subscriber.
#
#   ops/subscribers.sh        # who gets alerts, what is watched, the mails of the last 7 days
#   ops/subscribers.sh 30     # the mails of the last 30 days
set -e
cd "$(dirname "$0")/.."
DAYS="${1:-7}"
# the database by name, as hits.sh does: listing the databases printed a login notice on a fresh shell and the name parse failed on it
DB="${FLE_HITS_DB:-fle-hits}"
# sent is stamped in UTC by the run endpoint; shown here in Eastern (EDT: -4h; EST: -5h), in every table (the first showed UTC until 2026-10-15)
OFF=$(date +%Z | grep -q EDT && echo '-4 hours' || echo '-5 hours')
Q() {   # a query, printed as a table
  wrangler d1 execute "$DB" --remote --json --command "$1" 2>/dev/null | python3 -c '
import sys, json
out = json.load(sys.stdin)
if not isinstance(out, list):          # wrangler reports an error as an object, not a result list
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

# ------------------------------------------------------------ who gets alerts
# one row per address with a confirmed watch: the founder stream yes or no,
# how many companies, anything still pending, when the first watch was made,
# when the last alert went out
echo "== who gets alerts (one row per address) =="
Q "SELECT w.email AS address,
          max(CASE WHEN w.tk='FOUNDERS' AND w.confirmed=1 THEN 'yes' ELSE 'no' END) AS founders,
          sum(w.tk!='FOUNDERS' AND w.confirmed=1) AS companies,
          sum(w.confirmed=0) AS pending,
          substr(min(w.created),1,10) AS since,
          coalesce((SELECT date(datetime(max(s.sent), '$OFF')) FROM alerts_sent s JOIN watches x ON x.id=s.watch_id WHERE x.email=w.email), '') AS last_alert
   FROM watches w GROUP BY w.email HAVING sum(w.confirmed=1) > 0 ORDER BY since"
read -r N_ON N_TRIED < <(R "SELECT
   (SELECT count(DISTINCT email) FROM watches WHERE confirmed=1),
   (SELECT count(DISTINCT email) FROM watches w WHERE confirmed=0 AND NOT EXISTS (SELECT 1 FROM watches c WHERE c.email=w.email AND c.confirmed=1))" | tr '\t' ' ')
[ "${N_ON:-0}" = "1" ] && echo "  1 address gets alerts" || echo "  ${N_ON:-0} addresses get alerts"
if [ "${N_TRIED:-0}" != "0" ]; then
  echo
  echo "== asked and never confirmed (no alerts go to these) =="
  Q "SELECT email AS address, substr(min(created),1,10) AS asked, group_concat(tk, ', ') AS wanted
     FROM watches w WHERE confirmed=0 AND NOT EXISTS (SELECT 1 FROM watches c WHERE c.email=w.email AND c.confirmed=1)
     GROUP BY email ORDER BY asked"
fi

# ------------------------------------------------------------ what is watched
echo
echo "== what is watched (confirmed) =="
Q "SELECT CASE WHEN tk='FOUNDERS' THEN 'every founder' ELSE tk END AS watch, CASE WHEN tk='FOUNDERS' THEN '' ELSE ceo END AS ceo, count(*) AS watchers
   FROM watches WHERE confirmed=1 GROUP BY tk, ceo ORDER BY (tk='FOUNDERS') DESC, watchers DESC, tk LIMIT 60"

# ------------------------------------------------------------ what was sent
SINCE=$(date -d "$DAYS days ago" +%Y-%m-%dT00:00:00 2>/dev/null || date -v-"$DAYS"d +%Y-%m-%dT00:00:00)
echo
echo "== alert emails sent, last $DAYS days (Eastern) =="
Q "SELECT date(datetime(s.sent, '$OFF')) AS day, count(*) AS emails, count(DISTINCT x.email) AS addresses, group_concat(DISTINCT coalesce(x.tk, '(a watch since stopped)')) AS about
   FROM alerts_sent s LEFT JOIN watches x ON x.id = s.watch_id WHERE s.sent >= '$SINCE' GROUP BY day ORDER BY day"
