import json
import urllib.request

url = "https://raw.githubusercontent.com/qgis/QGIS-Plugins-Website/refs/heads/master/qgis-app/plugins/management/commands/data/file_analysis_rules.json"
data = json.load(urllib.request.urlopen(url))
enabled = [r["check_code"] for r in data["rules"] if r["enabled"]]
print(",".join(enabled))
