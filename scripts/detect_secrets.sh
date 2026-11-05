#!/usr/bin/env bash
set -euo pipefail

scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root_dir="$(dirname "$scripts_dir")"
secrets_rules_py="$scripts_dir/get_secrets_rules.py"

read -r DISABLED_LIST DISABLE_ARGS_STR < <(python "$secrets_rules_py")
read -ra DISABLE_ARGS <<<"$DISABLE_ARGS_STR"

baseline_rel_path="planet_explorer/.secrets.baseline"

echo "Running detect-secrets with plugins disabled: $DISABLED_LIST"
# Run through pre-commit to check for secrets
cd "$repo_root_dir"
mapfile -t FILES < <(git ls-files -- planet_explorer/ ':(exclude)planet_explorer/extlibs' ":(exclude)$baseline_rel_path")

detect-secrets-hook --verbose \
    --json \
    --baseline "$baseline_rel_path" \
    --no-verify \
    --exclude-files '^planet_explorer/(extlibs/|\.secrets\.baseline$)' \
    "${DISABLE_ARGS[@]}" "${FILES[@]}"
