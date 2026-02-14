# Interwatch

Doc freshness monitoring for Claude Code — detects drift between project state and documentation, scores confidence, and orchestrates refresh via generator plugins (Interpath for product docs, Interdoc for code docs).

Companion plugin for [Clavain](https://github.com/mistakeknot/Clavain).

## Install

```bash
claude plugin install interwatch@interagency-marketplace
```

## Commands

| Command | Description |
|---------|-------------|
| `/interwatch:watch` | Run drift scan across all watched docs |
| `/interwatch:status` | Show current drift health scores |
| `/interwatch:refresh` | Force regeneration of a specific doc |

## How It Works

Interwatch maintains a registry of **watchables** — documents that can be monitored for drift. Each watchable has:

- A **path** (where the doc lives)
- A **generator** (which plugin regenerates it)
- **Signals** (events that cause drift: beads closed, files renamed, version bumped)
- **Staleness threshold** (days before a doc is considered stale)

When drift is detected, Interwatch scores confidence and either:
- **Auto-refreshes** (Certain/High confidence — deterministic signals)
- **Suggests refresh** (Medium confidence — may be intentional)
- **Reports only** (Low confidence — possibly noise)

## License

MIT
