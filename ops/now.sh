#!/usr/bin/env bash
# THE SITE AS OF RIGHT NOW. The nightly, minus the price stage (closes do
# not change intraday): every filing on EDGAR at this minute, the walk for
# whoever filed, the events, the pages, the deploy, the alerts, the drafts.
# About three minutes. For a weekday when a founder bought this morning
# and the post should not wait until tomorrow.
#
#   ops/now.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export FLE_QUICK=1
python3 -m fle.cli refresh --dir "$(pwd)" 2>&1 | tee refresh.log | grep --line-buffered -E "^\[|VENDOR|published|alerts:|drafts:|Deployment|refus|Traceback"
echo
echo "== today's decisions (drafts/x-today.md) =="
sed -n '3,40p' drafts/x-today.md 2>/dev/null || echo "(no draft written)"
