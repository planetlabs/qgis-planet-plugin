#!/usr/bin/env bash
set -euo pipefail

: "${ENV_FILE:?Error: ENV_FILE environment variable is not set.}"
: "${VIRTUAL_ENV:?Error: VIRTUAL_ENV environment variable is not set.}"
: "${QGIS_PREFIX_PATH:?Error: QGIS_PREFIX_PATH environment variable is not set.}"
: "${QGIS_PYTHON_PATH:?Error: QGIS_PYTHON_PATH environment variable is not set.}"
: "${QGIS_CUSTOM_CONFIG_PATH:?Error: QGIS_CUSTOM_CONFIG_PATH environment variable is not set.}"
: "${QGIS_PROFILE_DIR:?Error: QGIS_PROFILE_DIR environment variable is not set.}"
: "${QGIS_PLUGINPATH:?Error: QGIS_PLUGINPATH environment variable is not set.}"
: "${QGIS_PLUGIN_DIR:?Error: QGIS_PLUGIN_DIR environment variable is not set.}"
: "${QGIS_PROFILE_NAME:?Error: QGIS_PLUGIN_DIR environment variable is not set.}"

echo "Writing environment variables to $ENV_FILE"
: >"$ENV_FILE"

# List of variables to export to the env file
VARS=(
    ENV_FILE
    VIRTUAL_ENV
    QGIS_PREFIX_PATH
    QGIS_PYTHON_PATH
    QGIS_CUSTOM_CONFIG_PATH
    QGIS_PROFILE_DIR
    QGIS_PLUGINPATH
    QGIS_PROFILE_NAME
)

for name in "${VARS[@]}"; do
    # skip unset variables instead of failing under `set -u`
    if [[ -v $name ]]; then
        printf '%s=%s\n' "$name" "${!name}" >>"$ENV_FILE"
    else
        echo "⚠️ $name is not set, skipping"
    fi
done

printf "... ✅ Done! \n"
