#!/usr/bin/env bash
# WHO CAME: ops/hits.py, which reads the window once (2026-10-20) and
# prints the same report this script always printed. The database is
# fle-hits (ops/hits-schema.sql); FLE_HITS_DB overrides it.
#
#   ops/hits.sh                        # the last 7 days
#   ops/hits.sh today | yesterday | 30 | 2026-10-10 | 2026-10-06..2026-10-10
#   ops/hits.sh visitors [window]      # one row per visitor, then each reader's journey
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 ops/hits.py "$@"
