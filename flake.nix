{
  description = "NixOS developer environment for the Planet QGIS plugin.";
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
          allowUnfree = false;
          allowUnfreePredicate =
            pkg:
            builtins.elem (nixpkgs-unstable.lib.getName pkg) [
              "bearer"
            ];
        };
      };
      pkgsUnstable = import nixpkgs-unstable {
        inherit system;
        config = {
          allowUnfree = false;
        };
      };
      darglint = darglint-repo.packages.${system}.darglint;
      # Common python for all package groups
      python = pkgs.python313;
      pythonPkgs = python.pkgs;
      # Split packages into groups for better tracking
      lintersFormatters = with pkgs; [
        actionlint
        biome
        cspell
        darglint
        jq
        markdownlint-cli
        mbake
        nixfmt
        pre-commit
        pythonPkgs.pre-commit-hooks
        ruff
        shellcheck
        shfmt
        taplo
        yamllint
      ];
      devUtils = with pkgs; [
        act
        gdb
        gh
        git
        glogg
        glow
        gource
        gum
        pyprof2calltree
        ripgrep
        tailspin
      ];
      qgisPlanetDeps = with pkgs; [
        pipewire
        privoxy
        pythonPkgs.httpx
        pythonPkgs.paver
      ];
      qgisPluginsSecurity = with pkgs; [
        bandit
        bearer
        detect-secrets
        fd
        pythonPkgs.flake8
        pythonPkgs.requests
      ];
      # Extra python packages to be made available to QGIS
      qgisCommonExtraPythonPackages =
        ps: with ps; [
          anyio
          debugpy
          httpcore
          jsonschema
          pip
          psutil
        ];
      qgisLtrWithExtras = pkgs.qgis-ltr.override {
        extraPythonPackages = ps: (qgisCommonExtraPythonPackages ps) ++ [ ps.pyqtwebengine ];
      };
      qgisWithExtras = pkgs.qgis.override {
        extraPythonPackages = ps: (qgisCommonExtraPythonPackages ps) ++ [ ps.pyqt6-webengine ];
      };
      # Qt5 packages for QGIS 3 LTR development
      # Note: kcachegrind is only available in Qt6, use .#qt6 devShell for profiling
      qt5Packages = with pkgs; [
        libsForQt5.qt5.qttools # includes designer
        qt5.qtbase
        qt5.qtlocation
        qt5.qtquickcontrols2
        qt5.qttools
        qt5.qtsvg
        (python.withPackages (
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
        (python.withPackages (
          ps: with ps; [
            pyqt6
            qscintilla-qt6
          ]
        ))
      ];
      commonLibPath = pkgs.lib.makeLibraryPath [
        # Dynamically links the pipewire libraries so Qt can resolve the symbols
        pkgs.pipewire
      ];
      qtPositioningHook = pyqt: ''
        export QTPOSITIONING="${pyqt}/${python.sitePackages}"
      '';
      qt6Positioning = qtPositioningHook pythonPkgs.pyqt6;
      qt5Positioning = qtPositioningHook pythonPkgs.pyqt5;
      commonPackages = lintersFormatters ++ qgisPluginsSecurity ++ devUtils ++ qgisPlanetDeps;
      commonShellHook = ''
        export QGIS_PROFILE_NAME=${profileName}
        source ./scripts/setup_dev_env.sh
        source ./scripts/setup_qgis_envs.sh

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

      devShells.${system} = rec {
        # Qt6 devShell for QGIS 4 development
        qt6 = pkgs.mkShell {
          name = "qt6";
          packages = commonPackages ++ qt6Packages;
          LD_LIBRARY_PATH = commonLibPath;
          shellHook = ''
            echo "🔧 Using Qt6 devShell (for QGIS 4 development)"
          ''
          + qt6Positioning
          + commonShellHook;
        };

        # Qt5 devShell for QGIS 3 LTR development
        qt5 = pkgs.mkShell {
          name = "qt5";
          packages = commonPackages ++ qt5Packages;
          LD_LIBRARY_PATH = commonLibPath;
          shellHook = ''
            echo "🔧 Using Qt5 devShell (for QGIS 3 LTR development)"
          ''
          + qt5Positioning
          + commonShellHook;
        };

        pyqgis3-qt5 = pkgs.mkShell {
          name = "pyqgis3-qt5";
          packages = commonPackages ++ [ qgisLtrWithExtras ] ++ qt5Packages;
          LD_LIBRARY_PATH = commonLibPath;
          shellHook = ''
            echo "🔧 Using PyQGIS for QGIS 3 and Qt5 devShell (for QGIS 3 LTR development)"
          ''
          + qt5Positioning
          + commonShellHook;
        };
        pyqgis4-qt6 = pkgs.mkShell {
          name = "pyqgis4-qt6";
          packages = commonPackages ++ [ qgisWithExtras ] ++ qt6Packages;
          LD_LIBRARY_PATH = commonLibPath;
          shellHook = ''
            echo "🔧 Using PyQGIS for QGIS 4 and Qt6 devShell (for QGIS 4 development)"
          ''
          + qt6Positioning
          + commonShellHook;
        };
        default = pyqgis4-qt6;
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
