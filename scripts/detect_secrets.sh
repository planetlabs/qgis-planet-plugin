#!/usr/bin/env bash
set -euo pipefail

read -r DISABLED_LIST DISABLE_ARGS_STR < <(python -c "
import json, requests
url = 'https://raw.githubusercontent.com/qgis/QGIS-Plugins-Website/ae1a19a1c5818043630e7642c4f8ed07419828dc/qgis-app/plugins/management/commands/data/secrets_rules.json'
data = requests.get(url).json()
disabled = [r['check_code'] for r in data['rules'] if not r['enabled']]
print(','.join(disabled), ' '.join(f'--disable-plugin {code}' for code in disabled))
")

# Convert to array to avoid word splitting warning
read -ra DISABLE_ARGS <<< "$DISABLE_ARGS_STR"

echo "Running detect-secrets with plugins disabled: $DISABLED_LIST"
# Updates baseline
# detect-secrets scan "${DISABLE_ARGS[@]}" --baseline .secrets.baseline planet_explorer/
# Run through pre-commit to check for secrets
mapfile -t FILES < <(git ls-files planet_explorer/ | grep -v 'planet_explorer/extlibs')
detect-secrets-hook --baseline .secrets.baseline "${DISABLE_ARGS[@]}" "${FILES[@]}"
