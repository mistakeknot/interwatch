# Refresh Orchestration Phase

Based on confidence assessment, take the appropriate action for each watchable.

## Action Matrix

| Confidence | Action |
|------------|--------|
| **Certain** | Invoke generator silently. Apply result. Record in history. |
| **High** | Invoke generator. Apply result. Tell user: "Refreshed [doc] — [reason]." |
| **Medium** | Show drift summary. Use AskUserQuestion: "Drift detected in [doc] (score: N). Refresh now?" |
| **Low** | Report only: "[doc] has minor drift (score: N). No action needed." |
| **Green** | Skip — no drift detected. |

## Generator Invocation

Each watchable has a `generator` field that specifies which plugin's skill to invoke:

- `interpath:artifact-gen` — for product artifacts (roadmap, PRD, vision, changelog, status)
- `interdoc:interdoc` — for code documentation (AGENTS.md)

To invoke a generator, use the Skill tool:

```
Skill(skill: "[generator]", args: "[generator_args]")
```

For example, for a roadmap watchable:
```
Skill(skill: "interpath:artifact-gen", args: "Generate a roadmap artifact")
```

## Diff Review

Before applying a refresh:
1. Read the current doc
2. Generate the new version
3. Compare for significant changes
4. If changes are trivial (whitespace, dates only): apply silently even for Medium confidence
5. If changes are substantial: follow the confidence-based action matrix

## State Update

State is managed automatically by the scanner:

- **`--save-state`** (on scan): Writes `drift.json` (full scan results) and `last-scan.json` (bead count baselines per doc).
- **`--record-refresh <name>`** (after refresh): Resets bead count baselines for the refreshed doc so the next scan sees zero delta.

After invoking a generator for any watchable, always record the refresh:

```bash
python3 scripts/interwatch-scan.py --record-refresh <watchable-name>
```

This prevents false positives on the next scan — without it, bead_closed/bead_created signals would fire against stale baselines.

## Force Refresh

When invoked with mode=refresh and a specific watchable name:
1. Skip detection and assessment
2. Invoke the generator directly
3. Apply the result
4. Update state
