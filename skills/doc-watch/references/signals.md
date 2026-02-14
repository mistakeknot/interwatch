# Signal Catalog

Signals are events that indicate potential documentation drift.

## Signal Types

| Signal | Detection Method | Cost | Weight Range |
|--------|-----------------|------|--------------|
| `bead_closed` | `bd list --status=closed` vs. last scan | Free (bd CLI) | 1-3 |
| `bead_created` | `bd list --status=open` vs. last scan | Free (bd CLI) | 1-2 |
| `version_bump` | plugin.json version vs. doc header | Free (file read) | 2-3 |
| `component_count_changed` | glob count vs. doc claims | Free (glob) | 2-3 |
| `file_renamed` | `git diff --name-status` since doc mtime | Free (git) | 2-3 |
| `file_deleted` | `git diff --name-status` since doc mtime | Free (git) | 2-3 |
| `file_created` | `git diff --name-status` since doc mtime | Free (git) | 1-2 |
| `commits_since_update` | `git rev-list --count` since doc mtime | Free (git) | 1 |
| `brainstorm_created` | `find docs/brainstorms/ -newer $DOC` | Free (find) | 1 |
| `companion_extracted` | plugin cache search for new companions | Free (find) | 2-3 |
| `research_completed` | new flux-drive summaries since doc mtime | Free (find) | 1-2 |

## Signal Categories

### Deterministic Signals

Produce **Certain** confidence when they fire — the doc is objectively wrong:
- `version_bump` (version number mismatch)
- `component_count_changed` (count mismatch)

### Probabilistic Signals

Contribute to weighted score — drift is likely but not guaranteed:
- All other signal types

## Adding New Signals

To add a signal type:
1. Add detection logic to `hooks/lib-watch.sh`
2. Add signal definition to `config/watchables.yaml` for relevant watchables
3. Update `phases/detect.md` with evaluation instructions
