#!/usr/bin/env bash
# THE SITE AS OF RIGHT NOW. The nightly, minus the price stage (closes do
# not change intraday): every filing on EDGAR at this minute, the walk for
# whoever filed, the events, the pages, the deploy, the alerts, the drafts.
# About ten minutes (the scan of 2,135 filing feeds is the floor). Best run
# around 6:30 p.m. Eastern on a weekday, after the day's filing wave
# (EDGAR accepts until 10 p.m.; most Form 4s land after the close), when
# a founder bought that day and the post should not wait until tomorrow.
#
#   ops/now.sh              # everyone: the full quick run, about ten minutes
#   ops/now.sh UPST,INBX    # targeted: only these companies are walked; the
#                           # rest keep last night's rows; about two minutes
#   REWALK=1 ops/now.sh CVNA,ASST   # targeted, and their history walked again even
#                           # with no new filing (a rule change); refresh.log has the walk
#   FORCE=1 ops/now.sh COIN # publish even if a verified holding moved without a filing
#                           # (after the change has been checked by hand)
set -euo pipefail
cd "$(dirname "$0")/.."
export FLE_QUICK=1
TICKERS="${1:-}"
python3 -m fle.cli refresh --dir "$(pwd)" ${TICKERS:+--tickers "$TICKERS"} ${REWALK:+--rewalk} ${FORCE:+--force} 2>&1 | tee refresh.log | grep --line-buffered -E "^\[|VENDOR|published|targeted|alerts:|drafts:|Deployment|refus|Traceback"
echo
echo "== today's moves (drafts/moves-today.md) =="
sed -n '3,40p' drafts/moves-today.md 2>/dev/null || echo "(no draft written)"
