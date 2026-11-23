#!/usr/bin/env bash

# Sets up repo-local path variables and the Python virtual environment.
# Intended to be sourced (e.g. from a flake shellHook), not executed.

#
# Note:
# - Direct references to `pkgs` should remain in flake shell hooks.
# - This script only establishes repo-local path variables.

echo ""
echo "Setting up repo-local path variables ..."
scripts_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export SCRIPTS_DIR="$scripts_dir"

repo_root_dir="$(dirname "$SCRIPTS_DIR")"
export REPO_ROOT_DIR="$repo_root_dir"

# Where to keep log files for various services.
export LOGS_DIR="$REPO_ROOT_DIR/.logs"
mkdir -p "$LOGS_DIR"

# Where to keep config files for services.
export CONFIG_DIR="$REPO_ROOT_DIR/.config"

# Set path to env file
# Note: .env file not sourced as dotenv in flake
# is expected to do so.
export ENV_FILE="$REPO_ROOT_DIR/.env"

# Setup the python virtual environment
echo "Setting up python virtual environment ..."
export VIRTUAL_ENV="$REPO_ROOT_DIR/.venv"
pip_log="$LOGS_DIR/.pip-install.log"

if [ ! -d "$VIRTUAL_ENV" ]; then
    python3 -m venv "$VIRTUAL_ENV"
fi

echo "Virtual env python version: $("$VIRTUAL_ENV/bin/python" --version 2>&1)"
env -u PYTHONPATH "$VIRTUAL_ENV/bin/python" -m pip install --upgrade pip

requirements_file="$REPO_ROOT_DIR/requirements.txt"
stamp_file="$VIRTUAL_ENV/.requirements.sha256"

if [ -f "$requirements_file" ]; then
    current_hash="$(sha256sum "$requirements_file" | cut -d' ' -f1)"
    stored_hash="$(cat "$stamp_file" 2>/dev/null || true)"

    # Only re-install if requirements.txt changed or hasn't been recorded yet
    if [ "$current_hash" != "$stored_hash" ]; then
        if env -u PYTHONPATH "$VIRTUAL_ENV/bin/python" -m pip install -r "$requirements_file" 2>&1 | tee "$pip_log"; then
            echo "$current_hash" >"$stamp_file"
        else
            echo "❌ Pip install failed. See $pip_log for details."
            exit 1
        fi
    else
        echo "requirements.txt unchanged, skipping pip install"
    fi
else
    echo "No requirements.txt found, skipping pip install."
fi

#shellcheck source=/dev/null
source "$VIRTUAL_ENV/bin/activate"

echo "✅ Repo-local path variables and Python virtual venv setup complete."
echo ""
