# Confidence Tiers

Confidence tiers determine the action taken when drift is detected.

## Tier Definitions

### Certain (Red)

**When:** Deterministic signals fire — version mismatch, count mismatch.

**Action:** Auto-refresh silently. The doc contains factual errors that can be corrected without judgment.

**Example:** plugin.json says v0.6.5 but roadmap says v0.6.4.

### High (Orange)

**When:** Multiple corroborating signals produce a drift score of 6+, OR doc exceeds staleness threshold.

**Action:** Auto-refresh with brief note to user: "Refreshed docs/roadmap.md — 5 beads closed since last update, version bumped."

**Example:** 3 beads closed + 1 brainstorm created + doc is 10 days old.

### Medium (Yellow)

**When:** Drift score 3-5. Moderate signal activity, may be intentional.

**Action:** Show drift summary and ask user via AskUserQuestion: "Drift detected in docs/PRD.md (score: 4). Refresh now?"

**Example:** 2 beads closed + new companion detected.

### Low (Blue)

**When:** Drift score 1-2. Minor activity, probably noise.

**Action:** Report only in status output. No prompt, no refresh.

**Example:** 1 commit since last update.

### Green

**When:** Drift score 0 and within staleness threshold.

**Action:** No action. Doc is current.

## Score Thresholds

| Range | Tier |
|-------|------|
| 0 | Green |
| 1-2 | Low |
| 3-5 | Medium |
| 6+ | High |
| deterministic | Certain |
| stale | High (override) |
