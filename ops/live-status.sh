#!/usr/bin/env bash
# WHAT THE WATCHER IS DOING. One screen: the timer's health, the recent
# passes, today's founder filings and what became of each, and EDGAR's front
# page checked independently.
#
#   ops/live-status.sh          # today, the last four hours of passes
#   ops/live-status.sh 2026-09-11
#   HOURS=8 ops/live-status.sh  # a longer timeline
set -uo pipefail
cd "$(dirname "$0")/.."
DAY="${1:-$(date +%F)}"

echo "== timer =="
systemctl list-timers fle-live.timer --no-pager 2>/dev/null | head -2 | tail -1 \
  | awk '{print "  next", $1, $2, $3, "· last", $5, $6, $7}'
if systemctl is-active --quiet fle-live.service; then
  echo "  a pass is running now (a run inside it takes about two minutes)"
fi

HOURS="${HOURS:-4}"
echo "== the last $HOURS hours of passes (a pass that found a filing shows the ticker instead of 'nothing new') =="
journalctl -u fle-live.service --since "$DAY" --no-pager 2>/dev/null \
  | grep -E "python3\[" | sed 's/.*python3\[[0-9]*\]: //' \
  | grep -E "^\s+[0-9]{2}:[0-9]{2} |^- [0-9]{2}:[0-9]{2} [A-Z.-]+ ·" \
  | sed -E 's/^- ([0-9:]+) ([A-Z.-]+) · (.*)$/  \1 FOUND \2: \3/' | cut -c1-120 | tail -$((HOURS * 12))

echo "== founder filings on $DAY =="
F="drafts/live-$DAY.md"
if [ -f "$F" ]; then
  n=$(grep -cE "^- [0-9:]+ [A-Z.-]+ ·" "$F"); m=$(grep -c "← mailed" "$F"); x=$(grep -c "MAIL FAILED" "$F")
  echo "  $n filing(s), $m mailed, $x mail failure(s)"
  grep -E "^- [0-9:]+ [A-Z.-]+ ·|^- [0-9:]+ published" "$F" | sed 's|https://founderledequities.com||; s|· filing https://www.sec.gov/Archives/edgar/data/[0-9/]*||' | cut -c1-170
else
  echo "  none yet"
fi

echo "== EDGAR's front page, checked independently (every FOUNDER line should say seen) =="
python3 ops/live.py --show 2>/dev/null | grep -E "FOUNDER|Form 4 filings" || echo "  (could not read the feed)"

echo "== the mail rule =="
echo "  this watcher (mail to LIVE_TO): a founder's open-market buy or discretionary sale, any size;"
echo "  any other filing by a founder that moves the holding >= ${LIVE_MIN_MOVE:-1}%"
echo "  subscribers get less: the founder stream mails only moves of 1% or more;"
echo "  a per-company watch mails that person's trades of any size, or any other move of 1%+"
