#!/usr/bin/env bash
# LOCAL PREVIEW (2026-09-29). Assembles public/ exactly as ops/deploy.sh does,
# stops before wrangler, and serves it on localhost. Nothing leaves the machine.
#
#   ops/preview.sh          build (FLE_QUICK=1: no price step) and serve on :8111
#   ops/preview.sh build    build only
#   PORT=8112 ops/preview.sh
#   FLE_QUICK=0 ops/preview.sh   a full build with prices, as the nightly runs it
set -euo pipefail
cd "$(dirname "$0")/.."
export FLE_QUICK="${FLE_QUICK:-1}"
# the assemble half of deploy.sh, run in place so its relative paths hold
sed '/^wrangler pages deploy/,$d' ops/deploy.sh > ops/.assemble-preview.sh
trap 'rm -f ops/.assemble-preview.sh' EXIT
bash ops/.assemble-preview.sh
[ "${1:-}" = "build" ] && exit 0
PORT="${PORT:-8111}"
echo "  preview: http://localhost:$PORT/  (Ctrl+C stops it; hard-refresh after a rebuild)"
exec python3 -m http.server "$PORT" -d public
