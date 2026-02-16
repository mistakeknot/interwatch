# Doc Watch (compact)

Monitor documentation freshness using pre-computed drift signals.

## Algorithm

### Step 1: Run Pre-computation

```bash
python3 scripts/interwatch-scan.py --config config/watchables.yaml
```

If a project `.interwatch/watchables.yaml` exists, it takes precedence over the plugin's default config.

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

After scanning (regardless of actions taken):

```bash
mkdir -p .interwatch
# Write scan results to .interwatch/drift.json
```

Write the full JSON output from Step 1 to `.interwatch/drift.json`.

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
