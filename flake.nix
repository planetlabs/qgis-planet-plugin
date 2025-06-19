{
  description = "NixOS developer environment for QGIS plugins.";

  inputs.geospatial.url = "github:imincik/geospatial-nix.repo";
  inputs.nixpkgs.follows = "geospatial/nixpkgs";

  outputs = { self, geospatial, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        inherit system;
        config = { allowUnfree = true; };
      };
      extraPythonPackages = ps: [
        ps.pyqtwebengine
        ps.jsonschema
        ps.debugpy
        ps.future
        ps.psutil
      ];
      qgisWithExtras = geospatial.packages.${system}.qgis.override {
        inherit extraPythonPackages;
      };
      qgisLtrWithExtras = geospatial.packages.${system}.qgis-ltr.override {
        inherit extraPythonPackages;
      };
    in {
      packages.${system} = {
        default = qgisWithExtras;
        qgis-ltr = qgisLtrWithExtras;
      };

      devShells.${system}.default = pkgs.mkShell {
        packages = [
          pkgs.chafa
          pkgs.ffmpeg
          pkgs.gdb
          pkgs.git
          pkgs.glow # terminal markdown viewer
          pkgs.gource # Software version control visualization
          pkgs.gum
          pkgs.gum # UX for TUIs
          pkgs.jq
          pkgs.libsForQt5.kcachegrind
          pkgs.nixfmt-rfc-style
          pkgs.pre-commit
          pkgs.pyprof2calltree # needed to covert cprofile call trees into a format kcachegrind can read
          pkgs.python3
          pkgs.qgis
          pkgs.qt5.full # so we get designer
          pkgs.qt5.qtbase
          pkgs.qt5.qtlocation
          pkgs.qt5.qtquickcontrols2
          pkgs.qt5.qtsvg
          pkgs.qt5.qttools
          pkgs.skate # Distributed key/value store
          pkgs.vim
          pkgs.virtualenv
          pkgs.vscode
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
              # For autocompletion in vscode
              ps.pyqt5-stubs
              ps.debugpy
              ps.numpy
              ps.gdal
              ps.toml
              ps.typer
              ps.snakeviz # For visualising cprofiler outputs
          ]))

        ];
        shellHook = ''
          unset SOURCE_DATE_EPOCH

          # Create a virtual environment in .venv if it doesn't exist
          if [ ! -d ".venv" ]; then
            python -m venv .venv
          fi

          # Activate the virtual environment
          source .venv/bin/activate

          # Upgrade pip and install packages from requirements.txt
          pip install --upgrade pip
          pip install -r requirements.txt

          echo "-----------------------"
          echo "🌈 Your Dev Environment is prepared."
          echo "Run QGIS from the command line"
          echo "for a QGIS environment with"
          echo "geopandas and rasterio, start QGIS"
          echo "like this:"
          echo ""
          echo "./start_qgis.sh"
          echo ""
          echo "📒 Note:"
          echo "-----------------------"
          echo "We provide a ready-to-use"
          echo "VSCode environment which you"
          echo "can start like this:"
          echo ""
          echo "./vscode.sh"
          echo "-----------------------"
          pre-commit clean
          pre-commit install --install-hooks
          pre-commit run --all-files
          paver setup
          paver install --pluginpath=~/.local/share/QGIS/QGIS3/profiles/PLANET/python/plugins
        '';
      };
    };
}
