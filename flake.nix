{
  description = "NixOS developer environment for QGIS plugins.";

  inputs.geospatial.url = "github:imincik/geospatial-nix.repo";
  inputs.nixpkgs.follows = "geospatial/nixpkgs";

  outputs = { self, geospatial, nixpkgs }:
    let
      system = "x86_64-linux";
      profileName = "PLANET";
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

          # Start privoxy caching proxy in background, using .privoxy-cache in CWD
          # This is used for testing the plugin works properly behind a proxy
          export PRIVOXY_CACHE_DIR="$(pwd)/.privoxy-cache"
          mkdir -p "$PRIVOXY_CACHE_DIR"
          PRIVOXY_CONFIG_FILE="$(pwd)/.privoxy-config"
          PRIVOXY_PID_FILE=".privoxy.pid"
          if [ ! -f "$PRIVOXY_CONFIG_FILE" ]; then
            cat > "$PRIVOXY_CONFIG_FILE" <<EOF
listen-address  127.0.0.1:8123
logdir $PRIVOXY_CACHE_DIR
confdir $PRIVOXY_CACHE_DIR
EOF
          fi
          if [ ! -f "$PRIVOXY_PID_FILE" ] || ! kill -0 $(cat "$PRIVOXY_PID_FILE") 2>/dev/null; then
            privoxy --pidfile "$PRIVOXY_PID_FILE" "$PRIVOXY_CONFIG_FILE" &
            echo "Started privoxy proxy on 127.0.0.1:8123 (logdir: $PRIVOXY_CACHE_DIR)"
          fi

          # Upgrade pip and install packages from requirements.txt if it exists
          pip install --upgrade pip > /dev/null
          if [ -f requirements.txt ]; then
            echo "Installing Python requirements from requirements.txt..."
            pip install -r requirements.txt
          else
            echo "No requirements.txt found, skipping pip install."
          fi

          echo "-----------------------"
          echo "🌈 Your Dev Environment is prepared."
          echo "To run QGIS with your profile, use one of these commands:"
          echo ""
          echo "  nix run .#qgis"
          echo "  nix run .#qgis-ltr"
          echo ""
          echo "📒 Note:"
          echo "-----------------------"
          echo "We provide a ready-to-use"
          echo "VSCode environment which you"
          echo "can start like this:"
          echo ""
          echo "./vscode.sh"
          echo "-----------------------"

          pre-commit clean > /dev/null
          pre-commit install --install-hooks > /dev/null
          pre-commit run --all-files || true
        '';
      };

      apps.${system} = {
        qgis = {
          type = "app";
          program = "${qgisWithExtras}/bin/qgis";
          args = [ "--profile" "${profileName}" ];
        };
        qgis-ltr = {
          type = "app";
          program = "${qgisLtrWithExtras}/bin/qgis";
          args = [ "--profile" "${profileName}" ];
        };
      };
    };
}
