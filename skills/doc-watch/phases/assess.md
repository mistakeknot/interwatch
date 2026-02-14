# Confidence Assessment Phase

Using the signal scores from the detection phase, compute a confidence tier for each watchable.

## Scoring Model

Each signal has a **weight** (configured in watchables.yaml) and a **count** (how many times the signal fired). The drift score is:

```
drift_score = sum(signal_weight * signal_count for each signal)
```

Additionally, check **staleness**: days since the doc was last modified vs. the watchable's `staleness_days` threshold.

## Confidence Tiers

| Score | Staleness | Confidence | Color |
|-------|-----------|------------|-------|
| 0 | < threshold | **Green** — current | Green |
| 1-2 | < threshold | **Low** — minor drift | Blue |
| 3-5 | any | **Medium** — moderate drift | Yellow |
| 6+ | any | **High** — significant drift | Orange |
| any | > threshold | **High** — stale | Orange |
| deterministic signal fired | any | **Certain** — version/count mismatch | Red |

### Deterministic Signals

These signals produce **Certain** confidence when they fire:
- `version_bump` with mismatch detected
- `component_count_changed` with mismatch detected

These are factual contradictions — the doc is objectively wrong.

### Probabilistic Signals

These contribute to the weighted score but don't guarantee drift:
- `bead_closed`, `bead_created`
- `file_renamed`, `file_deleted`, `file_created`
- `commits_since_update`
- `brainstorm_created`
- `companion_extracted`

## Output

For each watchable, produce an assessment:

```
watchable: roadmap
drift_score: 7
staleness_days: 3
staleness_threshold: 7
confidence: High
recommendation: Auto-refresh with brief note
```
