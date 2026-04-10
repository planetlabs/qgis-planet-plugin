{
  description = "NixOS developer environment for QGIS plugins.";

  inputs.geospatial.url = "github:imincik/geospatial-nix.repo";
  inputs.nixpkgs.follows = "geospatial/nixpkgs";

  outputs =
    {
      self,
      geospatial,
      nixpkgs,
    }:
    let
      system = "x86_64-linux";
      profileName = "PLANET";
      pkgs = import nixpkgs {
        inherit system;
        config = {
          allowUnfree = true;
          permittedInsecurePackages = [
            "qtwebengine-5.15.19"
          ];
        };
      };
      extraPythonPackages-qgis3 = ps: [
        ps.jsonschema
        ps.debugpy
        ps.psutil
      ];
      extraPythonPackages-qgis4 = ps: [
        ps.jsonschema
        ps.debugpy
        ps.psutil
      ];
      qgisWithExtras = geospatial.packages.${system}.qgis.override {
        extraPythonPackages = extraPythonPackages-qgis4;
      };
      qgisLtrWithExtras = geospatial.packages.${system}.qgis-ltr.override {
        extraPythonPackages = extraPythonPackages-qgis3;
      };

      # Common packages shared between all devShells (Qt-agnostic)
      commonPackages = [
        pkgs.chafa
        pkgs.ffmpeg
        pkgs.gdb
        pkgs.git
        pkgs.glow # terminal markdown viewer
        pkgs.gource # Software version control visualization
        pkgs.gum # UX for TUIs
        pkgs.jq
        pkgs.nixfmt-rfc-style
        pkgs.pre-commit
        pkgs.pyprof2calltree # needed to convert cprofile call trees into a format kcachegrind can read
        pkgs.python3
        pkgs.tailspin # Beautiful log tailing with syntax highlighting
        pkgs.vim
        pkgs.virtualenv
        pkgs.vscode
        pkgs.privoxy
        (pkgs.python3.withPackages (ps: [
          ps.python
          ps.pip
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
          ps.pyqt5-stubs # For autocompletion in vscode
          ps.debugpy
          ps.numpy
          ps.gdal
          ps.snakeviz # For visualising cprofiler outputs
        ]))
      ];

      # Qt5 packages for QGIS 3 LTR development
      # Note: kcachegrind is only available in Qt6, use .#qt6 devShell for profiling
      qt5Packages = [
        pkgs.qt5.qtbase
        pkgs.libsForQt5.qt5.qttools # includes designer
        pkgs.qt5.qtlocation
        pkgs.qt5.qtquickcontrols2
        pkgs.qt5.qtsvg
      ];

      # Qt6 packages for QGIS 4 development
      qt6Packages = [
        pkgs.qt6.qtbase
        pkgs.qt6.qttools # includes designer
        pkgs.qt6.qtlocation
        pkgs.qt6.qtdeclarative
        pkgs.qt6.qtsvg
        pkgs.kdePackages.kcachegrind
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
        # Default devShell uses Qt5 for QGIS 3 LTR development (most stable)
        default = pkgs.mkShell {
          packages = commonPackages ++ qt5Packages;
          shellHook = ''
            echo "🔧 Using Qt5 devShell (for QGIS 3 LTR development)"
            echo "   Use 'nix develop .#qt6' for QGIS 4/Qt6 development tools"
            echo ""
          ''
          + commonShellHook;
        };

        # Qt5 devShell for QGIS 3 LTR development
        qt5 = pkgs.mkShell {
          packages = commonPackages ++ qt5Packages;
          shellHook = ''
            echo "🔧 Using Qt5 devShell (for QGIS 3 LTR development)"
            echo ""
          ''
          + commonShellHook;
        };

        # Qt6 devShell for QGIS 4 development
        qt6 = pkgs.mkShell {
          packages = commonPackages ++ qt6Packages;
          shellHook = ''
            echo "🔧 Using Qt6 devShell (for QGIS 4 development)"
            echo ""
          ''
          + commonShellHook;
        };
      };

      apps.${system} = {
        qgis = {
          type = "app";
          program = "${pkgs.writeShellScript "qgis-with-profile" ''
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
