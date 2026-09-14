#!/usr/bin/env bash
# The Monday tape, sent by a person (PLAN.md 5a). The pipeline drafted it;
# this sends what the markdown says now.
#
#   ops/send-tape.sh 2026-09-21 --test            # to LETTER_TEST_TO (.env), nobody else
#   ops/send-tape.sh 2026-09-21 --test --to me@x  # to one address
#   ops/send-tape.sh 2026-09-21 --send            # a broadcast draft in Resend; review and press Send there
#   ops/send-tape.sh 2026-09-21 --send --confirm  # the broadcast, sent from here
#
# Re-renders from weekly/letter-<date>.md first, so an edit is always what
# goes out; refuses a list send without POSTAL_ADDRESS in .env.
set -euo pipefail
cd "$(dirname "$0")/.."
date="${1:?date, e.g. 2026-09-21}"; shift
python3 ops/letter.py render "$date"
python3 ops/letter.py send "$date" "$@"
