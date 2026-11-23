#!/usr/bin/env bash
# Commits one digest and pushes it: the end of every run, by the timer or by hand.
#   scripts/keep.sh digests/<name>.md
set -euo pipefail
cd "$(dirname "$0")/.."

digest="${1:-}"
# /veille may call this without a prompt (.claude/settings.json): commit nothing but a digest.
if [[ ! "$digest" =~ ^digests/[0-9A-Za-z-]+\.md$ || ! -f "$digest" ]]; then
    echo "usage: scripts/keep.sh digests/<name>.md (an existing digest)" >&2
    exit 2
fi

git add -- "$digest"
git commit -q -m "📰 docs(digest): add digest of $(basename "$digest" .md)" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
# Offline: the push fails but the commit stays, and the next run pushes both.
git push -q
echo "$digest committed and pushed"
