#!/usr/bin/env bash
# Measure the history walk's peak memory on a cold chunk of companies.
#
# Run this in a checkout that has a real cache (copy prod's .cache into
# the dev checkout, or run in prod on a throwaway --out). --reuse is left
# OFF so every company is actually walked; the number to read is
# "Maximum resident set size" at the end, in kilobytes.
#
#   ops/memcheck.sh 60 1      # 60 companies, one worker  (the old shape)
#   ops/memcheck.sh 60 2      # 60 companies, two workers (the new shape)
#
# Before the fix the single-worker number climbs with the chunk size and
# does not come back; after it, the total is bounded by one worker's
# high-water mark times the worker count, whatever the chunk size.
set -euo pipefail
cd "$(dirname "$0")/.."
N="${1:-60}"; W="${2:-2}"
UNI="${3:-universe/sp500-2026-08-25.csv}"
/usr/bin/time -v python3 -m fle.cli history --universe "$UNI" --limit "$N" \
  --splits --workers "$W" --out "_staging/memcheck-history.csv" 2>&1 \
  | grep -E "snapshots across|Maximum resident|Elapsed \(wall" 
