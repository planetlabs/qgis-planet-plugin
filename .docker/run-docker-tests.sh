#!/usr/bin/env bash

set -e

pushd /usr/src
DEFAULT_PARAMS='./planet_explorer/tests/ -v --qgis_disable_gui --qgis_disable_init'
xvfb-run pytest ${@:-`echo $DEFAULT_PARAMS`}
popd
