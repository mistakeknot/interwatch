# interwatch — Vision and Philosophy

**Version:** 0.1.0
**Last updated:** 2026-02-28

## What interwatch Is

interwatch monitors documentation freshness across a project's key artifacts. It watches a configurable set of documents — Vision, PRD, Roadmap, AGENTS.md, CLAUDE.md — and evaluates whether project activity since the last update constitutes evidence of drift. Signals include beads closed, files renamed or deleted, commits since last update, version bumps, and component count changes. These are combined into a weighted drift score that maps to a confidence tier: Green (current), Low, Medium, High, or Certain. Confidence determines action — from silent auto-refresh at Certain down to report-only at Low.

interwatch does not regenerate documents itself. It detects drift and dispatches to generator plugins: interpath for product artifacts (roadmap, PRD, vision), interdoc for code docs (AGENTS.md). It is a sensor and orchestrator, not a writer.

## Why This Exists

Stale documentation is silent technical debt for agents. An agent working from an AGENTS.md that describes last quarter's architecture is not operating with accurate memory — it is guessing. interwatch exists because documentation drift compounds invisibly: no single stale sentence breaks anything, but together they degrade every agent decision that depends on them. Measuring drift quantitatively makes the invisible visible, and a scored, inspectable receipt is actionable in a way that "remember to update the docs" never is.

## Design Principles

1. **Signals over timestamps.** Timestamp-only staleness checks are weak — a doc may be touched without being updated meaningfully, or untouched for weeks while the codebase stays stable. interwatch evaluates what changed: beads closed, files moved, version numbers incremented. Multiple signals resist single-metric gaming.

2. **Confidence tiers are graduated, not binary.** The system does not declare a doc stale or current. It scores drift and assigns a tier. Certain means a factual contradiction (version mismatch, component count wrong). High means strong probabilistic evidence. Medium invites human judgment. Low reports and stops. This prevents false urgency and preserves human authority at the right level.

3. **Generator-agnostic dispatch.** interwatch does not know how to regenerate any document. It knows which generator to call. This keeps concerns separated: interwatch owns detection and orchestration, interpath and interdoc own generation. Replacing a generator does not require changing interwatch.

4. **State is durable and inspectable.** Drift scores, scan history, and bead baselines are written to `.interwatch/` as plain JSON. A future agent session can read the last scan results without re-running detection. Receipts, not narratives.

5. **On-demand, not ambient.** There are no hooks running drift detection on every file save or commit. Detection is invoked explicitly via `/interwatch:watch` or surfaced by Clavain at session checkpoints. Continuous ambient scanning would add noise without improving signal quality.

## Scope

**Does:** Detect documentation drift via configurable signals. Score drift with weighted, tiered confidence. Dispatch to interpath or interdoc for regeneration. Maintain per-project scan state. Expose three commands (watch, status, refresh) and one skill (doc-watch).

**Does not:** Generate documentation content directly. Enforce documentation policies via hooks. Run continuously in the background. Monitor non-documentation files. Replace the generator plugins it delegates to.

## Direction

- Add `detect.md` phase file to complete the three-phase skill (detect → assess → refresh)
- Implement `config/watchables.yaml` with default entries for Vision, PRD, Roadmap, AGENTS.md
- Wire bead-count baseline tracking so signal counts reset correctly after each refresh
