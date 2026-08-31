#!/usr/bin/env bash
# Publish this checkout to a PREVIEW URL, never the domain.
# Cloudflare Pages aliases founderledequities.com to the production branch
# only; a deploy on any other branch is a full working copy -- Functions,
# sign-in and payments included -- at https://<branch>.founderledequities.pages.dev
# Run from the dev checkout to look at expansion work on a real host.
set -euo pipefail
BRANCH="${1:-dev}"
if [ "$BRANCH" = "production" ]; then
  echo "refusing: production deploys go through ops/deploy.sh" >&2; exit 1
fi
FLE_BRANCH="$BRANCH" exec "$(dirname "$0")/deploy.sh"
