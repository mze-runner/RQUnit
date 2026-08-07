#!/usr/bin/env bash
# H1 pre-write guard (RU framework §10.3). Inert unless an active task packet
# exists (spec/packets/.active) — zero cost during non-RU work. Exit 2 blocks
# the tool call, per the PreToolUse protocol.
#
# Fails OPEN: a missing tool exits 0. A scope guard that bricks every edit when
# the CLI is absent teaches people to remove the guard, which costs more than
# the writes it would have caught.
set -uo pipefail
root="${CLAUDE_PROJECT_DIR:-.}"
[ -f "$root/spec/packets/.active" ] || exit 0
command -v rqunit >/dev/null 2>&1 || exit 0
command -v jq >/dev/null 2>&1 || exit 0
f=$(jq -r '.tool_input.file_path // empty')
[ -n "$f" ] || exit 0
if ! out=$(rqunit hooks h1 --path "$f" 2>&1); then
  echo "$out" >&2
  exit 2
fi
exit 0
