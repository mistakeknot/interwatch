---
name: install-hooks
description: Install git post-commit/post-merge hooks that auto-refresh interwatch drift state on every commit and merge
---

# Install Git Hooks

Wires git lifecycle events to keep `.interwatch/drift.json` always-fresh-as-of-HEAD without scheduled cadence or LLM cost. Pure-Python scan runs in the background after each commit/merge.

## What it does

1. Installs (or updates) `.git/hooks/post-commit` and `.git/hooks/post-merge`.
2. Hook body runs `interwatch-scan.py --save-state` in the background, with a 5-second timeout.
3. Errors are logged to `.interwatch/hook.log` — never blocks the commit.
4. Idempotent: re-running the command updates the managed block in place. Other hook content (husky, lefthook, custom hooks) is preserved.

## Algorithm

Locate the installer script relative to the interwatch plugin install path:

```bash
INSTALLER="$(find ~/.claude ~/.local/share/claude /home/mk/projects/Sylveste/interverse/interwatch -name install-git-hooks.sh -path '*/interwatch/scripts/*' 2>/dev/null | head -1)"
if [[ -z "$INSTALLER" ]]; then
  echo "error: install-git-hooks.sh not found — is interwatch installed?"
  exit 1
fi
bash "$INSTALLER"
```

Then verify by reading `.git/hooks/post-commit` and `.git/hooks/post-merge` and confirming the `interwatch managed block` sentinel is present.

## Reporting

After install, report:
- Both hooks installed (or updated)
- Path to `.interwatch/hook.log` for diagnostics
- Reminder that uninstall is `bash interverse/interwatch/scripts/uninstall-git-hooks.sh`

## Notes

- This is opt-in per project. Do not auto-install on session start.
- Hooks coexist with husky, lefthook, pre-commit, and any custom hooks — interwatch's content lives inside a sentinel-bracketed managed block.
- If `.interwatch/` does not yet exist, the hook will create it on first run.
