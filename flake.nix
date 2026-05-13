{
  description = "NixOS developer environment for QGIS plugins.";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";
    nixpkgs-unstable.url = "github:NixOS/nixpkgs/nixos-unstable";
  };
  outputs =
    {
      self,
      nixpkgs,
      nixpkgs-unstable,
      ...
    }@inputs:
    let
      system = "x86_64-linux";

      profileName = "PLANET";

      pkgs = import nixpkgs-unstable {
        inherit system;
        config = {
          allowUnfree = true;
        };
      };

      extraPythonPackagesQgis4 = ps: [
        ps.jsonschema
        ps.debugpy
        ps.psutil
      ];

      qgisWithExtras = pkgs.qgis.override {
        extraPythonPackages = extraPythonPackagesQgis4;
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
        pkgs.uv # Fast python package installer written in Rust
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
          # ps.pyqt5-stubs # For autocompletion in vscode
          ps.debugpy
          ps.numpy
          ps.gdal
          ps.snakeviz # For visualising cprofiler outputs
        ]))
      ];

      # Qt6 packages for QGIS 4 development
      qt6Packages = [
        pkgs.qt6.qtbase
        pkgs.qt6.qttools # includes designer
        pkgs.qt6.qtlocation
        pkgs.qt6.qtdeclarative
        pkgs.qt6.qtsvg
        pkgs.kdePackages.kcachegrind
        (pkgs.python3.withPackages (ps: [
          ps.pyqt6
          ps.qscintilla-qt6
        ]))
      ];

      commonShellHook = ''
        unset SOURCE_DATE_EPOCH

        export QGIS_PREFIX_PATH="${qgisWithExtras}"
        export PYTHONPATH="$(pwd)/.pyqgis-extra:${qgisWithExtras}/share/qgis/python:${qgisWithExtras}/${pkgs.python3.sitePackages}:$PYTHONPATH"

        mkdir -p .pyqgis-extra
        python -m pip install --target .pyqgis-extra astpretty tokenize-rt PyQt6-stubs
      '';
    in
    {
      devShells.${system} = {
        # Default devShell uses Qt6 for QGIS 4 development
        default = pkgs.mkShell {
          packages = commonPackages ++ qt6Packages ++ [ qgisWithExtras ];
          shellHook = ''
            echo "🔧 Using Qt6 devShell (for QGIS 4/Qt6 development)"
            echo "   Use 'nix develop .#qt5' for QGIS 3 LTR development tools"
            echo ""
          ''
          + commonShellHook;
        };
      };
    };
}
