#!/usr/bin/env bash
set -euo pipefail

CODES=$(python -c "
import json, sys
import urllib.request
url = 'https://raw.githubusercontent.com/qgis/QGIS-Plugins-Website/refs/heads/master/qgis-app/plugins/management/commands/data/flake8_rules.json'
data = json.load(urllib.request.urlopen(url))
enabled = [r['check_code'] for r in data['rules'] if r['enabled']]
if not enabled:
    print('ERROR: No enabled rules found', file=sys.stderr)
    sys.exit(1)
print(','.join(enabled))
")

if [ -z "$CODES" ]; then
  echo "ERROR: Could not read rules from URL"
  exit 1
fi

echo "Running flake8 with enabled rules: $CODES"
flake8 --select="$CODES" \
    --max-complexity=10 \
    --exclude="planet_explorer/extlibs/*" \
    planet_explorer/
