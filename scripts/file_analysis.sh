#!/usr/bin/env bash
set -euo pipefail

scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root_dir="$(dirname "$scripts_dir")"
file_analysis_rules_py="$scripts_dir/get_file_analysis_rules.py"

TARGET="${1:-planet_explorer/}"

# Fetch enabled rules from remote JSON
RULES=$(python "$file_analysis_rules_py")

echo "Running file checks with enabled rules: $RULES"

FAILED=0

# Helper function to generate file list while ignoring extlibs, .git, and gitignored files
get_files() {
    fd --type f --hidden --print0 \
        --exclude extlibs \
        --exclude tests \
        --exclude resources \
        . "$TARGET"
}

cd "$repo_root_dir"
mapfile -d '' -t FILES < <(get_files)

if [ "${#FILES[@]}" -eq 0 ]; then
    echo "ERROR: no files found in '$TARGET'" >&2
    exit 1
else
    echo "Checking ${#FILES[@]} files"
fi

if echo "$RULES" | grep -q "FILE_EXECUTABLE"; then
    for file in "${FILES[@]}"; do
        if [ -f "$file" ] && [ -x "$file" ]; then
            echo "$file: FILE_EXECUTABLE file has executable bit set"
            FAILED=1
        fi
    done
fi

if echo "$RULES" | grep -q "FILE_BINARY"; then
    for file in "${FILES[@]}"; do
        if [ -f "$file" ] && ! file "$file" | grep -qE "text|empty|JSON|XML"; then
            echo "$file: FILE_BINARY binary file found"
            FAILED=1
        fi
    done
fi

if echo "$RULES" | grep -q "FILE_SUSPICIOUS"; then
    for file in "${FILES[@]}"; do
        if [[ "$file" =~ \.(exe|dll|so|sh|bat|cmd)$ ]]; then
            echo "$file: FILE_SUSPICIOUS suspicious file type found"
            FAILED=1
        fi
    done
fi

if echo "$RULES" | grep -q "FILE_HIDDEN"; then
    for file in "${FILES[@]}"; do
        if [ -f "$file" ] && [[ "$(basename "$file")" == .* ]]; then
            echo "$file: FILE_HIDDEN hidden file found"
            FAILED=1
        fi
    done
fi

if [ "$FAILED" -eq 0 ]; then
    echo "No file issues found."
fi

exit "$FAILED"
