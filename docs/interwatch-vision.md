# interwatch — Vision and Philosophy

**Version:** 0.1.8
**Last updated:** 2026-02-27

## What interwatch Is

interwatch monitors documentation freshness across a project's key artifacts. It auto-discovers watchable documents by convention — Vision, PRD, Roadmap, AGENTS.md, solution docs — and evaluates whether project activity since the last update constitutes evidence of drift. 14 signal types detect changes: beads closed, files renamed or deleted, commits since last update, version bumps, component count changes, roadmap-bead coverage gaps, unsynthesized solution docs, and skills lacking compact companions. These are combined into a weighted drift score that maps to a confidence tier: Green (current), Low, Medium, High, or Certain. Confidence determines action — from silent auto-refresh at Certain down to report-only at Low.

interwatch does not regenerate documents itself. It detects drift and dispatches to generator plugins: interpath for product artifacts (roadmap, PRD, vision), interdoc for code docs (AGENTS.md). It is a sensor and orchestrator, not a writer.

## Why This Exists

Stale documentation is silent technical debt for agents. An agent working from an AGENTS.md that describes last quarter's architecture is not operating with accurate memory — it is guessing. interwatch exists because documentation drift compounds invisibly: no single stale sentence breaks anything, but together they degrade every agent decision that depends on them. Measuring drift quantitatively makes the invisible visible, and a scored, inspectable receipt is actionable in a way that "remember to update the docs" never is.

## Design Principles

1. **Signals over timestamps.** Timestamp-only staleness checks are weak — a doc may be touched without being updated meaningfully, or untouched for weeks while the codebase stays stable. interwatch evaluates what changed: beads closed, files moved, version numbers incremented. Multiple signals resist single-metric gaming.

2. **Confidence tiers are graduated, not binary.** The system does not declare a doc stale or current. It scores drift and assigns a tier. Certain means a factual contradiction (version mismatch, component count wrong). High means strong probabilistic evidence. Medium invites human judgment. Low reports and stops. This prevents false urgency and preserves human authority at the right level.

3. **Generator-agnostic dispatch.** interwatch does not know how to regenerate any document. It knows which generator to call. This keeps concerns separated: interwatch owns detection and orchestration, interpath and interdoc own generation. Replacing a generator does not require changing interwatch.

4. **State is durable and inspectable.** Drift scores, scan history, and bead baselines are written to `.interwatch/` as plain JSON. A future agent session can read the last scan results without re-running detection. Receipts, not narratives.

5. **On-demand, not ambient.** There are no hooks running drift detection on every file save or commit. Detection is invoked explicitly via `/interwatch:watch` or surfaced by Clavain at session checkpoints. Continuous ambient scanning would add noise without improving signal quality.

6. **Convention-based discovery over manual configuration.** Projects shouldn't need to hand-author a watchables config. interwatch auto-discovers docs by matching the monorepo's naming conventions (`docs/{module}-roadmap.md`, `AGENTS.md`, etc.) and builds a per-project config on first run. Manual overrides are preserved on rediscovery — convention handles the common case, configuration handles the edge case.

## Scope

**Does:** Auto-discover watchable docs by convention. Detect documentation drift via 14 signal types. Score drift with weighted, tiered confidence. Dispatch to interpath or interdoc for regeneration. Maintain per-project scan state. Expose three commands (watch, status, refresh) and one skill (doc-watch).

**Does not:** Generate documentation content directly. Enforce documentation policies via hooks. Run continuously in the background. Monitor non-documentation files. Replace the generator plugins it delegates to.

## Shipped (0.1.x)

- Three-phase skill (detect → assess → refresh) with phase files and reference docs
- `config/watchables.yaml` with default entries for Vision, PRD, Roadmap, AGENTS.md, distillation-candidates
- Bead-count baseline tracking with snapshot-delta signals and `--record-refresh` reset
- Pre-computation scanner (`interwatch-scan.py`) with 14 signal evaluators
- Auto-discovery: convention-based watchable detection with `signal_templates`, `discovery_rules`, dedup, and manual entry preservation
- Three new signals: `roadmap_bead_coverage`, `unsynthesized_doc_count`, `skills_without_compact`
- Threshold refactoring: data-driven `THRESHOLD_SIGNALS` dispatch table

## Direction

- Cross-project scanning: run discovery across all monorepo subprojects in a single invocation
- Drift trend tracking: historical score progression to detect worsening vs. improving doc health
- Generator availability awareness: degrade gracefully when interpath/interdoc are not installed, suggest install
- Ambient mode (opt-in): periodic scan at Clavain session checkpoints without explicit invocation
