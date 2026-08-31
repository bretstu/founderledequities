#!/usr/bin/env bash
# Run the universe panel to completion, automatically pausing around the
# prod nightly (02:31). The panel's checkpoint makes stopping free, so
# this simply: runs until 01:55, kills the run, sleeps until 03:45,
# resumes -- as many nights as it takes. Start it in tmux and forget it.
#
#   tmux new -s universe
#   ops/panel_all_nights.sh
#   (Ctrl+B, D to detach)
set -uo pipefail
cd "$(dirname "$0")/.."

# YOUR Ctrl+C exits the wrapper; only the 01:55 TIMER pauses-and-resumes.
# (The first version could not tell the two apart and answered a user's
# interrupt by going to sleep until 03:45.)
trap 'echo; echo "== stopped by user; the checkpoint keeps all progress =="; exit 130' INT

CMD=(env PYTHONUNBUFFERED=1 FLE_RATE="${FLE_RATE:-4}" python3 -m fle.cli panel
     --universe universe/universe-2026-08-31.csv --workers 4
     --out _staging/u-panel.csv --checkpoint _staging/u-panel.jsonl)

secs_until() {  # HH:MM today, or tomorrow if already past
  local target now
  target=$(date -d "today $1" +%s); now=$(date +%s)
  if [ "$target" -le "$now" ]; then target=$(date -d "tomorrow $1" +%s); fi
  echo $(( target - now ))
}

while true; do
  budget=$(secs_until 01:55)
  # if we are inside the quiet window (01:55-03:45), sleep it out first
  if [ "$budget" -gt $(( 22 * 3600 )) ]; then
    naptime=$(secs_until 03:45)
    echo "== quiet hours: sleeping $(( naptime / 60 )) min until 03:45 =="
    sleep "$naptime"
    continue
  fi
  echo "== running until 01:55 ($(( budget / 60 )) min budget) =="
  timeout --signal=INT "$budget" "${CMD[@]}" 2>&1 | tee -a _staging/u-panel.log
  status=${PIPESTATUS[0]}
  if [ "$status" -eq 0 ]; then
    echo "== panel finished =="
    break
  fi
  if [ "$status" -ne 124 ]; then
    # not the timer (124 = timeout fired): a crash or something unexpected.
    # Do not silently sleep on it -- say so and stop.
    echo "== panel exited with status $status; see _staging/u-panel.log =="
    exit "$status"
  fi
  naptime=$(secs_until 03:45)
  echo "== paused for the nightly: sleeping $(( naptime / 60 )) min =="
  sleep "$naptime"
done
