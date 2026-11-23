import json
import sys
import urllib.request

url = "https://raw.githubusercontent.com/qgis/QGIS-Plugins-Website/refs/heads/master/qgis-app/plugins/management/commands/data/bandit_rules.json"
data = json.load(urllib.request.urlopen(url))
enabled = [r["check_code"] for r in data["rules"] if r["enabled"]]
if not enabled:
    print("ERROR: No enabled rules found", file=sys.stderr)
    sys.exit(1)
print(",".join(enabled))
