# Doc Watch (compact)

Monitor documentation freshness using pre-computed drift signals.

## Algorithm

### Step 1: Run Pre-computation

```bash
python3 scripts/interwatch-scan.py --config config/watchables.yaml --save-state
```

If a project `.interwatch/watchables.yaml` exists, it takes precedence over the plugin's default config.

The `--save-state` flag persists baselines to `.interwatch/last-scan.json` so subsequent scans use snapshot deltas instead of absolute counts (prevents false positives after a refresh).

Read the JSON output. Each watchable has: `path`, `exists`, `score`, `confidence`, `signals`, `recommended_action`, `generator`, `generator_args`.

### Step 2: Apply Action Matrix

For each watchable, act on its `confidence` tier:

| Confidence | Action |
|------------|--------|
| **Certain** | Invoke generator silently. Apply result. |
| **High** | Invoke generator. Tell user: "Refreshed [doc] — [reason]." |
| **Medium** | Ask user via AskUserQuestion: "Drift detected in [doc] (score: N). Refresh now?" |
| **Low** | Report only: "[doc] has minor drift (score: N). No action needed." |
| **Green** | Skip — no drift. |

### Step 3: Invoke Generators

Each watchable specifies a `generator` skill and `generator_args`:

```
Skill(skill: "[generator]", args: "[generator_args]")
```

Common generators:
- `interpath:artifact-gen` — product docs (roadmap, PRD, vision, changelog, status)
- `interdoc:interdoc` — code documentation (AGENTS.md)

### Step 4: Update State

State is auto-managed when `--save-state` is passed in Step 1. After **refreshing** a specific doc (Steps 2-3), record the refresh so the next scan sees zero delta:

```bash
python3 scripts/interwatch-scan.py --record-refresh <watchable-name>
```

For example, after refreshing the roadmap: `--record-refresh roadmap`. This resets bead count baselines for that doc in `.interwatch/last-scan.json`.

## Modes

- **scan** — run Steps 1-2 only (detect + assess, no refresh)
- **status** — read `.interwatch/drift.json` and display last scan results
- **refresh** — skip detection, invoke generator for a specific watchable directly

## Output Format

Present results as a table:

```
Doc Watch — Drift Scan
────────────────────────────────────
roadmap     docs/roadmap.md        [tier]  score: N
prd         docs/PRD.md            [tier]  score: N
────────────────────────────────────
```

---

*For edge cases, signal definitions, or confidence tier details, read the full SKILL.md and its phase/reference files.*
