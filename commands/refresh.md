---
name: refresh
description: Force regeneration of a specific document regardless of drift score
argument-hint: "<doc-name> [--attempt-id <hook-supplied-id>]"
---

# Force Refresh

Force-refresh a specific watchable regardless of its drift score.

## Arguments

<refresh_args> #$ARGUMENTS </refresh_args>

Parse the doc name from the arguments. Valid names come from `config/watchables.yaml`.

If this refresh follows an auto-fire advisory, retain its supplied attempt ID
(or the explicit `--attempt-id` argument) in the skill handoff. It must be passed
to the scanner's record-refresh command. Manual refreshes have no attempt ID;
do not select a recent logged attempt on their behalf.

If no argument provided, use AskUserQuestion to ask which doc to refresh, listing available watchables.

Then invoke the `doc-watch` skill in **refresh** mode with the specified watchable name.

This bypasses detection and assessment — it directly invokes the generator for the specified doc.

Use the Skill tool to invoke `interwatch:doc-watch` with the instruction: "Force refresh the [doc-name] watchable."

Include "Record with --attempt-id [hook-supplied-id]" only when that originating
ID is present. In other hosts, use the available skill/workflow mechanism.
