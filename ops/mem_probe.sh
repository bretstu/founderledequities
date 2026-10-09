#!/usr/bin/env bash
# WHERE THE NIGHTLY'S MEMORY GOES (2026-10-09). The full walk peaks at 6.3 GB
# on 2,135 companies, on a machine with 10 GB; the $200M universe is 3,000.
# Each stage is run on its own, against copies of last night's inputs and
# writing only under _staging/memprobe/, and the largest resident size any
# one of its processes reached is printed beside its wall time. Reads the
# cache; asks EDGAR only for feeds past the pipeline's own freshness window,
# as the nightly does. Nothing live is written. Half an hour or so.
#
#   ops/mem_probe.sh              # every stage
#   ops/mem_probe.sh history      # one stage
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
[ -x "$PY" ] || PY=python3
TIME=/usr/bin/time
[ -x "$TIME" ] || { echo "needs GNU time: sudo apt install time"; exit 1; }
P=_staging/memprobe
mkdir -p "$P"
U=$(ls universe/universe-????-??-??.csv | sort | tail -1)
ONLY="${1:-}"
want() { [ -z "$ONLY" ] || [ "$ONLY" = "$1" ]; }

# the finished checkpoint: tonight's if the nightly has run, else last night's
CK=_staging/panel.jsonl
[ -s "$CK" ] || CK=_staging/panel-prior.jsonl
cp "$CK" "$P/panel.jsonl"
[ -f history-state.json ] && cp history-state.json "$P/history-state.json" || true

LOG="$P/probe.log"; : > "$LOG"
printf "%-10s %10s %12s   %s\n" stage elapsed "peak RSS" "(the largest single process)"
run() {   # run <stage> <command...>: wall time and the max resident size
  local stage="$1"; shift
  local tf="$P/$stage.time"
  if "$TIME" -v -o "$tf" "$@" >> "$LOG" 2>&1; then :; else echo "  $stage: exit $? (see $LOG)"; fi
  local kb el
  kb=$(awk -F': ' '/Maximum resident set size/{print $2}' "$tf")
  el=$(awk -F'): ' '/Elapsed \(wall clock\)/{print $2}' "$tf")
  printf "%-10s %10s %9.2f GB\n" "$stage" "$el" "$(awk "BEGIN{print ${kb:-0}/1048576}")"
}

want panel   && run panel   "$PY" -m fle.cli panel   --universe "$U" --checkpoint "$P/panel.jsonl" --out "$P/panel.csv"
want history && run history "$PY" -m fle.cli history --universe "$U" --out "$P/history.csv" --reuse history.csv --state "$P/history-state.json" --splits --workers 2
want events  && run events  "$PY" -m fle.cli events  --panel panel.csv --history history.csv --out "$P/events.csv"
want perf    && run perf    "$PY" -m fle.cli perf    --panel panel.csv --out "$P/perf.csv"
SP=$(ls universe/sp500-????-??-??.csv | sort | tail -1)
want pages   && run pages   "$PY" ops/build_site_data.py panel.csv history.csv events.csv founders.csv "$SP" "$P/site-data/" --prices price-history
echo
echo "scaled to 3,000 companies, each stage's peak is about 1.4x the figure above; the box has 10 GB."
echo "details: $LOG and $P/*.time"
