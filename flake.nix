{
  description = "NixOS developer environment for QGIS plugins.";
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    nixpkgs-unstable.url = "github:NixOS/nixpkgs/nixos-unstable";
    darglint-repo.url = "github:vikineema/darglint-nix";
  };
  outputs =
    {
      self,
      darglint-repo,
      nixpkgs,
      nixpkgs-unstable,
      ...
    }@inputs:
    let
      system = "x86_64-linux";
      profileName = "PLANET";
      pkgs = import nixpkgs {
        inherit system;
        config = {
          allowUnfree = true;
        };
      };
      pkgs-unstable = import nixpkgs-unstable {
        inherit system;
        config = {
          allowUnfree = true;
        };
      };
      darglint = darglint-repo.packages.${system}.darglint;
      extraPythonPackages = ps: [
        ps.pyqtwebengine
        ps.jsonschema
        ps.debugpy
        ps.psutil
      ];

      qgisWithExtras = pkgs-unstable.qgis.override {
        extraPythonPackages = extraPythonPackages;
      };
      qgisLtrWithExtras = pkgs.qgis-ltr.override {
        extraPythonPackages = extraPythonPackages;
      };

      # Common packages shared between all devShells (Qt-agnostic)
      makeCommonPackages = p: [
        p.actionlint # for checking gh actions
        p.act # for running github actions locally
        p.bandit
        p.bearer
        p.chafa
        p.codeql
        p.cspell
        p.detect-secrets
        p.ffmpeg
        p.glogg
        p.gdb
        p.git
        p.glow # terminal markdown viewer
        p.gource # Software version control visualization
        p.gum # UX for TUIs
        p.isort
        p.jq
        p.markdownlint-cli
        p.nixfmt
        p.privoxy
        p.pyprof2calltree # needed to convert cprofile call trees into a format kcachegrind can read
        p.python3
        p.shellcheck
        p.shfmt
        p.tailspin # Beautiful log tailing with syntax highlighting
        p.vim
        p.virtualenv
        p.vscode
        p.yamllint
        p.yamlfmt
        darglint
        (p.python3.withPackages (ps: [
          ps.python
          ps.setuptools
          ps.wheel
          ps.pytest
          ps.pytest-qt
          ps.black
          ps.click # needed by black
          ps.jsonschema
          ps.pandas
          ps.odfpy
          ps.psutil
          ps.httpx
          ps.toml
          ps.typer
          ps.paver
          ps.detect-secrets
          ps.flake8
          # For autocompletion in vscode
          ps.snakeviz # For visualising cprofiler outputs
          ps.sqlfmt
          # This executes some shell code to initialize a venv in $venvDir before
          # dropping into the shell
          ps.venvShellHook
          ps.virtualenv
          # Those are dependencies that we would like to use from nixpkgs, which will
          # add them to PYTHONPATH and thus make them accessible from within the venv.
          ps.debugpy
          ps.numpy
          ps.gdal
          ps.pip
          ps.pyqtwebengine
          ps.pre-commit-hooks
          # darglint
        ]))
      ];
      commonPackages = makeCommonPackages pkgs;
      commonPackages-unstable = makeCommonPackages pkgs-unstable;

      # Qt5 packages for QGIS 3 LTR development
      # Note: kcachegrind is only available in Qt6, use .#qt6 devShell for profiling
      qt5Packages = [
        pkgs.libsForQt5.kcachegrind
        #pkgs.libsForQt5.qt5.qttools # includes designer
        pkgs.qt5.full # so we get designer
        pkgs.qt5.qtbase
        pkgs.qt5.qtlocation
        pkgs.qt5.qtquickcontrols2
        pkgs.qt5.qttools
        pkgs.qt5.qtsvg
        (pkgs.python3.withPackages (ps: [
          ps.pyqt5
          ps.pyqt5-stubs # For autocompletion in vscode
        ]))
      ];

      # Qt6 packages for QGIS 4 development
      qt6Packages = [
        pkgs-unstable.qt6.qtbase
        pkgs-unstable.qt6.qttools # includes designer
        pkgs-unstable.qt6.qtlocation
        pkgs-unstable.qt6.qtdeclarative
        pkgs-unstable.qt6.qtsvg
        pkgs-unstable.kdePackages.kcachegrind
        (pkgs-unstable.python3.withPackages (ps: [
          ps.pyqt6
          ps.qscintilla-qt6
        ]))
      ];

      commonShellHook = ''
        unset SOURCE_DATE_EPOCH

        # Create a virtual environment in .venv if it doesn't exist
        if [ ! -d ".venv" ]; then
          python -m venv .venv
        fi

        # Activate the virtual environment
        source .venv/bin/activate

        # Upgrade pip and install packages from requirements.txt if it exists
        pip install --upgrade pip > /dev/null
        if [ -f requirements.txt ]; then
          echo "Installing Python requirements from requirements.txt..."
          pip install -r requirements.txt > .pip-install.log 2>&1
          if [ $? -ne 0 ]; then
            echo "❌ Pip install failed. See .pip-install.log for details."
          fi
        else
          echo "No requirements.txt found, skipping pip install."
        fi

        echo "-----------------------"
        echo "🌈 Your Dev Environment is prepared."
        echo "To run QGIS with your profile, use one of these commands:"
        echo ""
        echo "  nix run .#qgis        # QGIS 4 (Qt6)"
        echo "  nix run .#qgis-ltr    # QGIS 3 LTR (Qt5)"
        echo ""
        echo " Or use the helper scripts:"
        echo " scripts/start_qgis.sh      # QGIS 4 (Qt6)"
        echo " scripts/start_qgis_ltr.sh  # QGIS 3 LTR (Qt5)"
        echo ""
        echo "📒 Note:"
        echo "-----------------------"
        echo "We provide a ready-to-use"
        echo "VSCode environment which you"
        echo "can start like this:"
        echo ""
        echo "scripts/vscode.sh"
        echo "-----------------------"
        echo "If you want to test the plugin behind an http proxy"
        echo "we provide a script to run privoxy."
        echo "🛡️  To start the proxy (Privoxy), run:"
        echo "   ./scripts/privoxy.sh start"
        echo "🛑  To stop the proxy, run:"
        echo "   ./scripts/privoxy.sh stop"
        echo "-----------------------"
        echo ""
        pre-commit clean > /dev/null
        pre-commit install --install-hooks > /dev/null
        pre-commit run --all-files || true
      '';

    in
    {
      packages.${system} = {
        default = qgisWithExtras;
        qgis-ltr = qgisLtrWithExtras;
      };

      devShells.${system} = {
        # Default devShell uses Qt6 for QGIS 4 development
        default = pkgs-unstable.mkShell {
          packages = commonPackages-unstable ++ qt6Packages;
          shellHook = ''
            echo "🔧 Using Qt6 devShell (for QGIS 4 development)"
            echo "   Use 'nix develop .#qt5' for QGIS 3 LTR development tools"
            echo ""
            export QTPOSITIONING="${pkgs-unstable.python3Packages.pyqt6}/${pkgs-unstable.python3.sitePackages}"
          ''
          + commonShellHook;
        };

        # Qt6 devShell for QGIS 4 development
        qt6 = pkgs-unstable.mkShell {
          packages = commonPackages-unstable ++ qt6Packages;
          shellHook = ''
            echo "🔧 Using Qt6 devShell (for QGIS 4 development)"
            echo ""
            export QTPOSITIONING="${pkgs-unstable.python3Packages.pyqt6}/${pkgs-unstable.python3.sitePackages}"
          ''
          + commonShellHook;
        };

        pyqgis-qt6 = pkgs-unstable.mkShell {
          packages = commonPackages-unstable ++ qt6Packages ++ [ qgisWithExtras ];
          shellHook = ''
            echo "🔧 Using PyQGIS and Qt6 devShell (for QGIS 4 development)"
            echo ""
            export PYTHONPATH="${qgisWithExtras}/share/qgis/python:${qgisWithExtras}/${pkgs-unstable.python3.sitePackages}:$PYTHONPATH"
          ''
          + commonShellHook;
        };

        # Qt5 devShell for QGIS 3 LTR development
        qt5 = pkgs.mkShell {
          packages = commonPackages ++ qt5Packages;
          shellHook = ''
            echo "🔧 Using Qt5 devShell (for QGIS 3 LTR development)"
            echo ""
            export QTPOSITIONING="${pkgs.python3Packages.pyqt5}/${pkgs.python3.sitePackages}"
          ''
          + commonShellHook;
        };

      };
      apps.${system} = {
        qgis = {
          type = "app";
          program = "${pkgs-unstable.writeShellScript "qgis-with-profile" ''
            exec ${qgisWithExtras}/bin/qgis --profile ${profileName} "$@"
          ''}";
        };
        qgis-ltr = {
          type = "app";
          program = "${pkgs.writeShellScript "qgis-ltr-with-profile" ''
            exec ${qgisLtrWithExtras}/bin/qgis --profile ${profileName} "$@"
          ''}";
        };
      };
    };
}
