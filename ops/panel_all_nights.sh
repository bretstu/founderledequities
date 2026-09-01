#!/usr/bin/env bash
# Run the universe panel to completion, resumably.
#
#   ops/panel_all_nights.sh            # start or resume (checkpoint)
#   Ctrl+C                             # stop cleanly; rerun to resume
#   FLE_RATE=6 FLE_WORKERS=2 ops/panel_all_nights.sh   # knobs
#
# What this script guarantees, each learned the hard way:
#   - it refuses to start while another panel is running (nine invisible
#     ghosts once hammered SEC all afternoon on stale code)
#   - the panel runs in the foreground, so Ctrl+C reaches it, and any exit
#     kills whatever panel is still alive
#   - output is unbuffered and mirrored to _staging/u-panel.log
# It no longer pauses for the prod nightly: a cold run is a one-time
# event and, once promoted, the nightly is the only run there is. If two
# ever do collide, the client's circuit breaker rests and resumes.
set -uo pipefail
cd "$(dirname "$0")/.."

if pgrep -f "fle.cli panel" >/dev/null; then
  echo "a panel is already running:"; pgrep -af "fle.cli panel"
  echo "stop it first:  pkill -f 'fle.cli panel'"; exit 1
fi
cleanup() { pkill -f "fle.cli panel" 2>/dev/null || true; }
trap 'echo; echo "== stopped by user; the checkpoint keeps all progress =="; cleanup; exit 130' INT
trap 'cleanup' EXIT

env PYTHONUNBUFFERED=1 FLE_RATE="${FLE_RATE:-4}" \
  python3 -m fle.cli panel \
    --universe universe/universe-2026-08-31.csv \
    --workers "${FLE_WORKERS:-4}" \
    --out _staging/u-panel.csv \
    --checkpoint _staging/u-panel.jsonl 2>&1 | tee -a _staging/u-panel.log
status=${PIPESTATUS[0]}
if [ "$status" -eq 0 ]; then
  echo "== panel finished =="
else
  echo "== panel exited with status $status; rerun to resume =="
fi
exit "$status"
