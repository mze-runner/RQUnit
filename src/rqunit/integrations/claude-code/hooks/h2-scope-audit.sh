#!/usr/bin/env bash
# H2 post-write auditor (RU framework §10.3, TASK-061). Non-blocking by spec:
# appends out-of-owns writes to spec/projections/scope-audit.jsonl and always
# exits 0. Inert unless an active task packet exists.
set -uo pipefail
root="${CLAUDE_PROJECT_DIR:-.}"
[ -f "$root/spec/packets/.active" ] || exit 0
command -v uv >/dev/null 2>&1 || exit 0
f=$(jq -r '.tool_input.file_path // empty')
[ -n "$f" ] || exit 0
(rqunit hooks h2 --path "$f") || true
exit 0
