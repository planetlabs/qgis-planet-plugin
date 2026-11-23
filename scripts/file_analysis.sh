#!/usr/bin/env bash
set -euo pipefail

TARGET="${1:-planet_explorer/}"

# Fetch enabled rules from remote JSON
RULES=$(python -c "
import json, sys, urllib.request
url = 'https://raw.githubusercontent.com/qgis/QGIS-Plugins-Website/ae1a19a1c5818043630e7642c4f8ed07419828dc/qgis-app/plugins/management/commands/data/file_analysis_rules.json'
data = json.load(urllib.request.urlopen(url))
enabled = [r['check_code'] for r in data['rules'] if r['enabled']]
print(','.join(enabled))
")

echo "Running file checks with enabled rules: $RULES"

FAILED=0

# Helper function to generate file list while ignoring extlibs, .git, and gitignored files
get_files() {
    # 1. find skips 'extlibs' and '.git' directories entirely using -prune
    # 2. git check-ignore filters out anything matched by .gitignore
    find "$TARGET" \
        -type d \( -name "extlibs" -o -name ".git" -o -name "tests" -o -name "resources" \) -prune \
        -o -type f -print0 | \
        xargs -0 -I {} sh -c 'git check-ignore -q "{}" || echo -n "{}\0"'
}

if echo "$RULES" | grep -q "FILE_EXECUTABLE"; then
    while IFS= read -r -d '' file; do
        if [ -f "$file" ] && [ -x "$file" ]; then
            echo "$file: FILE_EXECUTABLE file has executable bit set"
            FAILED=1
        fi
    done < <(get_files)
fi

if echo "$RULES" | grep -q "FILE_BINARY"; then
    while IFS= read -r -d '' file; do
        if [ -f "$file" ] && ! file "$file" | grep -qE "text|empty|JSON|XML"; then
            echo "$file: FILE_BINARY binary file found"
            FAILED=1
        fi
    done < <(get_files)
fi

if echo "$RULES" | grep -q "FILE_SUSPICIOUS"; then
    while IFS= read -r -d '' file; do
        if [[ "$file" =~ \.(exe|dll|so|sh|bat|cmd)$ ]]; then
            echo "$file: FILE_SUSPICIOUS suspicious file type found"
            FAILED=1
        fi
    done < <(get_files)
fi

if echo "$RULES" | grep -q "FILE_HIDDEN"; then
    while IFS= read -r -d '' file; do
        if [ -f "$file" ] && [[ "$(basename "$file")" == .* ]]; then
            echo "$file: FILE_HIDDEN hidden file found"
            FAILED=1
        fi
    done < <(get_files)
fi

if [ "$FAILED" -eq 0 ]; then
    echo "No file issues found."
fi

exit "$FAILED"
