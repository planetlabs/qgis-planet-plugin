#!/usr/bin/env bash

echo "🪛 Running QGIS with the PLANET profile:"
echo "--------------------------------"

echo "Do you want to enable debug mode?"
choice=$(gum choose "🪲 Yes" "🐞 No")
case $choice in
"🪲 Yes") developer_mode=1 ;;
"🐞 No") developer_mode=0 ;;
esac

echo "Do you want to enable experimental features?"
choice=$(gum choose "🪲 Yes" "🐞 No")
case "$choice" in
  "🪲 Yes") PLANET_EXPERIMENTAL=1 ;;
  "🐞 No") PLANET_EXPERIMENTAL=0 ;;
esac

# Running on local used to skip tests that will not work in a local dev env
PLANET_LOG=$HOME/PLANET2.log
PLANET_TEST_DIR="$(pwd)/test" # Set test directory relative to project root

rm -f "$PLANET_LOG"

# This is the new way, using Ivan Mincis nix spatial project and a flake
# see flake.nix for implementation details
# Both PLANET_* and PLANET_* env vars are set for backward compatibility
# QT_QPA_PLATFORM flag forces it to run under x11 protocol
PLANET_DEBUG="${developer_mode}" \
PLANET_EXPERIMENTAL="${PLANET_EXPERIMENTAL}" \
PLANET_TEST_DIR="${PLANET_TEST_DIR}" \
PLANET_LOG="${PLANET_LOG}" \
RUNNING_ON_LOCAL=1 \
QT_QPA_PLATFORM=xcb \
nix run .#qgis-ltr -- --profile PLANET
