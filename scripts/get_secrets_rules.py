import requests

url = "https://raw.githubusercontent.com/qgis/QGIS-Plugins-Website/refs/heads/master/qgis-app/plugins/management/commands/data/secrets_rules.json"
data = requests.get(url).json()
disabled = [r["check_code"] for r in data["rules"] if not r["enabled"]]
print(",".join(disabled), " ".join(f"--disable-plugin {code}" for code in disabled))
