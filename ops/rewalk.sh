#!/usr/bin/env bash
# A FORCED FULL WALK, SAFELY (2026-09-18). Three times this week the walk was
# run by hand as a long shell line, the sudo credential expired during the
# twenty minutes, and the watcher stayed stopped until someone noticed. This
# takes the credential once, keeps it alive for the duration, backs up the
# panel and the history, moves the state aside, walks, restarts the watcher
# WHATEVER HAPPENS (a trap), and prints the diff and the disagreement count.
#
#   ops/rewalk.sh <label>          # e.g. ops/rewalk.sh v257 -> backups panel-pre-v257.csv
#   ops/rewalk.sh <label> --keep   # keep the state files (a carry-walk, not a forced one)
set -u
cd "$(dirname "$0")/.."
LABEL="${1:?a label for the backups, e.g. v257}"
KEEP="${2:-}"
TS=$(date +%Y-%m-%d_%H%M)
BK="$HOME/backups"; mkdir -p "$BK"

sudo -v || { echo "no sudo credential; nothing started"; exit 1; }
# keep the credential fresh in the background for the walk's duration
( while true; do sudo -n true; sleep 240; kill -0 "$$" 2>/dev/null || exit; done ) 2>/dev/null &
KEEPALIVE=$!
restart() {
  sudo -n systemctl start fle-live.timer 2>/dev/null || sudo systemctl start fle-live.timer
  kill "$KEEPALIVE" 2>/dev/null
  echo "watcher: $(systemctl list-timers --no-pager 2>/dev/null | grep fle-live | awk '{print $1, $2, $3}' || echo 'not listed: start it by hand')"
}
trap restart EXIT

cp panel.csv "$BK/panel-pre-$LABEL.csv" && cp history.csv "$BK/history-pre-$LABEL.csv"
echo "backed up: $BK/panel-pre-$LABEL.csv, $BK/history-pre-$LABEL.csv"
sudo systemctl stop fle-live.timer
if [ "$KEEP" != "--keep" ]; then
  [ -f _staging/panel.jsonl ] && mv _staging/panel.jsonl "_staging/panel.pre-$LABEL.jsonl"
  [ -f history-state.json ] && mv history-state.json "history-state.pre-$LABEL.json"
fi
export FLE_QUICK=1
date
python3 -m fle.cli refresh --dir "$(pwd)" --force 2>&1 | tee "full-walk-$TS.log" | grep -E "rewalked|capped|graded|delisted|partnerships|published|deployed|Traceback"
date
.venv/bin/python -m fle.cli diff --before "$BK/panel-pre-$LABEL.csv" --after panel.csv --limit 40 | head -50
python3 - <<'PY'
import csv
a=[r for r in csv.DictReader(open('panel.csv',encoding='utf-8-sig'))]
dis=[r['ticker'] for r in a if 'disagrees with itself' in r['chain']]
print(f"{len(dis)} disagreements:", dis)
PY
