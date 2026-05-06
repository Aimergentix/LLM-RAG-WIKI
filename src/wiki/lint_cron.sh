#!/usr/bin/env bash
# lint_cron.sh — thin cron wrapper that invokes graph_lint.py from the
# stable .wiki/bin/ copy and appends a line to .wiki/cron.log.
#
# Usage:
#   lint_cron.sh [WIKI_ROOT]   (cron calls this; default: $PWD)
#
# Exit code mirrors graph_lint.py.

set -euo pipefail

# ---- 1. Locate wiki root -----------------------------------------------------

find_wiki_root() {
    local dir="${1:-$PWD}"
    while [[ "$dir" != "/" ]]; do
        if [[ -f "$dir/SCHEMA.md" ]]; then
            echo "$dir"
            return 0
        fi
        if [[ -d "$dir/.git" ]]; then
            return 1
        fi
        dir="$(dirname "$dir")"
    done
    return 1
}

WIKI_ROOT="${1:-}"
if [[ -z "$WIKI_ROOT" ]]; then
    WIKI_ROOT="$(find_wiki_root "$PWD")" || {
        echo "ERROR: No SCHEMA.md found walking up from $PWD" >&2
        exit 1
    }
else
    if [[ ! -d "$WIKI_ROOT" ]]; then
        echo "ERROR: $WIKI_ROOT is not a directory" >&2
        exit 1
    fi
    WIKI_ROOT="$(cd "$WIKI_ROOT" && pwd)"
    [[ -f "$WIKI_ROOT/SCHEMA.md" ]] || {
        echo "ERROR: $1 is not inside a wiki (no SCHEMA.md)." >&2
        exit 1
    }
fi
WIKI_ROOT="$(cd "$WIKI_ROOT" && pwd)"

# ---- 1b. Guard against concurrent runs --------------------------------------
# Cron may fire while a previous run is still active (long lints, slow disk).
# A second concurrent run would race on .lint_result.json / .alert.md /
# cron.log. Take a non-blocking flock; if held, exit 0 silently so cron does
# not retry-storm. Skip the guard if flock(1) is unavailable (e.g. macOS
# default) — the underlying writes are still atomic per-line.
mkdir -p "$WIKI_ROOT/.wiki"
if command -v flock >/dev/null 2>&1; then
    LOCK_FD=9
    LOCK_FILE="$WIKI_ROOT/.wiki/.lint_cron.lock"
    exec 9>"$LOCK_FILE"
    if ! flock -n "$LOCK_FD"; then
        exit 0
    fi
fi

# ---- 2. Run graph_lint.py ---------------------------------------------------

LINT_PY="$WIKI_ROOT/.wiki/bin/graph_lint.py"
if [[ ! -f "$LINT_PY" ]]; then
    echo "ERROR: graph_lint.py not found at $LINT_PY — run install_wiki_bin.sh first." >&2
    exit 1
fi

EXIT_CODE=0
JSON_OUT="$WIKI_ROOT/.wiki/.lint_result.json"
mkdir -p "$WIKI_ROOT/.wiki"

# Run with JSON output and logging enabled
python3 "$LINT_PY" "$WIKI_ROOT" --log --fail-on=medium --json > "$JSON_OUT" || EXIT_CODE=$?

# ---- 3. Alert Producer ------------------------------------------------------

# Parse JSON to determine if a human-readable alert is needed
python3 <<EOF
import json, os
try:
    with open("$JSON_OUT", "r") as f:
        data = json.load(f)
    issues = [i for i in data.get("issues", []) if i["severity"] in ["high", "medium"]]
    alert_file = "$WIKI_ROOT/.wiki/.alert.md"
    if issues:
        with open(alert_file, "w") as f:
            f.write(f"⚠️ **WIKI ALERT**: Graph linter found {len(issues)} issues (High/Medium).\n")
            f.write("Run \`python3 -m wiki.graph_lint .\` to review.\n")
    elif os.path.exists(alert_file):
        os.remove(alert_file)
except Exception:
    pass
EOF

# ---- 4. Append to cron.log --------------------------------------------------

CRON_LOG="$WIKI_ROOT/.wiki/cron.log"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] lint_cron exit=$EXIT_CODE" >> "$CRON_LOG"

exit "$EXIT_CODE"
