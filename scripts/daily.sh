#!/usr/bin/env bash
# Writes a digest with Claude Code, commits and pushes it.
#   scripts/daily.sh [--once] [YYYY-MM-DD]
# --once (the systemd timer) does nothing when today already has a digest; by hand, with
# `mise run veille`, every run writes a new one. A date collects the items since that day.
set -euo pipefail
cd "$(dirname "$0")/.."

once=false
if [[ "${1:-}" == "--once" ]]; then
    once=true
    shift
fi
since="${1:-}"

if $once && compgen -G "digests/$(date +%F)*.md" >/dev/null; then
    echo "today already has a digest"
    exit 0
fi

# Permissions come from .claude/settings.json, so the run never waits for a prompt.
claude -p "/veille --unattended $since"

# The fetcher names the file after the time of the run: the new digest is the untracked one.
digest=$(git ls-files --others --exclude-standard -- 'digests/*.md' | tail -n 1)
if [[ -z "$digest" ]]; then
    echo "Claude did not write a digest" >&2
    exit 1
fi

exec scripts/keep.sh "$digest"
