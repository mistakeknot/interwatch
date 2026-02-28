# interwatch

> See `AGENTS.md` for full development guide.

## Overview

Doc freshness monitoring — 1 skill, 3 commands, 0 agents, 0 hooks (library only), 0 MCP servers. Companion plugin for Clavain. Auto-discovers watchable docs by convention, detects drift via 14 signal types, and dispatches to generators for refresh.

## Quick Commands

```bash
# Test locally
claude --plugin-dir /root/projects/Interverse/plugins/interwatch

# Validate structure
ls skills/*/SKILL.md | wc -l          # Should be 1
ls commands/*.md | wc -l              # Should be 3
bash -n scripts/interwatch.sh         # Syntax check
bash -n hooks/lib-watch.sh            # Syntax check
python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))"  # Manifest check

# Auto-discovery
python3 scripts/interwatch-scan.py --discover-only    # Write .interwatch/watchables.yaml
python3 scripts/interwatch-scan.py --discover --save-state  # Discover + scan
python3 scripts/interwatch-scan.py --rediscover       # Force re-detection
```

## Design Decisions (Do Not Re-Ask)

- Namespace: `interwatch:` (companion to Clavain)
- Watchables registry in `config/watchables.yaml` — declarative, not code
- Confidence tiers: Certain (auto-fix), High (auto-fix+note), Medium (suggest), Low (report)
- State tracked in `.interwatch/` (per-project, gitignored)
- Generator-agnostic — calls interpath for product docs, interdoc for code docs
- No hooks — drift detection is on-demand, not event-driven
- Auto-discovery via `--discover` — convention-based, generates `.interwatch/watchables.yaml`
- 14 signal types with threshold-based dispatch table
