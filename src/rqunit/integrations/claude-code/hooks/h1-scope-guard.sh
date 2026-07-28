#!/usr/bin/env bash
# H1 pre-write guard (RU framework §10.3, TASK-060). Inert unless an active
# task packet exists (spec/packets/.active) — zero cost during non-RU work.
# Exit 2 = block the tool call (PreToolUse contract). Missing uv never bricks
# editing (plan D-P5.4).
set -uo pipefail
root="${CLAUDE_PROJECT_DIR:-.}"
[ -f "$root/spec/packets/.active" ] || exit 0
command -v uv >/dev/null 2>&1 || exit 0
f=$(jq -r '.tool_input.file_path // empty')
[ -n "$f" ] || exit 0
if ! out=$(rqunit hooks h1 --path "$f" 2>&1); then
  echo "$out" >&2
  exit 2
fi
exit 0
