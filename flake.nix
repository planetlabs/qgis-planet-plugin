{
  description = "NixOS developer environment for QGIS plugins.";
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    darglint-repo.url = "github:vikineema/darglint-nix";
  };
  outputs =
    {
      self,
      darglint-repo,
      nixpkgs,
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
      darglint = darglint-repo.packages.${system}.darglint;
      extraPythonPackages = ps: [
        ps.pyqtwebengine
        ps.jsonschema
        ps.debugpy
        ps.psutil
        ps.httpcore
        ps.anyio
      ];
      qgisWithExtras = pkgs.qgis.override {
        extraPythonPackages = extraPythonPackages;
      };
      qgisLtrWithExtras = pkgs.qgis-ltr.override {
        extraPythonPackages = extraPythonPackages;
      };

      # Common packages shared between all devShells (Qt-agnostic)
      makeCommonPackages =
        p: with p; [
          actionlint # for checking gh actions
          act # for running github actions locally
          bandit
          bearer
          chafa
          # p.codeql # Build time is too long
          cspell
          detect-secrets
          ffmpeg
          glogg
          gdb
          git
          glow # terminal markdown viewer
          gource # Software version control visualization
          gum # UX for TUIs
          isort
          jq
          markdownlint-cli
          nixfmt
          pipewire
          privoxy
          pyprof2calltree # needed to convert cprofile call trees into a format kcachegrind can read
          python3
          ripgrep
          shellcheck
          shfmt
          tailspin # Beautiful log tailing with syntax highlighting
          vim
          virtualenv
          vscode
          yamllint
          yamlfmt
          darglint
          (python3.withPackages (
            ps: with ps; [
              python
              setuptools
              wheel
              pytest
              pytest-qt
              black
              click # needed by black
              jsonschema
              pandas
              odfpy
              psutil
              httpx
              toml
              typer
              paver
              detect-secrets
              flake8
              # For autocompletion in vscode
              snakeviz # For visualising cprofiler outputs
              sqlfmt
              # This executes some shell code to initialize a venv in $venvDir before
              # dropping into the shell
              venvShellHook
              virtualenv
              # Those are dependencies that we would like to use from nixpkgs, which will
              # add them to PYTHONPATH and thus make them accessible from within the venv.
              debugpy
              numpy
              gdal
              pip
              pyqtwebengine
              pre-commit-hooks
            ]
          ))
        ];
      commonPackages = makeCommonPackages pkgs;

      # Qt5 packages for QGIS 3 LTR development
      # Note: kcachegrind is only available in Qt6, use .#qt6 devShell for profiling
      qt5Packages = with pkgs; [
        libsForQt5.qt5.qttools # includes designer
        qt5.qtbase
        qt5.qtlocation
        qt5.qtquickcontrols2
        qt5.qttools
        qt5.qtsvg
        (python3.withPackages (
          ps: with ps; [
            pyqt5
          ]
        ))
      ];

      # Qt6 packages for QGIS 4 development
      qt6Packages = with pkgs; [
        qt6.qtbase
        qt6.qttools # includes designer
        qt6.qtlocation
        qt6.qtdeclarative
        qt6.qtsvg
        kdePackages.kcachegrind
        (python3.withPackages (
          ps: with ps; [
            pyqt6
            qscintilla-qt6
          ]
        ))
      ];

      # Jupyter notebooks
      jupyterEnv = with pkgs; [
        (python3.withPackages (
          ps: with ps; [
            jupyterlab
            pillow
          ]
        ))
      ];
      precommitHook = ''
        pre-commit clean > /dev/null
        pre-commit install --install-hooks > /dev/null
        pre-commit run --all-files || true
      '';
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
      '';

    in
    {
      packages.${system} = {
        default = qgisWithExtras;
        qgis-ltr = qgisLtrWithExtras;
      };

      devShells.${system} = {
        # Default devShell uses Qt6 for QGIS 4 development
        default = pkgs.mkShell {
          name = "default";
          packages = commonPackages ++ qt6Packages;
          shellHook = ''
            echo "🔧 Using Qt6 devShell (for QGIS 4 development)"
            echo "   Use 'nix develop .#qt5' for QGIS 3 LTR development tools"
            echo ""
            export QTPOSITIONING="${pkgs.python3Packages.pyqt6}/${pkgs.python3.sitePackages}"
          ''
          + commonShellHook;
        };

        # Qt6 devShell for QGIS 4 development
        qt6 = pkgs.mkShell {
          name = "qt6";
          packages = commonPackages ++ qt6Packages;
          shellHook = ''
            echo "🔧 Using Qt6 devShell (for QGIS 4 development)"
            echo ""
            export QTPOSITIONING="${pkgs.python3Packages.pyqt6}/${pkgs.python3.sitePackages}"
            # Dynamically links the pipewire libraries so Qt can resolve the symbols
            export LD_LIBRARY_PATH="${pkgs.pipewire}/lib:$LD_LIBRARY_PATH"
          ''
          + commonShellHook;
        };

        pyqgis-qt6 = pkgs.mkShell {
          name = "pyqgis-qt6";
          packages = commonPackages ++ qt6Packages ++ [ qgisWithExtras ] ++ jupyterEnv;
          shellHook = ''
            echo "🔧 Using PyQGIS and Qt6 devShell (for QGIS 4 development)"
            echo ""
            export PYTHONPATH="${qgisWithExtras}/share/qgis/python:${qgisWithExtras}/${pkgs.python3.sitePackages}:$PYTHONPATH"
            export QTPOSITIONING="${pkgs.python3Packages.pyqt6}/${pkgs.python3.sitePackages}"
            export LD_LIBRARY_PATH="${pkgs.pipewire}/lib:$LD_LIBRARY_PATH"
          ''
          + commonShellHook;
        };

        # Qt5 devShell for QGIS 3 LTR development
        qt5 = pkgs.mkShell {
          name = "qt5";
          packages = commonPackages ++ qt5Packages;
          shellHook = ''
            echo "🔧 Using Qt5 devShell (for QGIS 3 LTR development)"
            echo ""
            export QTPOSITIONING="${pkgs.python3Packages.pyqt5}/${pkgs.python3.sitePackages}"
          ''
          + commonShellHook;
        };

        pyqgis-qt5 = pkgs.mkShell {
          name = "pyqgis-qt5";
          packages = commonPackages ++ qt5Packages ++ [ qgisLtrWithExtras ] ++ jupyterEnv;
          shellHook = ''
            echo "🔧 Using PyQGIS and Qt5 devShell (for QGIS 3 LTR development)"
            echo ""
            export PYTHONPATH="${qgisLtrWithExtras}/share/qgis/python:${qgisLtrWithExtras}/${pkgs.python3.sitePackages}:$PYTHONPATH"
            export QTPOSITIONING="${pkgs.python3Packages.pyqt5}/${pkgs.python3.sitePackages}"
            export LD_LIBRARY_PATH="${pkgs.pipewire}/lib:$LD_LIBRARY_PATH"
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
