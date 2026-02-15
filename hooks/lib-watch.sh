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
