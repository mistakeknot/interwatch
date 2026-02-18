# interwatch

Documentation freshness monitoring for Claude Code.

## What This Does

Documentation drifts. You ship a feature, update the code, and three weeks later someone discovers that the architecture section of AGENTS.md still describes the old design. interwatch solves this by maintaining a registry of watched documents, detecting drift signals (beads closed, files renamed, versions bumped), and scoring confidence on whether a refresh is needed.

When drift is detected, interwatch acts based on confidence:

- **Certain/High** — auto-refreshes the document (deterministic signals, unlikely to be wrong)
- **Medium** — suggests a refresh (might be intentional drift, you decide)
- **Low** — reports only (could be noise)

It delegates the actual regeneration to the right tool: interpath for product artifacts (roadmaps, PRDs), interdoc for code documentation. interwatch knows *what's* stale; the generators know how to fix it.

## Installation

```bash
/plugin install interwatch
```

Companion plugin for [Clavain](https://github.com/mistakeknot/Clavain).

## Usage

Run a drift scan:

```
/interwatch:watch
```

Check current health without re-scanning:

```
/interwatch:status
```

Force a specific document refresh regardless of drift score:

```
/interwatch:refresh
```

## How It Works

Each watched document is registered in `config/watchables.yaml` with:
- A path (where the doc lives)
- A generator (which plugin regenerates it)
- Signals (events that cause drift)
- A staleness threshold (days before it's considered stale)

State is tracked in `.interwatch/` (per-project, gitignored). No hooks — drift detection is on-demand, not event-driven.

## License

MIT
