#!/usr/bin/env bash

set -e

pushd /usr/src
DEFAULT_PARAMS='./planet_explorer/tests/test_orders.py -k test_order_scene -v --reruns 2'
xvfb-run pytest ${@:-`echo $DEFAULT_PARAMS`}
popd
