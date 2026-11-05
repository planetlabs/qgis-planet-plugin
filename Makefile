#!make
SHELL := /usr/bin/env bash

# This Makefile is intended for use with the Nix \
development environment defined in the flake.nix

.DEFAULT_GOAL := help

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST) | sort

# ------------------------------------------------------------------------------
# Targets with '##' comments will automatically appear in 'make help'
# ------------------------------------------------------------------------------

## Linting and security checks

activate-env: ## Enter the pyqgis4-qt6 dev shell
	@-nix develop .#pyqgis4-qt6

activate-ltr-env: ## Enter the pyqgis4-qt6 dev shell
	@-nix develop .#pyqgis3-qt5

lint-format: run-pre-commit ## Format and lint all files

general-lint-fix: ## Fix end of files and trailing white space.
	@pre-commit run end-of-file-fixer --all-files
	@pre-commit run trailing-whitespace --all-files

yaml-lint: ## Lint YAML files
	@pre-commit run check-yaml --all-files
	@pre-commit run yamllint --all-files

json-lint-fix: ## JSON checks and formatting only
	@pre-commit run biome-json-jsonc --all-files

rm-core-files: ## Remove core files
	@scripts/rm_core_files.sh

md-lint-fix: ## Lint and format markdown files using markdownlint
	@pre-commit run markdownlint --all-files

md-spell-check: ## Spell check markdown files using cspell
	@pre-commit run cspell --all-files

nix-lint-fix: ## Lint and format .nix files
	@pre-commit run nixfmt --all-files

sh-lint-fix: ## Lint and format shell scripts using shfmt and shellcheck
	@pre-commit run shfmt-scripts --all-files
	@pre-commit run shellcheck-scripts --all-files

actions-lint-fix: ## Lint and format github action workflow files.
	@pre-commit run actionlint --all-files

toml-lint-fix: ## Lint and format TOML files using taplo
	@pre-commit run taplo-fmt --all-files

make-lint-fix: ## Format and validate Makefiles
	@pre-commit run mbake-format --all-files
	@pre-commit run mbake-validate --all-files

py-lint-fix: ## Lint and format python files.
	@pre-commit run ruff-formatter --all-files
	@pre-commit run flake8 --all-files
	@pre-commit run ensure-google-docstrings --all-files

security-checks: ## Run QGIS plugins security scanning
	@pre-commit run bearer-plugin --all-files
	@pre-commit run bandit --all-files
	@pre-commit run detect-secrets --all-files
	@pre-commit run flake8 --all-files
	@pre-commit run filecheck --all-files

run-pre-commit: ## Run all pre-commit checks
	@printf "Running pre-commit checks ... \n"
	pre-commit clean
	pre-commit install --install-hooks
	pre-commit run --all-files
	@printf "Pre-commit checks complete. Happy coding! 🚀 \n"

## General cross-service targets

update-secrets-baseline: ## Update the baseline file for detect-secrets
	@scripts/update_secrets_baseline.sh

create-pr: ## Create PR to upstream from current branch
	@gh pr create --repo timlinux/Fork-QGIS-Planet-Plugin --web        # describe, link the issue

setup-env-file: ## Write a selection of environment variables to env file
	@scripts/setup_env_file.sh

## Plugin specific targets

clean-python-env: ## Remove the virtual environment if it exists and the extlibs
	@if [ -n "$$VIRTUAL_ENV" ] && [ -d "$$VIRTUAL_ENV" ]; then \
		rm -rf "$$VIRTUAL_ENV"; \
		printf "Virtual environment removed: $$VIRTUAL_ENV\n"; \
	fi
	@if [ -d planet_explorer/extlibs ]; then \
		rm -rf planet_explorer/extlibs; \
		printf "Plugin extlibs dir removed: planet_explorer/extlibs\n"; \
	fi

zip-plugin: ## Package the planet plugin into a zip file.
	paver package

plugin-zip-size: ## Get the size of the plugin zip file.
	#$(MAKE) zip-plugin
	@FILE="planet_explorer.zip"; \
	IF_OVER=$$(fd -F --max-depth 1 --size +25m "$$FILE"); \
	SIZE=$$(du -h "$$FILE" | cut -f1); \
	if [ -n "$$IF_OVER" ]; then \
		echo "WARNING: $$FILE is $$SIZE (exceeds 25MB limit!)"; \
	else \
		echo "OK: $$FILE size is $$SIZE"; \
	fi

update-resources: # Requires the pyqgis3-qt5 flake env
	@if echo "$$name" | grep -q "qt5"; then \
		pyrcc5 planet_explorer/resources/resources.qrc -o planet_explorer/resources/resources.py; \
	else \
		echo "Error: Requires resources build requires qt5 environment to run.""; \
	fi

## QGIS targets

setup-qgis: ## Fresh install of the plugin into QGIS
	paver setup --clean
	rm -rf "$(QGIS_PLUGIN_DIR)/planet_explorer"
	paver install --pluginpath="$(QGIS_PLUGIN_DIR)"

start-qgis: ## Start QGIS
	@if echo "$$name" | grep -q "qt5"; then \
		echo "Starting QGIS LTR 3.44"; \
		scripts/start_qgis_ltr.sh; \
	else \
		echo "Starting QGIS 4.2"; \
		scripts/start_qgis.sh; \
	fi

QGIS_TEST_VERSION = 4.0.3
run-qgis-docker:
	docker run --rm \
		-e QT_QPA_PLATFORM=offscreen \
		-v "${PWD}:/tests_directory" \
		-w /tests_directory \
		"qgis/qgis:${QGIS_TEST_VERSION}-questing" \
		sh -lc 'LANG=C.utf8 LC_ALL=C.utf8 DISPLAY=:0 qgis --noversioncheck --nologo --version-migration --code planet_explorer/tests/install_plugin.py'

qgis-shell:
	docker exec -it qgis /bin/bash

## VS Code targets

start-vscode: ## Start VS Code in the Nix environment
	scripts/vscode.sh

clean-vscode: ## Clean VS Code settings and extensions
	@printf "Cleaning VS Code settings and extensions ... \n"
	@rm -rf .vscode 2>/dev/null || true
	@rm -rf .vscode-extensions 2>/dev/null || true
	@printf "... ✅ Done! \n"

## Testing
setup-notebooks: # Side load draft notebooks
	@ln -sfn ../planet-draft-notebooks testnotebooks

##  Github Workflows

QGIS_TEST_VERSION = 3.44
test-workflow:
	GITHUB_WORKSPACE=${REPO_ROOT_DIR} QGIS_TEST_VERSION=${QGIS_TEST_VERSION} \
		docker compose -f .docker/docker-compose.gh.yml build qgis
	GITHUB_WORKSPACE=${REPO_ROOT_DIR} QGIS_TEST_VERSION=${QGIS_TEST_VERSION} \
		docker compose -f .docker/docker-compose.gh.yml run qgis /usr/src/.docker/run-docker-tests.sh

test-shell:
	GITHUB_WORKSPACE=${REPO_ROOT_DIR} QGIS_TEST_VERSION=${QGIS_TEST_VERSION} \
		docker compose -f .docker/docker-compose.gh.yml build qgis
	GITHUB_WORKSPACE=${REPO_ROOT_DIR} QGIS_TEST_VERSION=${QGIS_TEST_VERSION} \
		docker compose -f .docker/docker-compose.gh.yml run --rm qgis /bin/bash
