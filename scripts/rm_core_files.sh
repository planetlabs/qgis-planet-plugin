#!/usr/bin/env bash
set -euo pipefail

: "${REPO_ROOT_DIR:?Error: REPO_ROOT_DIR environment variable is not set.}"

mapfile -d '' CORE_FILES < <(
    fd '^core\.[0-9]+$' \
        --unrestricted --case-sensitive --absolute-path --type file \
        --base-directory "$REPO_ROOT_DIR" --print0
)

if [[ ${#CORE_FILES[@]} -eq 0 ]]; then
    gum style --foreground 2 "No core files found."
    exit 0
fi

gum style --bold --foreground 3 "Found ${#CORE_FILES[@]} core file(s):"
du -h -- "${CORE_FILES[@]}"

if gum confirm "Delete these ${#CORE_FILES[@]} file(s)?"; then
    rm -v -- "${CORE_FILES[@]}"
else
    echo "Aborted, nothing deleted."
fi
