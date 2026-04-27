#!/usr/bin/env bash
# pretool-doc-access.sh — PreToolUse hook entry point.
#
# Thin wrapper that exec's pretool_doc_access.py with the stdin payload
# already in the agent's working directory. Exits 0 on any setup failure
# (fail-open). The Python implementation is the authoritative logic and
# does its own error suppression.
#
# Matches Read|Edit|Write|MultiEdit. Output is one of:
# - empty / exit 0 (silent — Green/Low or unknown file)
# - {"hookSpecificOutput": {"additionalContext": "..."}} (advisory)

set +e

# Fail-open if python3 is missing.
command -v python3 >/dev/null 2>&1 || exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PY="${SCRIPT_DIR}/pretool_doc_access.py"

[[ -f "$PY" ]] || exit 0

exec python3 "$PY"
