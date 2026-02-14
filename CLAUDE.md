# Interwatch

> See `AGENTS.md` for full development guide.

## Overview

Doc freshness monitoring — 1 skill, 3 commands, 0 agents, 0 hooks (library only), 0 MCP servers. Companion plugin for Clavain. Detects drift between project state and documentation using signal-based scoring.

## Quick Commands

```bash
# Test locally
claude --plugin-dir /root/projects/interwatch

# Validate structure
ls skills/*/SKILL.md | wc -l          # Should be 1
ls commands/*.md | wc -l              # Should be 3
bash -n scripts/interwatch.sh         # Syntax check
bash -n hooks/lib-watch.sh            # Syntax check
python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))"  # Manifest check
```

## Design Decisions (Do Not Re-Ask)

- Namespace: `interwatch:` (companion to Clavain)
- Watchables registry in `config/watchables.yaml` — declarative, not code
- Confidence tiers: Certain (auto-fix), High (auto-fix+note), Medium (suggest), Low (report)
- State tracked in `.interwatch/` (per-project, gitignored)
- Generator-agnostic — calls Interpath for product docs, Interdoc for code docs
- No hooks — drift detection is on-demand, not event-driven
