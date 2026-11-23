#!/usr/bin/env bash
set -euo pipefail

scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root_dir="$(dirname "$scripts_dir")"
bandit_codes_py="$scripts_dir/get_bandit_rules.py"

CODES=$(python "$bandit_codes_py")

if [ -z "$CODES" ]; then
    echo "ERROR: Could not fetch bandit rules"
    exit 1
fi

echo "Running bandit with enabled rules: $CODES"
bandit --ini "$repo_root_dir/planet_explorer/.bandit" \
    --tests "$CODES" \
    -r "$repo_root_dir/planet_explorer/"
