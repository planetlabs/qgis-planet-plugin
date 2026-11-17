#!make
SHELL := /usr/bin/env bash

# This Makefile is intended for use with the Nix \
development environment defined in the flake.nix

activate-env:
	nix develop .#pyqgis-qt6
	# nix develop .#pyqgis-qt5

lint:
	@echo "🎨 Formatting shell scripts to Google Style Guide ..."
	fd -t f -e sh -e bash -e zsh . scripts -X shfmt -i 2 -ci -bn -w
	@echo "🐚 ShellCheck - scripts ..."
	fd -t f -e sh -e bash -e zsh . scripts -X shellcheck
	@echo "🖤 black"
	black planet_explorer/ --exclude planet_explorer/extlibs/
	@echo "📦 isort - sort Python imports"
	isort planet_explorer/ --skip planet_explorer/extlibs/

start-antigravity:
	scripts/antigravity.sh

start-vscode:
	scripts/code_.sh

setup-qgis4:
	paver setup --clean
	QGIS4_PLUGIN_DIR="$$HOME/.local/share/QGIS/QGIS4/profiles/PLANET/python/plugins"; \
	rm -rf "$$QGIS4_PLUGIN_DIR/planet_explorer"; \
	paver install --pluginpath="$$QGIS4_PLUGIN_DIR"

setup-qgis3:
	paver setup
	QGIS3_PLUGIN_DIR="$$HOME/.local/share/QGIS/QGIS3/profiles/PLANET/python/plugins"; \
	rm -rf "$$QGIS3_PLUGIN_DIR/planet_explorer"
	paver install --pluginpath="$$QGIS3_PLUGIN_DIR"

start-qgis:
	# nix run .#qgis --print-build-logs
	scripts/start_qgis.sh

start-qgis-ltr:
	# nix run .#qgis-ltr --print-build-logs
	scripts/start_qgis_ltr.sh

start-jupyterlab:
	nohup jupyter lab --port 8888 --no-browser > jupyter.log 2>&1 &
	@echo "Jupyter Lab started with PID: $$!"
	@echo "View logs: tail -f jupyter.log"

stop-jupyterlab:
	pkill -f "jupyter lab"
	@echo "Jupyter Lab stopped"

logs-jupyterlab:
	tail -f jupyter.log

status-jupyterlab:
	ps aux | grep jupyter | grep -v grep

link-notebooks:
	ln -s ../planet-draft-notebooks testnotebooks

run-pre-commit:
	@echo "Running pre-commit checks..."
	pre-commit clean > /dev/null
	pre-commit install --install-hooks > /dev/null
	pre-commit run --all-files || true
	@echo "Pre-commit checks complete. Happy coding! 🚀"

clean-setup:
	rm -rf .venv/
	rm -rf planet_explorer/extlibs/

QGIS_TEST_VERSION=4.0.3
run-qgis-docker:
	docker run --rm \
		-e QT_QPA_PLATFORM=offscreen \
		-v "${PWD}:/tests_directory" \
		-w /tests_directory \
		"qgis/qgis:${QGIS_TEST_VERSION}-questing" \
		sh -lc 'LANG=C.utf8 LC_ALL=C.utf8 DISPLAY=:0 qgis --noversioncheck --nologo --version-migration --code planet_explorer/tests/install_plugin.py'

qgis-shell:
	docker exec -it qgis /bin/bash
