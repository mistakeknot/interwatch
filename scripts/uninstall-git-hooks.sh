#!/usr/bin/env bash
# uninstall-git-hooks.sh — remove interwatch managed blocks from git hooks
#
# Idempotent. If the hook file becomes empty (only shebang) after removal,
# it is deleted. Other hook content is preserved.
#
# Usage: bash uninstall-git-hooks.sh [--repo <path>]

set -euo pipefail

SENTINEL_BEGIN='# >>> interwatch managed block — do not edit manually'
SENTINEL_END='# <<< interwatch managed block'

REPO_ROOT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO_ROOT="$2"; shift 2 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$REPO_ROOT" ]]; then
  REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
fi
if [[ -z "$REPO_ROOT" || ! -d "$REPO_ROOT/.git" ]]; then
  echo "error: not a git repository" >&2
  exit 1
fi

# Respect core.hooksPath if set (must match installer behavior).
CONFIGURED_HOOKS_PATH="$(git -C "$REPO_ROOT" config --get core.hooksPath 2>/dev/null || true)"
if [[ -n "$CONFIGURED_HOOKS_PATH" ]]; then
  if [[ "$CONFIGURED_HOOKS_PATH" = /* ]]; then
    HOOKS_DIR="$CONFIGURED_HOOKS_PATH"
  else
    HOOKS_DIR="$REPO_ROOT/$CONFIGURED_HOOKS_PATH"
  fi
else
  HOOKS_DIR="$REPO_ROOT/.git/hooks"
fi

remove_block() {
  local hook_path="$1"
  [[ -f "$hook_path" ]] || return 0
  grep -qF "$SENTINEL_BEGIN" "$hook_path" || return 0

  local cleaned
  cleaned="$(awk -v begin="$SENTINEL_BEGIN" -v end="$SENTINEL_END" '
    $0 == begin { in_block=1; next }
    in_block && $0 == end { in_block=0; next }
    !in_block { print }
  ' "$hook_path")"

  # Strip trailing blank lines.
  cleaned="$(printf '%s\n' "$cleaned" | awk 'NF{found=1} found{buf = buf $0 ORS} END{ sub(/\n+$/, "", buf); print buf }')"

  # If only a shebang or empty, remove the file.
  # `grep -v` returns 1 when nothing matches; with pipefail that kills the
  # script. Capture exit status via `|| true` and let wc count zero.
  local non_shebang_lines
  non_shebang_lines="$(printf '%s\n' "$cleaned" | { grep -vE '^(#!.*|[[:space:]]*)$' || true; } | wc -l)"
  if [[ "$non_shebang_lines" -eq 0 ]]; then
    rm -f "$hook_path"
    echo "✓ removed $(basename "$hook_path") (empty after cleanup)"
  else
    printf '%s\n' "$cleaned" > "$hook_path"
    chmod +x "$hook_path"
    echo "✓ cleaned $(basename "$hook_path")"
  fi
}

remove_block "$HOOKS_DIR/post-commit"
remove_block "$HOOKS_DIR/post-merge"
echo "interwatch hooks uninstalled."
