# interwatch

> See `AGENTS.md` for full development guide.

## Overview

Doc freshness and correctness monitoring — 1 skill, 4 commands, 0 agents, 0 hooks (library only), 0 MCP servers. Companion plugin for Clavain. Auto-discovers watchable docs by convention, detects drift via 17 signal types, dispatches to generators for refresh, and runs stranger-perspective correctness audits with cross-document consistency checking against project reality.

## Quick Commands

```bash
# Test locally
claude --plugin-dir /root/projects/Interverse/plugins/interwatch

# Validate structure
ls skills/*/SKILL.md | wc -l          # Should be 1
ls commands/*.md | wc -l              # Should be 4
bash -n scripts/interwatch.sh         # Syntax check
bash -n hooks/lib-watch.sh            # Syntax check
python3 -c "import json; json.load(open('.claude-plugin/plugin.json'))"  # Manifest check

# Auto-discovery
python3 scripts/interwatch-scan.py --discover-only    # Write .interwatch/watchables.yaml
python3 scripts/interwatch-scan.py --discover --save-state  # Discover + scan
python3 scripts/interwatch-scan.py --rediscover       # Force re-detection

# Correctness audit
python3 scripts/interwatch-audit.py                   # Gather ground truth for all eligible docs
python3 scripts/interwatch-audit.py --check README.md # Single doc
python3 scripts/interwatch-audit.py --gather-only     # Print ground truth JSON only
```

## Design Decisions (Do Not Re-Ask)

- Namespace: `interwatch:` (companion to Clavain)
- Watchables registry in `config/watchables.yaml` — declarative, not code
- Confidence tiers: Certain (auto-fix), High (auto-fix+note), Medium (suggest), Low (report)
- State tracked in `.interwatch/` (per-project, gitignored)
- Generator-agnostic — calls interpath for product docs, interdoc for code docs
- No hooks — drift detection is on-demand, not event-driven
- Auto-discovery via `--discover` — convention-based, generates `.interwatch/watchables.yaml`
- 17 signal types with threshold-based dispatch table (including bead_reference_stale, bead_count_mismatch)
- Correctness audit is agent-dispatched (expensive), separate from signal-based scoring (cheap)
- Audit gathers ground truth (counts, files, versions, cross-doc consistency) then dispatches sonnet agent for verification
- Cross-document consistency: audit auto-discovers related doc groups (vision+roadmap) and detects P0 set and count mismatches
- Freshness (scan) and correctness (audit) are complementary: fresh docs can be wrong, stale docs can be correct
