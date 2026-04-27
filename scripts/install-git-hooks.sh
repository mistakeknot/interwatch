#!/usr/bin/env bash
# install-git-hooks.sh — wire git post-commit/post-merge to interwatch-scan
#
# Idempotent installer. Detects existing managed block via sentinel comments
# and rewrites it. Preserves any other hook content above/below the sentinel.
# Hook body runs interwatch-scan.py --save-state in the background, swallows
# errors, and never blocks the commit.
#
# Usage: bash install-git-hooks.sh [--repo <path>] [--dry-run]

set -euo pipefail

SENTINEL_BEGIN='# >>> interwatch managed block — do not edit manually'
SENTINEL_END='# <<< interwatch managed block'
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAN_SCRIPT="${SCRIPT_DIR}/interwatch-scan.py"
RUNNER_SCRIPT="${SCRIPT_DIR}/hook-runner.sh"

REPO_ROOT=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO_ROOT="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$REPO_ROOT" ]]; then
  REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
fi
if [[ -z "$REPO_ROOT" || ! -d "$REPO_ROOT/.git" ]]; then
  echo "error: not a git repository (use --repo or run from inside one)" >&2
  exit 1
fi

if [[ ! -f "$SCAN_SCRIPT" ]]; then
  echo "error: interwatch-scan.py not found at $SCAN_SCRIPT" >&2
  exit 1
fi
if [[ ! -f "$RUNNER_SCRIPT" ]]; then
  echo "error: hook-runner.sh not found at $RUNNER_SCRIPT" >&2
  exit 1
fi

# Respect core.hooksPath if set (e.g., bd configures this to .beads/hooks).
# Fall back to .git/hooks otherwise.
CONFIGURED_HOOKS_PATH="$(git -C "$REPO_ROOT" config --get core.hooksPath 2>/dev/null || true)"
if [[ -n "$CONFIGURED_HOOKS_PATH" ]]; then
  if [[ "$CONFIGURED_HOOKS_PATH" = /* ]]; then
    HOOKS_DIR="$CONFIGURED_HOOKS_PATH"
  else
    HOOKS_DIR="$REPO_ROOT/$CONFIGURED_HOOKS_PATH"
  fi
  echo "note: respecting core.hooksPath = $CONFIGURED_HOOKS_PATH"
else
  HOOKS_DIR="$REPO_ROOT/.git/hooks"
fi
mkdir -p "$HOOKS_DIR"

hook_body() {
  cat <<EOF
$SENTINEL_BEGIN
# Refreshes .interwatch/drift.json after $1. Detached background process,
# non-blocking; errors logged to .interwatch/hook.log.
#
# Hook body uses portable path resolution (no hardcoded machine paths)
# because in some setups (e.g., bd's core.hooksPath = .beads/hooks) the
# hook file is tracked in git and shared across developers.
#
# Resolution order: \$INTERWATCH_HOOK_RUNNER, repo-relative
# interverse/interwatch/scripts/hook-runner.sh, plugin cache. If none
# found, silently skip (interwatch may not be installed on this machine).
#
# setsid escapes git's process group — \`&\` + \`disown\` alone is
# insufficient because git SIGHUPs its process group on exit, killing the
# background scan before it completes.
(
  cd "\$(git rev-parse --show-toplevel)" || exit 0
  mkdir -p .interwatch
  runner=""
  for candidate in \\
      "\${INTERWATCH_HOOK_RUNNER:-}" \\
      "\$(pwd)/interverse/interwatch/scripts/hook-runner.sh" \\
      "\$HOME/.claude/plugins/cache/interwatch/scripts/hook-runner.sh"; do
    if [[ -n "\$candidate" && -x "\$candidate" ]]; then
      runner="\$candidate"; break
    fi
  done
  if [[ -z "\$runner" ]]; then exit 0; fi
  setsid bash "\$runner" "$1" </dev/null >/dev/null 2>&1 &
) || true
$SENTINEL_END
EOF
}

install_hook() {
  local hook_name="$1"
  local hook_path="$HOOKS_DIR/$hook_name"
  local body
  body="$(hook_body "$hook_name")"

  local new_content
  if [[ -f "$hook_path" ]]; then
    if grep -qF "$SENTINEL_BEGIN" "$hook_path"; then
      # Replace existing managed block in-place.
      new_content="$(awk -v begin="$SENTINEL_BEGIN" -v end="$SENTINEL_END" -v body="$body" '
        $0 == begin { print body; in_block=1; next }
        in_block && $0 == end { in_block=0; next }
        !in_block { print }
      ' "$hook_path")"
    else
      # Prepend managed block after the shebang, preserving existing hook
      # content. Prepending (not appending) ensures the block runs even when
      # the existing hook ends with `exec ...` (e.g., bd's hook shim).
      # The block spawns in background and returns immediately, so the
      # existing hook still executes normally after it.
      local existing
      existing="$(cat "$hook_path")"
      if [[ "$existing" == '#!'* ]]; then
        local shebang rest
        shebang="$(printf '%s\n' "$existing" | head -1)"
        rest="$(printf '%s\n' "$existing" | tail -n +2)"
        new_content="$shebang"$'\n'"$body"$'\n'"$rest"
      else
        new_content="#!/usr/bin/env bash"$'\n'"$body"$'\n'"$existing"
      fi
    fi
  else
    new_content="#!/usr/bin/env bash"$'\n'"$body"
  fi

  if [[ $DRY_RUN -eq 1 ]]; then
    echo "--- would write $hook_path ---"
    printf '%s\n' "$new_content"
    return
  fi

  printf '%s\n' "$new_content" > "$hook_path"
  chmod +x "$hook_path"
  echo "✓ installed $hook_name → $hook_path"
}

install_hook post-commit
install_hook post-merge

if [[ $DRY_RUN -eq 0 ]]; then
  echo
  echo "interwatch hooks installed. Drift state will refresh on every commit and merge."
  echo "Logs: $REPO_ROOT/.interwatch/hook.log"
  echo "Uninstall: bash ${SCRIPT_DIR}/uninstall-git-hooks.sh"
fi
