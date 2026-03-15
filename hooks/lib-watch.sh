#!/usr/bin/env bash
# Bash library for interwatch drift detection.
# Sourced by skills, not used as a hook handler.
# All functions are prefixed with _watch_ to avoid namespace collisions.

# Get file modification time as epoch seconds.
# Usage: _watch_file_mtime <path>
_watch_file_mtime() {
    local path="$1"
    stat -c %Y "$path" 2>/dev/null || stat -f %m "$path" 2>/dev/null || echo 0
}

# Get file modification time as ISO date.
# Usage: _watch_file_date <path>
_watch_file_date() {
    local mtime
    mtime=$(_watch_file_mtime "$1")
    if [[ "$mtime" -gt 0 ]]; then
        date -d "@$mtime" +%Y-%m-%d 2>/dev/null || date -r "$mtime" +%Y-%m-%d 2>/dev/null || echo "unknown"
    else
        echo "unknown"
    fi
}

# Count days since file was last modified.
# Usage: _watch_staleness_days <path>
_watch_staleness_days() {
    local mtime now
    mtime=$(_watch_file_mtime "$1")
    now=$(date +%s)
    if [[ "$mtime" -gt 0 ]]; then
        echo $(( (now - mtime) / 86400 ))
    else
        echo 999
    fi
}

# Extract version from doc header (looks for "Version: X.Y.Z" in first 10 lines).
# Usage: _watch_doc_version <path>
_watch_doc_version() {
    head -10 "$1" 2>/dev/null | grep -oP 'Version:\s*\K[\d.]+' || echo "unknown"
}

# Get plugin.json version.
# Usage: _watch_plugin_version
_watch_plugin_version() {
    python3 -c "import json; print(json.load(open('.claude-plugin/plugin.json'))['version'])" 2>/dev/null || echo "unknown"
}

# Count git commits since a given epoch timestamp.
# Usage: _watch_commits_since <epoch>
_watch_commits_since() {
    local since="$1"
    git rev-list --count HEAD --after="$since" 2>/dev/null || echo 0
}

# List files changed (renamed/deleted/created) since a doc was last modified.
# Usage: _watch_file_changes <doc_path>
_watch_file_changes() {
    local doc_path="$1"
    local mtime
    mtime=$(_watch_file_mtime "$doc_path")
    local commit
    commit=$(git log -1 --format=%H --until="@$mtime" 2>/dev/null || echo "")
    if [[ -n "$commit" ]]; then
        git diff --name-status "$commit"..HEAD -- skills/ commands/ agents/ hooks/ 2>/dev/null
    fi
}

# Count brainstorms newer than a given file.
# Usage: _watch_newer_brainstorms <doc_path>
_watch_newer_brainstorms() {
    find docs/brainstorms/ -name "*.md" -newer "$1" 2>/dev/null | wc -l | tr -d ' '
}

# Check roadmap-bead coverage using the audit script.
# Returns JSON with coverage_pct and confidence level.
# Usage: _watch_roadmap_bead_coverage [roadmap_path]
# Confidence mapping:
#   green  — 100% coverage, all roadmap IDs have beads
#   blue   — >95% coverage, minor gaps
#   yellow — 80-95% coverage
#   orange — <80% coverage
#   red    — audit script or beads database unreachable
_watch_roadmap_bead_coverage() {
    local roadmap="${1:-}"
    local repo_root
    repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
    local script="$repo_root/scripts/audit-roadmap-beads.sh"

    if [[ ! -x "$script" ]]; then
        echo '{"coverage_pct":0,"confidence":"red","error":"audit script not found"}'
        return 1
    fi

    if ! command -v bd >/dev/null 2>&1; then
        echo '{"coverage_pct":0,"confidence":"red","error":"bd command not available"}'
        return 1
    fi

    local result
    if [[ -n "$roadmap" ]]; then
        result=$("$script" --json "$roadmap" 2>/dev/null)
    else
        result=$("$script" --json 2>/dev/null)
    fi

    if [[ $? -ne 0 ]] || [[ -z "$result" ]]; then
        echo '{"coverage_pct":0,"confidence":"red","error":"audit script failed"}'
        return 1
    fi

    echo "$result"
}

# Count solution docs older than 14 days without synthesized_into frontmatter.
# Usage: _watch_unsynthesized_count [solutions_dir]
_watch_unsynthesized_count() {
    local dir="${1:-docs/solutions}"
    if [[ ! -d "$dir" ]]; then
        echo 0
        return
    fi

    local count=0
    local cutoff
    cutoff=$(date -d "14 days ago" +%s 2>/dev/null || date -v-14d +%s 2>/dev/null || echo 0)

    while IFS= read -r -d '' file; do
        # Skip special files
        local basename
        basename=$(basename "$file")
        [[ "$basename" == "INDEX.md" || "$basename" == "TEMPLATE.md" ]] && continue

        # Skip files newer than 14 days
        local mtime
        mtime=$(_watch_file_mtime "$file")
        [[ "$mtime" -gt "$cutoff" ]] && continue

        # Check for synthesized_into in YAML frontmatter
        if head -20 "$file" 2>/dev/null | grep -q "^synthesized_into:"; then
            continue
        fi

        ((count++))
    done < <(find "$dir" -name "*.md" -print0 2>/dev/null)

    echo "$count"
}

# Count SKILL.md files >90 lines that lack a sibling SKILL-compact.md.
# Usage: _watch_skills_without_compact
_watch_skills_without_compact() {
    local count=0

    for skill_md in skills/*/SKILL.md; do
        [[ -f "$skill_md" ]] || continue

        local skill_dir
        skill_dir=$(dirname "$skill_md")
        [[ -f "$skill_dir/SKILL-compact.md" ]] && continue

        local lines
        lines=$(wc -l < "$skill_md" 2>/dev/null || echo 0)
        if [[ "$lines" -gt 90 ]]; then
            ((count++))
        fi
    done

    echo "$count"
}
