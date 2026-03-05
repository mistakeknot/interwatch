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
| `interpath:artifact-gen` | interpath | Roadmap, PRD, Vision, Changelog, Status, CUJ |
| `interdoc:interdoc` | interdoc | AGENTS.md, CLAUDE.md |

## Built-in Watchables

The default `config/watchables.yaml` ships with entries for common docs. Projects can customize by editing the config file.

## Auto-Discovery

When interwatch runs with `--discover`, it auto-detects watchable docs by convention:

### Discovery Flags

| Flag | Behavior |
|------|----------|
| `--discover` | Auto-discover on first run, then scan. Skips discovery if `.interwatch/watchables.yaml` exists. |
| `--rediscover` | Force re-discovery even if `.interwatch/watchables.yaml` exists. |
| `--discover-only` | Write config without scanning. |

### How Discovery Works

1. Loads `signal_templates` and `discovery_rules` from the plugin's `config/watchables.yaml`
2. Resolves `{module}` placeholders using `plugin.json` name or directory basename
3. Checks each rule's pattern against the project filesystem
4. Applies dedup: if a rule has `skip_if_exists` and that path exists, the rule is skipped (e.g., prefer `docs/clavain-roadmap.md` over `docs/roadmap.md`)
5. Builds watchable entries from matched templates, marked with `discovered: true`
6. Checks generator availability — unavailable generators set to `null` with a `generator_note`

### Signal Templates

Templates define what signals apply to each doc type:

```yaml
signal_templates:
  roadmap:
    generator: interpath:artifact-gen
    staleness_days: 7
    signals: [bead_closed(2), version_bump(3), ...]
```

### Discovery Rules

Rules map filesystem patterns to templates:

```yaml
discovery_rules:
  - pattern: "docs/{module}-roadmap.md"
    template: roadmap
    name_format: "{module}-roadmap"
    skip_if_exists: "docs/roadmap.md"  # optional dedup
```

### Merge Behavior

On `--rediscover`, manual entries (those without `discovered: true`) in the existing `.interwatch/watchables.yaml` are preserved. Only auto-discovered entries are replaced.

## Legacy Discovery

When running without `--discover`, interwatch uses the legacy config resolution:
1. Reads `config/watchables.yaml` from its own plugin directory (defaults)
2. Reads `.interwatch/watchables.yaml` from the project root (overrides)
3. Merges: project overrides win for same-named watchables
4. Skips watchables whose path doesn't exist in the current project
