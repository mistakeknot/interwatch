#!/usr/bin/env bash
# hook-runner.sh — invoked by git post-commit/post-merge hooks via setsid.
#
# Runs interwatch-scan.py --save-state with a 5s timeout. Logs failures
# (with exit code and first line of error) to .interwatch/hook.log. Silent
# on success. Designed to be detached from git's process group so it
# survives git's exit.
#
# Usage: hook-runner.sh <hook-name>
#   hook-name: "post-commit", "post-merge", etc. (used in log entries)

set +e  # never exit non-zero — this is a fire-and-forget runner

HOOK_NAME="${1:-unknown}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAN_SCRIPT="${SCRIPT_DIR}/interwatch-scan.py"

# Already cwd'd by the calling hook to repo root; .interwatch/ already exists.

output=$(timeout 5s python3 "$SCAN_SCRIPT" --save-state 2>&1)
rc=$?

if [[ $rc -ne 0 ]]; then
  ts=$(date -Iseconds)
  first_err=$(printf '%s' "$output" | head -1)
  printf '[%s] interwatch hook (%s) exit=%d: %s\n' "$ts" "$HOOK_NAME" "$rc" "$first_err" >> .interwatch/hook.log
fi

exit 0
