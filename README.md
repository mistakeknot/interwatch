# interwatch

Doc freshness monitoring for Claude Code — detects drift between project state and documentation, scores confidence, and orchestrates refresh via generator plugins (interpath for product docs, interdoc for code docs).

Companion plugin for [Clavain](https://github.com/mistakeknot/Clavain).

## Install

```bash
claude plugin install interwatch@interagency-marketplace
```

## Commands

| Command | Description |
|---------|-------------|
| `/interwatch:watch` | Run drift scan across all watched docs |
| `/interwatch:interwatch-status` | Show current drift health scores |
| `/interwatch:refresh` | Force regeneration of a specific doc |

## How It Works

interwatch maintains a registry of **watchables** — documents that can be monitored for drift. Each watchable has:

- A **path** (where the doc lives)
- A **generator** (which plugin regenerates it)
- **Signals** (events that cause drift: beads closed, files renamed, version bumped)
- **Staleness threshold** (days before a doc is considered stale)

When drift is detected, interwatch scores confidence and either:
- **Auto-refreshes** (Certain/High confidence — deterministic signals)
- **Suggests refresh** (Medium confidence — may be intentional)
- **Reports only** (Low confidence — possibly noise)

## Hook Integration

interwatch can be auto-triggered from a Claude Code Stop hook when shipped work is detected. See `examples/hooks/auto-drift-check-example.sh` for a standalone example.

The example hook:
- Detects work signals (git commits, bead closures, version bumps) in the conversation transcript
- Uses weighted signal detection with a configurable threshold
- Outputs a `block` decision telling Claude to run `/interwatch:watch`
- Includes throttling and opt-out guards

To use it, copy the script to your plugin's `hooks/` directory and register it in `hooks.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/auto-drift-check-example.sh",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

## License

MIT
