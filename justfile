# This just file was built for Windows development
# for the plugin with commands expected to be run in Powershell 7.
set windows-shell := ["pwsh.exe", "-NoLogo", "-NoProfile", "-Command"]
py := "micromamba run -n qgis4-conda-forge python"

# List available recipes
default:
    @just --list

# Run all pre-commit checks
run-pre-commit:
    pre-commit clean
    pre-commit install --install-hooks
    pre-commit run --all-files

# Create the conda environment
create-conda-env:
    micromamba create -f ./qgis4-conda-forge-env.yaml -y

# Setup the plugin for use with QGIS4 in a conda environment.
setup-qgis4:
    {{py}} -m paver setup --clean
    if (Test-Path "$env:QGIS_PLUGIN_DIR\planet_explorer") { Remove-Item -Recurse -Force "$env:QGIS_PLUGIN_DIR\planet_explorer" }
    {{py}} -m paver install --pluginpath="$env:QGIS_PLUGIN_DIR"

# Start QGIS4 with the plugin profile
start-qgis4:
    micromamba run -n qgis4-conda-forge qgis --profile "$env:QGIS_PROFILE"
