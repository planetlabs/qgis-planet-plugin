#!/usr/bin/env bash
set -euo pipefail

# Startup script for VSCode with a custom profile and extensions

: "${REPO_ROOT_DIR:?Error: REPO_ROOT_DIR environment variable is not set.}"
: "${CONFIG_DIR:?Error: CONFIG_DIR environment variable is not set.}"
: "${LOGS_DIR:?Error: LOGS_DIR environment variable is not set.}"

# ----------------------------------------------
# User-adjustable parameters
# ----------------------------------------------

VSCODE_PROFILE="PLANET"
VSCODE_USER_DIR="$REPO_ROOT_DIR/.vscode"
VSCODE_EXT_DIR="$REPO_ROOT_DIR/.vscode-extensions"
EXTENSIONS_FILE="$CONFIG_DIR/vscode/extensions.json"
SETTINGS_FILE="$CONFIG_DIR/vscode/settings.json"
VSCODE_SETTINGS_FILE="$VSCODE_USER_DIR/settings.json"
LOG_FILE="$LOGS_DIR/vscode.log"

# ----------------------------------------------
# Functions
# ----------------------------------------------

launch_vscode() {
    code --user-data-dir="$VSCODE_USER_DIR" \
        --profile="${VSCODE_PROFILE}" \
        --extensions-dir="$VSCODE_EXT_DIR" "$@"
}

list_installed_extensions() {
    if [[ ! -d "$VSCODE_EXT_DIR" ]]; then
        return
    fi

    fd --hidden --no-ignore --max-depth 1 --min-depth 1 --type d --search-path "$VSCODE_EXT_DIR" | while read -r dir; do
        pkg="$dir/package.json"
        if [[ -f "$pkg" ]]; then
            name=$(jq -r '.name' <"$pkg")
            publisher=$(jq -r '.publisher' <"$pkg")
            echo "${publisher}.${name}" | tr '[:upper:]' '[:lower:]'
        fi
    done
}

read_recommended_extensions() {
    # Strip whole-line // comments (JSONC), extract recommendations, lowercase.
    sed -E 's#^[[:space:]]*//.*$##' "$EXTENSIONS_FILE" \
        | jq -r '.recommendations[]' \
        | tr '[:upper:]' '[:lower:]'
}

install_required_extensions() {
    echo "🗨️ Checking and installing required extensions..."

    if [[ ! -f "$EXTENSIONS_FILE" ]]; then
        echo "  ❌ Extensions file not found: $EXTENSIONS_FILE"
        exit 1
    fi

    local installed_exts
    installed_exts="$(list_installed_extensions)"

    while IFS= read -r ext || [[ -n "$ext" ]]; do
        [[ -z "$ext" ]] && continue

        if echo "$installed_exts" | grep -qx "$ext"; then
            echo "  ✅ Extension ${ext} already installed."
        else
            echo "  📦 Installing ${ext}..."
            if launch_vscode --install-extension "$ext" >>"$LOG_FILE" 2>&1; then
                installed_exts="$(list_installed_extensions)"
                if echo "$installed_exts" | grep -qx "$ext"; then
                    echo "  ✅ Successfully installed ${ext}."
                else
                    echo "  ❌ Failed to install ${ext} (not found after install)."
                    exit 1
                fi
            else
                echo "  ❌ Failed to install ${ext} (error during install). Check $LOG_FILE for details."
                exit 1
            fi
        fi
    done < <(read_recommended_extensions)
}

clean() {
    rm -rf "$VSCODE_USER_DIR" "$VSCODE_EXT_DIR"
}

print_help() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

This script sets up and launches VSCode with a custom profile and extensions for the intro-to-python-gis project.

Actions performed:
    - Checks for required files and directories
    - Ensures VSCode is installed
    - Initializes VSCode user and extension directories if needed
    - Installs all required VSCode extensions
    - Launches VSCode with the specified profile and directories

Options:
    --help                             Show this help message and exit
    --verbose                          Print final settings.json contents before launching VSCode
    --list-extensions                  List installed VSCode extensions
    --install-required-extensions      Install all required VSCode extensions
    --clean                            Remove the "$VSCODE_USER_DIR" and "$VSCODE_EXT_DIR" directories completely

EOF
}

# Parameter handler
for arg in "$@"; do
    case "$arg" in
        --help)
            print_help
            exit 0
            ;;
        --verbose)
            # Handled later in the script if needed
            ;;
        --install-required-extensions)
            install_required_extensions
            exit 0
            ;;
        --list-extensions)
            echo "Installed extensions:"
            list_installed_extensions
            exit 0
            ;;
        --clean)
            echo "Removing custom VSCode environments..."
            clean
            exit 0
            ;;
        *) ;;
    esac
done

# ----------------------------------------------
# Script starts here
# ----------------------------------------------

# Truncate the log file at the start
echo "🗨️ Truncating $LOG_FILE..."
: >"$LOG_FILE"

echo "🗨️ Checking VSCode is installed ..."
if ! command -v code &>/dev/null; then
    echo "  ❌ 'code' CLI not found. Please install VSCode and add 'code' to your PATH."
    exit 1
else
    echo "  ✅ VSCode found ok."
fi

echo "🗨️  Checking if VSCode has been run before..."
if [[ ! -d "$VSCODE_USER_DIR" ]]; then
    echo "  🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻🔻"
    echo "  ⭐️ It appears you have not run VSCode in this project before."
    echo "     After it opens, please close VSCode and then rerun this script"
    echo "     so that the extensions directory initialises properly."
    echo "  🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺🔺"
    mkdir -p "$VSCODE_USER_DIR"
    mkdir -p "$VSCODE_EXT_DIR"
    # Launch VSCode with the sandboxed environment
    launch_vscode .
    exit 1
else
    echo "  ✅ VSCode directory found from previous runs of code."
fi

# Automatically sync extensions on script run before boot
install_required_extensions

echo "🗨️ Launching VSCode..."
launch_vscode .

echo "🗨️ Checking if $VSCODE_SETTINGS_FILE exists..."

if [ -L "$VSCODE_SETTINGS_FILE" ]; then
    echo "Settings file $VSCODE_SETTINGS_FILE exists."
else
    ln -s "$SETTINGS_FILE" "$VSCODE_USER_DIR/settings.json"
    echo "Created new $VSCODE_SETTINGS_FILE file."
fi
