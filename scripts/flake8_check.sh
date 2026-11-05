#!/usr/bin/env bash
set -euo pipefail

scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root_dir="$(dirname "$scripts_dir")"
config_file="$repo_root_dir/planet_explorer/.flake8"

flake8_rules_py="$scripts_dir/get_flake8_rules.py"
CODES=$(python "$flake8_rules_py")

if [ -z "$CODES" ]; then
    echo "ERROR: Could not read rules from URL"
    exit 1
fi

echo "Running flake8 with enabled rules: $CODES"
flake8 --config="$config_file" --select="$CODES" \
    "$repo_root_dir/planet_explorer/" "$repo_root_dir/scripts/"
