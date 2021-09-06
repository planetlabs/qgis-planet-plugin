#!/usr/bin/env bash

set -e

pushd /usr/src
DEFAULT_PARAMS='-v'
xvfb-run pytest ${@:-`echo $DEFAULT_PARAMS`}
popd
