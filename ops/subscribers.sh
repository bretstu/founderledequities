#!/usr/bin/env bash
# WHO IS SUBSCRIBED TO WHAT (2026-09-17). The letter lives in Resend (a
# contact in the segment); live founder alerts and the watches live in the
# same D1 database as the hits (the `watches` table: one row per address per
# name, FOUNDERS meaning every founder), and the alert emails are counted in
# `alerts_sent`. Resend's Audience page shows only the first; this shows all.
#
#   ops/subscribers.sh            # the counts, the watches by name, this week's alert mails
#   ops/subscribers.sh --emails   # the same with the addresses
set -e
cd "$(dirname "$0")/.."
# only the one key, read by name: .env holds values with spaces and is not a shell script
RESEND_API_KEY="${RESEND_API_KEY:-$(grep -E '^RESEND_API_KEY=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")}"
DB="${FLE_HITS_DB:-$(wrangler d1 list --json 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['name'])")}"
q() { wrangler d1 execute "$DB" --remote --json --command "$1" 2>/dev/null | python3 -c '
import sys,json
d=json.load(sys.stdin); rows=(d[0].get("results") if isinstance(d,list) else d.get("results")) or []
for r in rows: print("  " + "  ".join(f"{k}={v}" for k,v in r.items()))'; }
WEEK=$(date -d "7 days ago" +%Y-%m-%dT00:00:00 2>/dev/null || date -v-7d +%Y-%m-%dT00:00:00)
echo "== the letter (Resend) =="
if [ -n "$RESEND_API_KEY" ]; then
  curl -s -H "Authorization: Bearer $RESEND_API_KEY" "https://api.resend.com/contacts" | python3 -c '
import sys,json
d=json.load(sys.stdin); c=d.get("data",[]) if isinstance(d,dict) else []
on=[x for x in c if not x.get("unsubscribed")]
print(f"  {len(on)} subscribed, {len(c)-len(on)} unsubscribed")
if "--emails" in sys.argv[1:]: [print("   ", x.get("email")) for x in on]' "$@"
else echo "  (RESEND_API_KEY not in .env)"; fi
echo "== live founder alerts (a watch on FOUNDERS) =="
q "SELECT count(*) AS subscribers FROM watches WHERE tk='FOUNDERS' AND confirmed=1"
[ "$1" = "--emails" ] && q "SELECT email, created FROM watches WHERE tk='FOUNDERS' AND confirmed=1 ORDER BY created DESC"
echo "== watches by name (confirmed) =="
q "SELECT tk, ceo, count(*) AS watchers FROM watches WHERE tk!='FOUNDERS' AND confirmed=1 GROUP BY tk, ceo ORDER BY watchers DESC, tk LIMIT 40"
q "SELECT count(DISTINCT email) AS readers_with_a_watch, count(*) AS watches, sum(confirmed=0) AS unconfirmed FROM watches WHERE tk!='FOUNDERS'"
[ "$1" = "--emails" ] && q "SELECT email, tk, confirmed, created FROM watches WHERE tk!='FOUNDERS' ORDER BY created DESC LIMIT 60"
echo "== alert emails sent since $WEEK (Eastern) =="
# sent is stamped in UTC by the run endpoint; shown here in Eastern (EDT: -4h; EST: -5h)
OFF=$(date +%Z | grep -q EDT && echo '-4 hours' || echo '-5 hours')
q "SELECT date(datetime(sent, '$OFF')) AS day, count(*) AS emails, count(DISTINCT watch_id) AS watches FROM alerts_sent WHERE sent >= '$WEEK' GROUP BY day ORDER BY day"
