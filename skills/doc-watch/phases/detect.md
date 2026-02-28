# Drift Detection Phase

For each watchable in the registry, evaluate its configured signals.

## Signal Evaluation

### bead_closed

Uses **snapshot delta**: compares current `bd list --status=closed` count against the baseline stored in `.interwatch/last-scan.json`. Only the *change* since last scan triggers drift. If no baseline exists (first run), falls back to capped total count (conservative).

### bead_created

Same snapshot-delta approach: compares current `bd list --status=open` count against baseline from `last-scan.json`. Only new beads since last scan trigger drift.

### version_bump

```bash
# Compare plugin.json version with version mentioned in doc header
plugin_version=$(python3 -c "import json; print(json.load(open('.claude-plugin/plugin.json'))['version'])" 2>/dev/null || echo "unknown")
doc_version=$(head -10 "$DOC_PATH" 2>/dev/null | grep -oP 'Version:\s*\K[\d.]+' || echo "unknown")
if [ "$plugin_version" != "$doc_version" ]; then echo "DRIFT"; fi
```

### component_count_changed

```bash
# Count actual components vs. doc claims
actual_skills=$(ls skills/*/SKILL.md 2>/dev/null | wc -l | tr -d ' ')
actual_commands=$(ls commands/*.md 2>/dev/null | wc -l | tr -d ' ')
# Compare against counts parsed from doc
```

### file_renamed / file_deleted / file_created

```bash
# Check git changes since doc was last modified
doc_mtime=$(stat -c %Y "$DOC_PATH" 2>/dev/null || echo 0)
doc_commit=$(git log -1 --format=%H --until="@$doc_mtime" 2>/dev/null || echo "HEAD~20")
git diff --name-status "$doc_commit"..HEAD -- skills/ commands/ agents/ 2>/dev/null
```

### commits_since_update

```bash
# Count commits since doc was last modified
git rev-list --count HEAD --since="@$doc_mtime" 2>/dev/null || echo 0
```

### brainstorm_created

```bash
# Check for brainstorms newer than doc
find docs/brainstorms/ -name "*.md" -newer "$DOC_PATH" 2>/dev/null | wc -l | tr -d ' '
```

### companion_extracted

Check plugin cache for companion plugins not mentioned in the doc.

### roadmap_bead_coverage

Sources `_watch_roadmap_bead_coverage` from `hooks/lib-watch.sh` via bash subprocess. Parses the JSON result and checks `coverage_pct` against `threshold_min` (default 95%). Returns 1 if coverage is below threshold, 0 otherwise. Gracefully returns 0 if the audit script or `bd` command is not available.

```bash
source hooks/lib-watch.sh && _watch_roadmap_bead_coverage "$DOC_PATH"
# Returns JSON: {"coverage_pct": 92, "confidence": "yellow", ...}
```

### unsynthesized_doc_count

Walks `docs/solutions/` recursively for `.md` files. Skips `INDEX.md` and `TEMPLATE.md`. Skips files newer than 14 days (too recent to expect synthesis). Parses YAML frontmatter — files with a `synthesized_into` field are considered synthesized. Returns 1 if unsynthesized count >= threshold (default 5), else 0.

### skills_without_compact

Globs `skills/*/SKILL.md` files. Counts those with >90 lines that lack a sibling `SKILL-compact.md`. Returns 1 if count >= threshold (default 3), else 0.

## Output

For each watchable, produce a signal report:

```
watchable: roadmap
path: docs/myproject-roadmap.md
signals:
  bead_closed: 3 (weight 2, score 6)
  version_bump: 0 (weight 3, score 0)
  brainstorm_created: 1 (weight 1, score 1)
total_score: 7
```
