# Watchables Reference

A **watchable** is a document registered for drift monitoring. Each watchable has:

## Schema

```yaml
watchables:
  - name: string          # Unique identifier
    path: string          # Relative path to the document
    generator: string     # Skill to invoke for regeneration
    generator_args: map   # Arguments passed to the generator
    signals:              # List of drift signals to monitor
      - type: string      # Signal type (from signals.md catalog)
        weight: int       # How much this signal contributes to drift score
        description: str  # Human-readable explanation
        threshold: int    # Optional: minimum count before signal fires
    staleness_days: int   # Days before doc is considered stale
```

## Generator Mapping

| Generator | Plugin | Produces |
|-----------|--------|----------|
| `interpath:artifact-gen` | interpath | Roadmap, PRD, Vision, Changelog, Status |
| `interdoc:interdoc` | interdoc | AGENTS.md, CLAUDE.md |

## Built-in Watchables

The default `config/watchables.yaml` ships with entries for common docs. Projects can customize by editing the config file.

## Discovery

When interwatch runs, it:
1. Reads `config/watchables.yaml` from its own plugin directory (defaults)
2. Reads `.interwatch/watchables.yaml` from the project root (overrides)
3. Merges: project overrides win for same-named watchables
4. Skips watchables whose path doesn't exist in the current project
