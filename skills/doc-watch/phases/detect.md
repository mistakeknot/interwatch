# Drift Detection Phase

For each watchable in the registry, evaluate its configured signals.

## Signal Evaluation

### bead_closed

```bash
# Count beads closed since doc was last modified
doc_mtime=$(stat -c %Y "$DOC_PATH" 2>/dev/null || echo 0)
doc_date=$(date -d "@$doc_mtime" +%Y-%m-%d 2>/dev/null || echo "1970-01-01")
bd list --status=closed 2>/dev/null | grep -c "closed after $doc_date" || echo 0
```

Simplified: compare `bd stats` closed count against last-scan snapshot.

### bead_created

Compare current `bd list --status=open` count against last-scan snapshot.

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

## Output

For each watchable, produce a signal report:

```
watchable: roadmap
path: docs/roadmap.md
signals:
  bead_closed: 3 (weight 2, score 6)
  version_bump: 0 (weight 3, score 0)
  brainstorm_created: 1 (weight 1, score 1)
total_score: 7
```
