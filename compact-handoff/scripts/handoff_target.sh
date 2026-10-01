#!/usr/bin/env bash

set -uo pipefail

HANDOFF_DIR="/tmp/claude-handoffs"

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SLUG="${1:-}"
DATE="${2:-}"
TITLE="${3:-}"

if [[ -z "$DATE" ]]; then
  DATE=$(date +%Y-%m-%d)
fi

DERIVED=$(python3 "$SELF_DIR/next_title.py" --cwd "$(pwd)" 2>/dev/null)
CURRENT_TITLE=$(sed -n 's/^CURRENT_TITLE=//p' <<<"$DERIVED")
NEXT_TITLE=$(sed -n 's/^NEXT_TITLE=//p' <<<"$DERIVED")
NEXT_SLUG=$(sed -n 's/^NEXT_SLUG=//p' <<<"$DERIVED")
PARENT_HANDOFF=$(sed -n 's/^PARENT_HANDOFF=//p' <<<"$DERIVED")

[[ -z "$SLUG" ]] && SLUG="${NEXT_SLUG:-handoff}"
[[ -z "$TITLE" ]] && TITLE="${NEXT_TITLE:-Handoff}"

# CLONE is optional provenance metadata for multi-instance setups (several Claude
# Code installs running side by side, each in its own window). A normal single
# install has no clone, so this is best-effort and nothing downstream depends on
# it: set COMPACT_HANDOFF_CLONE yourself if you run multiple instances and want it
# recorded, otherwise it stays empty.
CLONE="${COMPACT_HANDOFF_CLONE:-}"

mkdir -p "$HANDOFF_DIR"

HANDOFF_PATH="$HANDOFF_DIR/${DATE}-${SLUG}.md"

echo "HANDOFF_PATH=$HANDOFF_PATH"
echo "HANDOFF_DIR=$HANDOFF_DIR"
echo "CLONE=${CLONE:-none}"
echo "SESSION_ID=${CLAUDE_CODE_SESSION_ID:-unknown}"
echo "HOST_SESSION_ID=${CLAUDE_CODE_HOST_SESSION_ID:-unknown}"
echo "CWD=$(pwd)"
echo "CURRENT_TITLE=${CURRENT_TITLE:-unknown}"
echo "NEXT_TITLE=$TITLE"
echo "PARENT_HANDOFF=${PARENT_HANDOFF:-none}"
echo "---"
echo "Open a new Claude Code session named \"$TITLE\" and send it this as the first message:"
echo "Read $HANDOFF_PATH then continue from the Optional Next Step section."
