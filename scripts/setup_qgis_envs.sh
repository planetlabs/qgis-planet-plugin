#!/usr/bin/env bash
set -euo pipefail

echo ""
echo "Setting up QGIS env variables ..."

# Locate QGIS binary
if ! qgis_bin=$(command -v qgis); then
    echo "Error: QGIS binary not found!"
    exit 1
fi
qgis_bin=$(readlink -f "$qgis_bin")

# Extract the Nix store path (removing /bin/qgis)
qgis_prefix=$(dirname "$(dirname "$qgis_bin")")

# Construct the correct QGIS Python path
qgis_python_path="$qgis_prefix/share/qgis/python"

# Check if the Python directory exists
if [[ ! -d "$qgis_python_path" ]]; then
    echo "Error: QGIS Python path not found at $qgis_python_path"
    exit 1
fi

qgis_version=$(qgis --version 2>/dev/null | awk '{print $2}' | cut -d- -f1)
qgis_version_major=${qgis_version%%.*}

if [ "$qgis_version_major" -ge 4 ]; then
    qgis_custom_config_path="$HOME/.local/share/QGIS/QGIS4"
else
    qgis_custom_config_path="$HOME/.local/share/QGIS/QGIS3"
fi

qgis_profile_dir="$qgis_custom_config_path/profiles/$QGIS_PROFILE_NAME"
qgis_pluginpath="$qgis_profile_dir/python/plugins"
export QGIS_PLUGIN_DIR="$qgis_pluginpath"

echo "✅ QGIS env variables setup complete."
echo ""

set +euo pipefail
