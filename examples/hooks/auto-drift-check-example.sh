#!/usr/bin/env bash
# Example: Auto-trigger /interwatch:watch from a Claude Code Stop hook.
#
# This is a standalone example showing how to detect work signals
# and trigger Interwatch drift scanning. It does NOT depend on
# Clavain's lib-signals.sh — all signal detection is inline.
#
# This example uses a minimal signal set (3 signals). For the full
# reference of all possible signals (7 types), see Clavain's
# hooks/lib-signals.sh at:
#   https://github.com/interagency-marketplace/clavain/blob/main/hooks/lib-signals.sh
#
# To use this in your own plugin:
# 1. Copy this file to your plugin's hooks/ directory
# 2. Register it in your hooks.json under "Stop" event
# 3. Customize the signals and threshold below
#
# Hook JSON input (stdin):
#   { "session_id": "...", "transcript_path": "...", "stop_hook_active": false }
#
# Output (stdout):
#   { "decision": "block", "reason": "..." } — when drift check is warranted
#   (empty) — when no action needed
#
# Exit: always 0 (hooks must not fail)

set -euo pipefail

# --- CUSTOMIZABLE SETTINGS ---

# Minimum signal weight to trigger a drift check.
# Lower = more sensitive. commit(1) + bead-close(1) = 2.
THRESHOLD=2

# Throttle window in seconds (600 = 10 minutes).
THROTTLE_SECONDS=600

# Per-repo opt-out file. Create this file to disable drift checking.
OPT_OUT_FILE=".claude/no-driftcheck"

# --- END SETTINGS ---

# Guard: fail-open if jq is not available
if ! command -v jq &>/dev/null; then
    exit 0
fi

INPUT=$(cat)

# Guard: prevent infinite loop
STOP_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')
if [[ "$STOP_ACTIVE" == "true" ]]; then
    exit 0
fi

# Guard: per-repo opt-out
if [[ -f "$OPT_OUT_FILE" ]]; then
    exit 0
fi

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // "unknown"')

# Guard: throttle
# Use a unique prefix to avoid collision with other plugins.
THROTTLE_FILE="/tmp/yourplugin-drift-last-${SESSION_ID}"
if [[ -f "$THROTTLE_FILE" ]]; then
    MTIME=$(stat -c %Y "$THROTTLE_FILE" 2>/dev/null || stat -f %m "$THROTTLE_FILE" 2>/dev/null || date +%s)
    NOW=$(date +%s)
    if [[ $((NOW - MTIME)) -lt $THROTTLE_SECONDS ]]; then
        exit 0
    fi
fi

TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty')
if [[ -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]]; then
    exit 0
fi

RECENT=$(tail -80 "$TRANSCRIPT" 2>/dev/null || true)
if [[ -z "$RECENT" ]]; then
    exit 0
fi

# --- SIGNAL DETECTION (customize these patterns) ---

WEIGHT=0

# Git commit (weight 1)
if echo "$RECENT" | grep -q '"git commit'; then
    WEIGHT=$((WEIGHT + 1))
fi

# Bead/issue closed (weight 1)
if echo "$RECENT" | grep -q '"bd close'; then
    WEIGHT=$((WEIGHT + 1))
fi

# Version bump (weight 2)
if echo "$RECENT" | grep -q 'bump-version\|interpub:release'; then
    WEIGHT=$((WEIGHT + 2))
fi

# --- END SIGNAL DETECTION ---

if [[ "$WEIGHT" -lt "$THRESHOLD" ]]; then
    exit 0
fi

touch "$THROTTLE_FILE"

REASON="Shipped work detected (weight ${WEIGHT}). Run /interwatch:watch to check for documentation drift."
jq -n --arg reason "$REASON" '{"decision":"block","reason":$reason}'

exit 0
