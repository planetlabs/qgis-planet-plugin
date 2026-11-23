#!/usr/bin/env bash
set -euo pipefail

scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root_dir="$(dirname "$scripts_dir")"
secrets_rules_py="$scripts_dir/get_secrets_rules.py"

read -r _ DISABLE_ARGS_STR < <(python "$secrets_rules_py")
read -ra DISABLE_ARGS <<<"$DISABLE_ARGS_STR"

baseline_rel_path="planet_explorer/.secrets.baseline"
baseline_full_path="$repo_root_dir/$baseline_rel_path"

COMMON_ARGS=(
    --no-verify
    --exclude-files '^planet_explorer/(extlibs/|\.secrets\.baseline$)'
)

cd "$repo_root_dir"

if [[ ! -f "$baseline_full_path" ]]; then
    echo "Creating fresh baseline from scratch"
    tmp_baseline="$(mktemp)"
    trap 'rm -f "$tmp_baseline"' EXIT
    detect-secrets --verbose \
        scan "${DISABLE_ARGS[@]}" \
        "${COMMON_ARGS[@]}" \
        "planet_explorer/" >"$tmp_baseline"
    mv "$tmp_baseline" "$baseline_full_path"
    echo "detect-secrets scan complete"
else
    echo "Updating baseline file"
    detect-secrets --verbose \
        scan "${DISABLE_ARGS[@]}" \
        "${COMMON_ARGS[@]}" \
        --baseline "$baseline_rel_path" \
        "planet_explorer/"
    echo "detect-secrets scan complete"
fi
