#!/usr/bin/env bash

set -e

pushd /usr/src
DEFAULT_PARAMS='-v --qgis_disable_gui'
xvfb-run pytest ${@:-`echo $DEFAULT_PARAMS`}
popd
