#!/bin/bash
set -euo pipefail

SRC="${SKILL_BOARD_SKILLS_DIR:-$HOME/ai-workspace/shared-skills}"
DIST="${SKILL_BOARD_SYNC_DIR:-$HOME/Library/Mobile Documents/com~apple~CloudDocs/ai-skills}"

if [ ! -d "$SRC" ]; then
  echo "skills directory does not exist: $SRC"
  exit 1
fi

mkdir -p "$DIST"
rsync -rL --delete \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude '__pycache__' \
  --exclude '.DS_Store' \
  "$SRC/" "$DIST/"

count=$(find "$DIST" -name SKILL.md | wc -l | tr -d ' ')
echo "$count skills synced to $DIST"
