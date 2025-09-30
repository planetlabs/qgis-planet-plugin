#!/usr/bin/env bash
echo "🪛 Running QGIS with the PLANET profile:"
echo "--------------------------------"
echo "Do you want to enable debug mode?"
choice=$(gum choose "🪲 Yes" "🐞 No")
case $choice in
    "🪲 Yes") developer_mode=1 ;;
    "🐞 No") developer_mode=0 ;;
esac

# Running on local used to skip tests that will not work in a local dev env
PLANET_LOG="$HOME/PLANET.log"
rm -f "$PLANET_LOG"
# This is the new way, using Ivan Mincis nix spatial project and a flake
# see flake.nix for implementation details
PLANET_LOG=${PLANET_LOG} \
    PLANET_DEBUG="${developer_mode}" \
    RUNNING_ON_LOCAL=1 \
    nix run .#default -- --profile PLANET
