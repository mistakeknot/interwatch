---
name: refresh
description: Force regeneration of a specific document regardless of drift score
argument-hint: "<doc-name> (e.g., roadmap, prd, vision, agents-md)"
---

# Force Refresh

Force-refresh a specific watchable regardless of its drift score.

## Arguments

<refresh_args> #$ARGUMENTS </refresh_args>

Parse the doc name from the arguments. Valid names come from `config/watchables.yaml`.

If no argument provided, use AskUserQuestion to ask which doc to refresh, listing available watchables.

Then invoke the `doc-watch` skill in **refresh** mode with the specified watchable name.

This bypasses detection and assessment — it directly invokes the generator for the specified doc.

Use the Skill tool to invoke `interwatch:doc-watch` with the instruction: "Force refresh the [doc-name] watchable."
