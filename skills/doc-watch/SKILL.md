---
name: doc-watch
description: Detect documentation drift, score confidence, and orchestrate refresh via generator plugins (Interpath for product docs, Interdoc for code docs)
---

# Doc Watch

You are monitoring documentation freshness. Follow these steps.

## Step 1: Load Watchables

Read `doc-watch/references/watchables.md` to understand the watchable registry format, then read the project's `config/watchables.yaml` to get the list of documents to monitor.

## Step 2: Detect Drift

Read `doc-watch/phases/detect.md` and evaluate each watchable's signals. For each signal, check whether the triggering condition has occurred since the doc was last updated.

## Step 3: Assess Confidence

Read `doc-watch/phases/assess.md` and compute a confidence tier for each watchable based on its accumulated signal weights.

## Step 4: Act

Read `doc-watch/phases/refresh.md` and take the appropriate action based on confidence:

| Confidence | Action |
|------------|--------|
| Certain | Auto-refresh silently |
| High | Auto-refresh with brief note |
| Medium | Suggest refresh via AskUserQuestion |
| Low | Report drift score only |

## Modes

This skill supports three modes (set by the invoking command):

- **scan** — detect + assess only (no refresh)
- **status** — show current drift scores from last scan
- **refresh** — force refresh of a specific watchable regardless of score
